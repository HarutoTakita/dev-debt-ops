"""Static code-debt analysis helpers (issue 028) — pure, deterministic, dependency-light.

These functions are the MVP static analysis behind the ``code_debt_detection`` pipeline:
cyclomatic complexity, normalized-block duplication, and import-graph dead-file detection
(reusing :mod:`service.services.dependency_extraction`). They take file contents already
fetched via ``GitHubGitClient`` and return scores in ``0..1`` plus raw ``metrics``.

The severity quantization thresholds and the ``derive_priority`` bands are **fixed here**
(issue 028, see the doc's "severity 量子化・優先度近似" section) — there is no external spec
file in the repo, so these are the product-decision values, chosen to line up with doc 008's
``derivePriority`` bands and the mock data's 0..1 ranges.
"""

import re

from service.services.dependency_extraction import extract_dependencies

# --- tunables -------------------------------------------------------------
_COMPLEXITY_MIN = 8  # cyclomatic complexity at/above which a file is flagged as a complexity debt
_COMPLEXITY_SPAN = 25.0  # cc - 5 mapped over this span into 0..1 (cc 5→0.0, cc 30→1.0)
_DUP_WINDOW = 6  # consecutive normalized lines forming a duplication block
_DUP_MIN_RATIO = 0.2  # fraction of a file's windows that must be duplicated to flag it

_PY_EXTS = (".py",)
_TS_JS_EXTS = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")
_SOURCE_EXTS = _PY_EXTS + _TS_JS_EXTS

# インストール済み依存・生成物・ツールのディレクトリ。これらは開発者が書いたコードではないため、
# 解析（コード品質 / 理解度 / 理解負債 / 機能クラスタリング）の対象外にする。パスのいずれかの
# セグメントがこの集合に一致したら除外する（例: frontend/node_modules/x/index.js, backend/.venv/...）。
_VENDORED_DIRS: frozenset[str] = frozenset(
    {
        "node_modules",
        "bower_components",
        "jspm_packages",
        "vendor",
        "third_party",
        "third-party",
        "vendored",
        ".venv",
        "venv",
        "site-packages",
        "dist",
        "build",
        "target",  # Rust / Maven / Gradle 出力
        ".next",
        ".nuxt",
        ".svelte-kit",
        ".output",
        ".turbo",
        ".cache",
        ".parcel-cache",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "coverage",
        "htmlcov",
        ".gradle",
        "Pods",
        "Carthage",
        # デプロイバンドル（pip インストール先をリポジトリに同梱するもの）・パッケージング成果物。
        "lambda_package",
        "lambda_packages",
        ".serverless",
        ".aws-sam",
        ".tox",
        ".nox",
        ".eggs",
        "eggs",
        "wheels",
    }
)

# セグメント名そのものではなく*パターン*で判定する除外（任意名のバンドルでも拾える）:
#  - ``*.dist-info`` / ``*.egg-info`` / ``*.egg``: pip / setuptools がインストールしたパッケージのメタデータ。
_VENDORED_SEGMENT_RE = re.compile(r".+\.(?:dist-info|egg-info|egg)$", re.IGNORECASE)

# 自動生成・ボイラープレートのパス（開発者が読み書きして「理解」する対象ではない）: DB マイグレーション等。
# 単独著者リポジトリでは機能クラスタリング / 学習 / KC がこれら（例 ``alembic/versions/0001_*.py``）に
# 埋もれてしまうため、解析対象から一律除外する。
_GENERATED_PATH_RE = re.compile(r"(?:^|/)(?:alembic/versions|migrations|db/migrate)/", re.IGNORECASE)

# 開発者が自前モジュールとして書くことがまず無い、ユビキタスな第三者パッケージのトップレベル名。
# AWS Lambda 等のデプロイバンドル（任意ディレクトリ名）に同梱された installed module を、親ディレクトリ名に
# 依存せず除外するための補助シグナル（例: ``lambda_package/urllib3/connection.py``）。誤検知を避けるため
# 「自前命名と衝突しにくい」名前に限定する。
_VENDORED_PACKAGE_NAMES: frozenset[str] = frozenset(
    {
        "botocore",
        "boto3",
        "s3transfer",
        "jmespath",
        "urllib3",
        "certifi",
        "charset_normalizer",
        "idna",
        "dateutil",
        "six",
        "pkg_resources",
        "setuptools",
        "pip",
        "wheel",
    }
)


