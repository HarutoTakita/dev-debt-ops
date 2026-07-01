"""Extract intra-repository import edges (``dependency`` = "wormhole") from file content.

Given a file's path + content and the set of paths that exist in the repository snapshot,
this produces ``(from_path, to_path)`` edges for imports that resolve to **another file in the
same repository**. External/third-party specifiers (npm / PyPI packages) and unresolvable
imports are dropped — only intra-repo edges are returned, matching the product meaning of a
wormhole (``frontend/src/lib/api/schemas.ts`` ``wormholeSchema`` ``from`` / ``to``).

The output feeds the ``dependency`` rows owned by issue 026 (``run_id`` / ``from_path`` /
``to_path``); persistence (DML on ``ctx.session``) is the consuming pipeline's job (029). This
module is a pure function with no I/O. See ADR ``docs/adr/0002-git-history-access-and-authorship.md``.
"""

import posixpath
import re
from dataclasses import dataclass

_PY_EXTS = (".py",)
_TS_JS_EXTS = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")

# Python: ``import a.b.c`` / ``import a.b as x`` and ``from a.b import c`` / ``from . import x``.
_PY_IMPORT = re.compile(r"^\s*import\s+([.\w]+)", re.MULTILINE)
_PY_FROM = re.compile(r"^\s*from\s+([.\w]*)\s+import\s+(.+)$", re.MULTILINE)

# JS/TS: ``import ... from "x"`` / ``export ... from "x"`` / ``require("x")`` / ``import("x")``.
_JS_FROM = re.compile(r"""(?:import|export)\s[^;]*?from\s*['"]([^'"]+)['"]""")
_JS_BARE_IMPORT = re.compile(r"""(?<![\w.])import\s*['"]([^'"]+)['"]""")
_JS_REQUIRE = re.compile(r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)""")
_JS_DYNAMIC = re.compile(r"""import\s*\(\s*['"]([^'"]+)['"]\s*\)""")


@dataclass(frozen=True)
class DependencyEdge:
    """A directed intra-repo import edge (``from_path`` imports ``to_path``)."""

    from_path: str
    to_path: str


def _language(path: str) -> str | None:
    lower = path.lower()
    if lower.endswith(_PY_EXTS):
        return "python"
    if lower.endswith(_TS_JS_EXTS):
        return "ts_js"
    return None


def _norm(path: str) -> str:
    """Normalize a posix path (collapses ``.``/``..`` and a leading ``./``)."""
    return posixpath.normpath(path)


def _resolve_python(module: str, level: int, src_path: str, repo: set[str]) -> str | None:
    """Resolve a Python module reference to a repo file path, or ``None`` if external/unknown."""
    if level > 0:
        # Relative import: walk up ``level`` dirs from the source file's package directory.
        base = posixpath.dirname(src_path)
        for _ in range(level - 1):
            base = posixpath.dirname(base)
        rel = module.replace(".", "/") if module else ""
        stem = _norm(posixpath.join(base, rel)) if rel else _norm(base)
    else:
        # Absolute import rooted at the repo top (first-party package layout).
        stem = module.replace(".", "/")

    for candidate in (f"{stem}.py", f"{stem}/__init__.py"):
        candidate = _norm(candidate)
        if candidate in repo:
            return candidate
    # Nested-package fallback: many repos root first-party packages under src/ or backend/api/app/…,
    # so an absolute import like ``app.foo`` resolves to ``backend/api/app/foo.py``, not repo-top
    # ``app/foo.py``. Suffix-match a *uniquely* matching repo path so nested layouts still form edges
    # (a big source of "孤立したクラスタ"). Ambiguous (multiple) matches are skipped to avoid wrong edges.
    if level == 0:
        for suffix in (f"/{stem}.py", f"/{stem}/__init__.py"):
            matches = [p for p in repo if p.endswith(suffix)]
            if len(matches) == 1:
                return matches[0]
    return None


def _resolve_js(spec: str, src_path: str, repo: set[str]) -> str | None:
    """Resolve a relative JS/TS specifier to a repo file path, or ``None`` for bare/external."""
    if not (spec.startswith(".") or spec.startswith("/")):
        return None  # bare specifier → npm package, not an intra-repo edge
    base = posixpath.dirname(src_path)
    target = _norm(posixpath.join(base, spec))
    candidates = [target]
    candidates += [f"{target}{ext}" for ext in _TS_JS_EXTS]
    candidates += [f"{target}/index{ext}" for ext in _TS_JS_EXTS]
    for candidate in candidates:
        if candidate in repo:
            return candidate
    return None


def _parse_import_names(clause: str) -> list[str]:
    """Return the imported names from a ``from X import <clause>`` tail (``*`` and aliases dropped)."""
    clause = clause.split("#", 1)[0].strip().strip("()")
    names: list[str] = []
    for part in clause.split(","):
        token = part.strip().split(" as ", 1)[0].strip()
        if token and token != "*":
            names.append(token)
    return names


def _python_targets(content: str, src: str, repo: set[str]) -> list[str]:
    """Resolve every Python import in ``content`` to intra-repo file paths."""
    targets: list[str] = []
    for match in _PY_IMPORT.finditer(content):
        token = match.group(1)
        if token.startswith("."):
            continue
        resolved = _resolve_python(token, 0, src, repo)
        if resolved is not None:
            targets.append(resolved)
    for match in _PY_FROM.finditer(content):
        raw = match.group(1)
        level = len(raw) - len(raw.lstrip("."))
        module = raw[level:]
        if module:
            resolved = _resolve_python(module, level, src, repo)
            if resolved is not None:
                targets.append(resolved)
        # ``from . import sibling`` / ``from .pkg import mod`` — names may be submodules.
        for name in _parse_import_names(match.group(2)):
            sub = f"{module}.{name}" if module else name
            resolved = _resolve_python(sub, level, src, repo)
            if resolved is not None:
                targets.append(resolved)
    return targets


def _js_specs(content: str) -> list[str]:
    """Return raw module specifiers referenced by a JS/TS source."""
    specs: list[str] = []
    for pattern in (_JS_FROM, _JS_BARE_IMPORT, _JS_REQUIRE, _JS_DYNAMIC):
        specs.extend(pattern.findall(content))
    return specs


def extract_dependencies(path: str, content: str, repo_paths: set[str]) -> list[DependencyEdge]:
    """Return de-duplicated intra-repo import edges from ``path`` to other repo files.

    ``repo_paths`` is the set of file paths present in the repository snapshot (e.g. the blob
    paths from :meth:`GitHubGitClient.get_repository_tree`). Imports resolving outside this set
    (third-party packages, generated paths) are dropped. Self-edges are excluded.
    """
    src = _norm(path)
    language = _language(src)
    if language is None:
        return []

    targets: list[str] = []
    if language == "python":
        targets.extend(_python_targets(content, src, repo_paths))
    else:
        for spec in _js_specs(content):
            resolved = _resolve_js(spec, src, repo_paths)
            if resolved is not None:
                targets.append(resolved)

    edges: list[DependencyEdge] = []
    seen: set[str] = set()
    for target in targets:
        if target == src or target in seen:
            continue
        seen.add(target)
        edges.append(DependencyEdge(from_path=src, to_path=target))
    return edges
