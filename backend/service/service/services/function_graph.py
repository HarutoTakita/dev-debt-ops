"""Deterministic source-based function/file graph (issue 250).

CodeGraphContext (CGC) builds the understanding map's L2 (file↔file) and L3 (per-file function
call graph) snapshots, but it is alpha and may fail to index a repo or return no functions. This
module derives the SAME node-link shape directly from source so L3 (and L2 ``file_edges``) are
guaranteed for any repository the product analyses:
  - Python: stdlib ``ast`` — function nodes + intra-file call edges (enclosing fn → callee).
  - TS/JS: lightweight regex heuristics — function nodes only (edge attribution needs brace
    matching, so we emit accurate nodes and leave edges to CGC; nodes alone still render L3).
  - file_edges: reuse :func:`dependency_extraction.extract_dependencies` (the import graph, same as
    wormholes).

The pipeline MERGES this with the CGC snapshot (CGC preferred, this fills the gaps) — see
``code_graph.merge_snapshots``. Pure/deterministic and dependency-light (matches ``code_analysis``).
Output shape matches ``code_graph.extract_snapshot``: ``{"file_edges", "functions", "function_calls"}``.
"""

import ast
import logging
import os
import re

from service.services import code_analysis
from service.services.dependency_extraction import extract_dependencies

logger = logging.getLogger(__name__)

# Bounds mirror code_graph._SNAPSHOT_* so the persisted snapshot stays UI-friendly regardless of source.
_FN_LIMIT = 8000  # cap function nodes + intra-file call edges
_EDGE_LIMIT = 2000  # cap file↔file edges
_MAX_FILES = 2000  # cap source files read from a clone
_MAX_FILE_BYTES = 512_000  # skip very large files (generated / minified)


class _PyVisitor(ast.NodeVisitor):
    """Collect function defs (ordered, unique) and raw (enclosing_fn, callee) pairs for one file.

    Calls are filtered to same-file targets *after* the walk (so forward references resolve).
    """

    def __init__(self) -> None:
        self.defs: list[str] = []
        self._defset: set[str] = set()
        self._stack: list[str] = []
        self.raw_calls: list[tuple[str, str]] = []

    def _enter_fn(self, node: ast.AST, name: str) -> None:
        if name not in self._defset:
            self._defset.add(name)
            self.defs.append(name)
        self._stack.append(name)
        self.generic_visit(node)
        self._stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._enter_fn(node, node.name)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._enter_fn(node, node.name)

    def visit_Call(self, node: ast.Call) -> None:
        callee = _callee_name(node.func)
        if callee and self._stack:
            self.raw_calls.append((self._stack[-1], callee))
        self.generic_visit(node)


def _callee_name(func: ast.expr) -> str | None:
    """Resolve a call target to a bare function/method name (``foo`` / ``obj.foo`` → ``foo``)."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def extract_python(content: str) -> tuple[list[str], list[tuple[str, str]]]:
    """Return ``(function_names, intra_file_call_edges)`` for one Python source (empty on syntax error)."""
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError):
        return [], []
    visitor = _PyVisitor()
    visitor.visit(tree)
    defset = set(visitor.defs)
    calls: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for src, dst in visitor.raw_calls:
        if dst in defset and src != dst and (src, dst) not in seen:
            seen.add((src, dst))
            calls.append((src, dst))
    return visitor.defs, calls


# TS/JS function-name heuristics. Names that are control-flow keywords are excluded so the method
# pattern (``NAME(...) {``) does not match ``if (...) {`` etc.
_TS_RESERVED = frozenset(
    {"if", "for", "while", "switch", "catch", "return", "function", "do", "else", "with", "await", "yield", "typeof"}
)
_TS_FUNC_DECL = re.compile(r"\bfunction\*?\s+([A-Za-z_$][\w$]*)\s*\(")
_TS_ASSIGN_FN = re.compile(
    r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?(?:function\b|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)"
)
_TS_METHOD = re.compile(r"(?m)^\s*(?:async\s+)?(?:static\s+)?(?:get\s+|set\s+)?([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{")


def extract_ts_js(content: str) -> tuple[list[str], list[tuple[str, str]]]:
    """Return ``(function_names, [])`` for one TS/JS source — nodes only (edges left to CGC)."""
    names: list[str] = []
    seen: set[str] = set()
    for pattern in (_TS_FUNC_DECL, _TS_ASSIGN_FN, _TS_METHOD):
        for match in pattern.finditer(content):
            name = match.group(1)
            if name in _TS_RESERVED or name in seen:
                continue
            seen.add(name)
            names.append(name)
    return names, []


def build_snapshot(files: dict[str, str]) -> dict:
    """Build a deterministic ``{file_edges, functions, function_calls}`` snapshot from source files.

    ``files`` maps repo-relative path → content. Non-source / vendored paths are skipped. Returns
    ``{}`` when nothing is extracted so the caller persists nothing (mirrors ``extract_snapshot``).
    """
    functions: list[dict[str, str]] = []
    function_calls: list[dict[str, str]] = []
    for path, content in files.items():
        if not code_analysis.is_source_file(path):
            continue
        defs, calls = extract_python(content) if path.lower().endswith(".py") else extract_ts_js(content)
        for name in defs:
            if len(functions) >= _FN_LIMIT:
                break
            functions.append({"file": path, "name": name})
        for src, dst in calls:
            if len(function_calls) >= _FN_LIMIT:
                break
            # Deterministic fallback resolves intra-file calls only → both endpoints share `path`
            # (matches the CGC snapshot shape; cross-file calls come from CGC, issue 282).
            function_calls.append({"source_file": path, "source": src, "target_file": path, "target": dst})

    repo_paths = set(files)
    file_edges: list[dict[str, str]] = []
    seen_edges: set[tuple[str, str]] = set()
    for path, content in files.items():
        for edge in extract_dependencies(path, content, repo_paths):
            key = (edge.from_path, edge.to_path)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            file_edges.append({"source": edge.from_path, "target": edge.to_path})
        if len(file_edges) >= _EDGE_LIMIT:
            break

    if not file_edges and not functions and not function_calls:
        return {}
    return {"file_edges": file_edges, "functions": functions, "function_calls": function_calls}


def read_repo_sources(repo_dir: str) -> dict[str, str]:
    """Read source files from a cloned repo into ``{repo-relative posix path: content}`` (bounded).

    Walks ``repo_dir`` skipping vendored/generated dirs and non-source files (``is_source_file``),
    capping count and per-file size. Paths use forward slashes to match CGC's ``File.relative_path``
    so the frontend joins by path. Best-effort: unreadable files are skipped.
    """
    if not repo_dir or not os.path.isdir(repo_dir):
        return {}
    files: dict[str, str] = {}
    for root, dirs, names in os.walk(repo_dir):
        # Prune vendored/generated/.git dirs in-place so os.walk doesn't descend into them.
        dirs[:] = [d for d in dirs if d != ".git" and not code_analysis.is_vendored_path(d)]
        for name in names:
            abs_path = os.path.join(root, name)
            rel = os.path.relpath(abs_path, repo_dir).replace(os.sep, "/")
            if not code_analysis.is_source_file(rel):
                continue
            try:
                if os.path.getsize(abs_path) > _MAX_FILE_BYTES:
                    continue
                with open(abs_path, encoding="utf-8", errors="replace") as fh:
                    files[rel] = fh.read()
            except OSError:
                continue
            if len(files) >= _MAX_FILES:
                return files
    return files