def is_vendored_path(path: str) -> bool:
    """Whether a path is an installed-dependency / generated / tooling file (node_modules, .venv, dist, build …).

    次のいずれかに該当したら True（解析パイプラインはこれで「開発者が書いていないファイル」を一律除外）:
      - セグメントが ``_VENDORED_DIRS`` に一致（例: ``frontend/node_modules/…``、``…/lambda_package/…``）
      - セグメントが ``*.dist-info`` / ``*.egg-info`` / ``*.egg``（pip/setuptools のパッケージメタデータ）
      - セグメントがユビキタスな第三者パッケージ名（``_VENDORED_PACKAGE_NAMES``）＝任意名バンドル内の installed module
      - 自動生成パス（``alembic/versions/`` / ``migrations/`` / ``db/migrate/`` = DB マイグレーション等）
    """
    if _GENERATED_PATH_RE.search(path):
        return True
    for segment in path.split("/"):
        if segment in _VENDORED_DIRS or segment in _VENDORED_PACKAGE_NAMES or _VENDORED_SEGMENT_RE.match(segment):
            return True
    return False


# Decision-point keywords per language family (base complexity is 1).
_PY_DECISION = re.compile(r"\b(if|elif|for|while|except|with|assert|and|or)\b|\bcase\b")
# 三項 `(?<!\?)\?(?![?.:])` は genuine ternary のみ計上（`?.` chaining / `??` nullish / `x?:` 型注釈は除外）。
_JS_DECISION = re.compile(r"\b(if|for|while|case|catch)\b|&&|\|\||(?<!\?)\?(?![?.:])")

# 複雑度カウント前に除去する「コード以外」（コメント・文字列・docstring）。これを剥がさないと、コメントや
# 文字列内の if/and/or/`?` が判定ポイントとして誤カウントされ、単純なファイルが complexity 負債と誤検知される。
_PY_NONCODE = re.compile(r"\"\"\"[\s\S]*?\"\"\"|'''[\s\S]*?'''|#[^\n]*|\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*'")
_JS_NONCODE = re.compile(r"/\*[\s\S]*?\*/|//[^\n]*|`(?:\\.|[^`\\])*`|\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*'")


def _strip_noncode(content: str, language: str) -> str:
    """Blank out comments / string / docstring literals so their keywords aren't miscounted as branches."""
    return (_PY_NONCODE if language == "python" else _JS_NONCODE).sub(" ", content)


# Files that are legitimately unreferenced by intra-repo imports (entrypoints / packaging).
_ENTRYPOINT_NAMES = ("__init__.py", "__main__.py", "main.py", "conftest.py", "index", "setup.py")


def _language(path: str) -> str | None:
    lower = path.lower()
    if lower.endswith(_PY_EXTS):
        return "python"
    if lower.endswith(_TS_JS_EXTS):
        return "ts_js"
    return None


def cyclomatic_complexity(content: str, language: str) -> int:
    """Approximate cyclomatic complexity = 1 + number of decision points."""
    pattern = _PY_DECISION if language == "python" else _JS_DECISION
    return 1 + len(pattern.findall(_strip_noncode(content, language)))


def complexity_score(complexity: int) -> float:
    """Map a cyclomatic-complexity count into ``0..1`` (cc 5 → 0.0, cc 30 → 1.0)."""
    return max(0.0, min(1.0, (complexity - 5) / _COMPLEXITY_SPAN))


def _normalized_lines(content: str) -> list[str]:
    """Strip whitespace, drop blank lines and single-line comments."""
    out: list[str] = []
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "//", "*", "/*")):
            continue
        out.append(line)
    return out


def find_duplicate_ratios(files: dict[str, str]) -> dict[str, float]:
    """Return per-file fraction of ``_DUP_WINDOW``-line blocks duplicated elsewhere in the repo.

    A block is "duplicated" if its normalized text appears in two or more distinct windows
    across all files. The ratio is duplicated-windows / total-windows for that file.
    """
    # Count every window's occurrences across the whole file set.
    counts: dict[str, int] = {}
    per_file_windows: dict[str, list[str]] = {}
    for path, content in files.items():
        lines = _normalized_lines(content)
        windows = ["\n".join(lines[i : i + _DUP_WINDOW]) for i in range(len(lines) - _DUP_WINDOW + 1)]
        per_file_windows[path] = windows
        for w in windows:
            counts[w] = counts.get(w, 0) + 1

    ratios: dict[str, float] = {}
    for path, windows in per_file_windows.items():
        if not windows:
            ratios[path] = 0.0
            continue
        dup = sum(1 for w in windows if counts[w] > 1)
        ratios[path] = dup / len(windows)
    return ratios


def _is_entrypoint(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0]
    return name in _ENTRYPOINT_NAMES or stem == "index" or "test" in name.lower() or "spec" in name.lower()


