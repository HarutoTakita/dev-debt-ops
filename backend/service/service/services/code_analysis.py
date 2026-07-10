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
from typing import NamedTuple

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


_HOTSPOT_WINDOW = 12  # lines; the sliding window used to locate the densest decision-point region


def complexity_hotspot(content: str, language: str) -> tuple[int, int, str] | None:
    """Locate the densest decision-point region: ``(start_line, end_line, verbatim_text)`` (1-based).

    Whole-file cyclomatic complexity doesn't say *where* the complexity is, so a top-of-file excerpt
    highlights imports rather than the offending logic. This slides a window over the file and returns
    the block with the most decision points (branches/loops/boolean ops), as verbatim contiguous source
    so the viewer can locate + highlight it. Returns ``None`` when no region stands out (caller falls
    back to a generic excerpt).
    """
    lines = content.split("\n")
    decision = _PY_DECISION if language == "python" else _JS_DECISION
    per_line = [len(decision.findall(_strip_noncode(ln, language))) for ln in lines]
    if sum(per_line) <= 0:
        return None
    if len(lines) <= _HOTSPOT_WINDOW:
        window = range(len(lines))
    else:
        best_start, best_sum = 0, -1
        for i in range(len(lines) - _HOTSPOT_WINDOW + 1):
            s = sum(per_line[i : i + _HOTSPOT_WINDOW])
            if s > best_sum:
                best_sum, best_start = s, i
        window = range(best_start, best_start + _HOTSPOT_WINDOW)
    # Trim to the branching span so the anchor lands on real logic (not the leading blank/def lines).
    dense = [i for i in window if per_line[i] > 0]
    lo, hi = dense[0], dense[-1]
    return (lo + 1, hi + 1, "\n".join(lines[lo : hi + 1]))


_PY_DEF_RE = re.compile(r"^\s*(?:async\s+)?def\s+(\w+)|^\s*class\s+(\w+)")
_JS_DEF_RE = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)"
    r"|^\s*(?:export\s+)?(?:default\s+)?class\s+(\w+)"
    r"|^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*="
)


def nearest_definition(content: str, line: int, language: str) -> str | None:
    """Name of the nearest def / class / function at or above 1-based ``line`` (best-effort, else None)."""
    pattern = _PY_DEF_RE if language == "python" else _JS_DEF_RE
    lines = content.split("\n")
    for i in range(min(line, len(lines)) - 1, -1, -1):
        m = pattern.match(lines[i])
        if m:
            return next((g for g in m.groups() if g), None)
    return None


def _normalized_lines(content: str) -> list[str]:
    """Strip whitespace, drop blank lines and single-line comments."""
    out: list[str] = []
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "//", "*", "/*")):
            continue
        out.append(line)
    return out


def _normalized_with_lineno(content: str) -> list[tuple[int, str]]:
    """Like ``_normalized_lines`` but keeps each kept line's 1-based original line number."""
    out: list[tuple[int, str]] = []
    for idx, raw in enumerate(content.splitlines()):
        line = raw.strip()
        if not line or line.startswith(("#", "//", "*", "/*")):
            continue
        out.append((idx + 1, line))
    return out


class DuplicateInfo(NamedTuple):
    """Per-file duplication result: the ratio plus *where* and *with whom* the block is shared."""

    ratio: float
    block_text: str  # verbatim source of the first duplicated block ("" when none)
    block_start_line: int  # 1-based; 0 when none
    block_end_line: int
    related_files: list[str]  # other files that contain a block duplicated with this file


def duplicate_report(files: dict[str, str]) -> dict[str, DuplicateInfo]:
    """Per-file duplication with the offending block's location + the partner files sharing it.

    A block ("window") of ``_DUP_WINDOW`` normalized lines is "duplicated" when its text occurs in two
    or more windows across the whole file set. Beyond the scalar ratio (kept for scoring), this reports
    the first duplicated block's verbatim source + original line range (so the viewer highlights the
    real location, not the file top) and the *other* files sharing a duplicated block (so a cross-file
    problem isn't presented as a lone single-file issue).
    """
    counts: dict[str, int] = {}
    key_to_files: dict[str, set[str]] = {}
    # (key, original_start_line, original_end_line) per window, per file.
    per_file: dict[str, list[tuple[str, int, int]]] = {}
    for path, content in files.items():
        norm = _normalized_with_lineno(content)
        windows: list[tuple[str, int, int]] = []
        for i in range(len(norm) - _DUP_WINDOW + 1):
            chunk = norm[i : i + _DUP_WINDOW]
            key = "\n".join(t for _, t in chunk)
            windows.append((key, chunk[0][0], chunk[-1][0]))
            counts[key] = counts.get(key, 0) + 1
            key_to_files.setdefault(key, set()).add(path)
        per_file[path] = windows

    report: dict[str, DuplicateInfo] = {}
    for path, windows in per_file.items():
        if not windows:
            report[path] = DuplicateInfo(0.0, "", 0, 0, [])
            continue
        dup = [w for w in windows if counts[w[0]] > 1]
        ratio = len(dup) / len(windows)
        block_text, start_line, end_line, related = "", 0, 0, []
        if dup:
            key, start_line, end_line = dup[0]
            block_text = "\n".join(content_lines(files[path])[start_line - 1 : end_line])
            related = sorted({f for w in dup for f in key_to_files[w[0]] if f != path})
        report[path] = DuplicateInfo(ratio, block_text, start_line, end_line, related)
    return report


def content_lines(content: str) -> list[str]:
    """Split file content into lines (helper so callers don't re-implement ``split``)."""
    return content.split("\n")


def find_duplicate_ratios(files: dict[str, str]) -> dict[str, float]:
    """Return per-file fraction of ``_DUP_WINDOW``-line blocks duplicated elsewhere in the repo."""
    return {path: info.ratio for path, info in duplicate_report(files).items()}


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