def find_dead_files(files: dict[str, str]) -> set[str]:
    """Return source files that nothing in the repo imports and that are not entrypoints.

    Builds intra-repo import edges via :func:`extract_dependencies`; a source file with zero
    inbound edges and a non-entrypoint name is a dead-code candidate (heuristic MVP).
    """
    repo_paths = set(files)
    referenced: set[str] = set()
    for path, content in files.items():
        for edge in extract_dependencies(path, content, repo_paths):
            referenced.add(edge.to_path)

    dead: set[str] = set()
    for path in files:
        if _language(path) is None or _is_entrypoint(path):
            continue
        if path not in referenced:
            dead.add(path)
    return dead


def quantize_severity(score: float) -> str:
    """Quantize a ``0..1`` code-debt score into a 4-level severity (issue 028 fixed thresholds)."""
    if score >= 0.75:
        return "critical"
    if score >= 0.5:
        return "high"
    if score >= 0.25:
        return "medium"
    return "low"


def derive_priority(code: float, knowledge_coverage: float) -> str:
    """Two-axis priority P0–P3 (issue 028; doc 008 ``derivePriority`` ported to Python).

    ``know = 1 − knowledge_coverage`` (low coverage ⇒ high knowledge risk). ``business_impact``
    is not yet available so the third axis is omitted.
    """
    know = 1.0 - knowledge_coverage
    if code >= 0.6 and know >= 0.6:
        return "P0"
    if code >= 0.6 or know >= 0.6:
        return "P1"
    if code >= 0.3 or know >= 0.3:
        return "P2"
    return "P3"


def is_source_file(path: str) -> bool:
    """Whether a path is a source file this analysis considers (vendored/generated paths excluded)."""
    return path.lower().endswith(_SOURCE_EXTS) and not is_vendored_path(path)


def complexity_is_debt(complexity: int) -> bool:
    """Whether a cyclomatic-complexity count is high enough to record as a debt."""
    return complexity >= _COMPLEXITY_MIN


def duplication_is_debt(ratio: float) -> bool:
    """Whether a file's duplication ratio is high enough to record as a debt."""
    return ratio >= _DUP_MIN_RATIO


def duplication_score(ratio: float) -> float:
    """Map a duplication ratio into ``0..1`` (ratio 0.5+ saturates to 1.0)."""
    return max(0.0, min(1.0, ratio * 2))


# --- excerpt selection (skip leading docstring / imports) -----------------
# quiz 素材やコードスニペットが「ファイル先頭」を機械的に切り出すと、docstring 主体のファイルでは
# モジュール docstring + import しか入らず、実装ではない自然言語プロースになる。以下は言語非依存の
# ヒューリスティックで、先頭の docstring・コメント・import 群を読み飛ばして実装が始まる行を返す。
_IMPORT_PREFIXES = ("import ", "from ", "export ", "require(", "#include", "package ", "use ", "using ")


def _docstring_delim(s: str) -> str | None:
    """If ``s`` opens a Python triple-quoted string (optionally after an r/b/u/f prefix), return the delim."""
    j = 0
    while j < len(s) and j < 2 and s[j].lower() in "rbuf":
        j += 1
    rest = s[j:]
    if rest.startswith('"""'):
        return '"""'
    if rest.startswith("'''"):
        return "'''"
    return None


def leading_code_line(content: str) -> int:
    """Return the 1-based line where real implementation begins, past a leading docstring/imports/comments.

    Language-agnostic heuristic: skips blank lines, ``#`` / ``//`` line comments, ``/* */`` block
    comments, a leading Python module docstring, and import/module declarations. Returns 1 when nothing
    is skippable, and never points past the last line (a file that is *only* boilerplate → 1, i.e. the top).
    """
    lines = content.split("\n")
    n = len(lines)
    i = 0
    in_block_comment = False
    in_docstring = False
    doc_delim = ""
    while i < n:
        s = lines[i].strip()
        if in_block_comment:
            if "*/" in s:
                in_block_comment = False
            i += 1
            continue
        if in_docstring:
            if doc_delim in s:
                in_docstring = False
            i += 1
            continue
        if not s or s.startswith("#") or s.startswith("//"):
            i += 1
            continue
        if s.startswith("/*"):
            if "*/" not in s[2:]:
                in_block_comment = True
            i += 1
            continue
        delim = _docstring_delim(s)
        if delim is not None:
            if delim in s[s.index(delim) + 3 :]:  # opens and closes on the same line
                i += 1
                continue
            in_docstring = True
            doc_delim = delim
            i += 1
            continue
        if s.startswith(_IMPORT_PREFIXES):
            i += 1
            continue
        return i + 1  # first line that is neither comment/docstring/import/blank → real code
    return 1  # whole file was boilerplate → don't skip everything; show from the top


def implementation_excerpt(content: str) -> str:
    """Return ``content`` from its first real implementation line (drops a leading docstring/import block)."""
    start = leading_code_line(content)
    if start <= 1:
        return content
    return "\n".join(content.split("\n")[start - 1 :])
