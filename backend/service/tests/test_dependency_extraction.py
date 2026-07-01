"""Intra-repo import resolution, incl. nested-package suffix matching (fixes 孤立クラスタ)."""

from service.services.dependency_extraction import extract_dependencies


def _edges(path: str, content: str, repo: set[str]) -> set[tuple[str, str]]:
    return {(e.from_path, e.to_path) for e in extract_dependencies(path, content, repo)}


def test_resolves_direct_repo_top_import() -> None:
    repo = {"pkg/a.py", "pkg/b.py"}
    assert _edges("pkg/a.py", "from pkg import b\n", repo) == {("pkg/a.py", "pkg/b.py")}


def test_resolves_nested_package_by_unique_suffix() -> None:
    # Nested layout: ``from app.foo import bar`` lives under backend/api/app/, not the repo top.
    repo = {"backend/api/app/foo.py", "backend/api/app/main.py"}
    edges = _edges("backend/api/app/main.py", "from app.foo import bar\n", repo)
    assert ("backend/api/app/main.py", "backend/api/app/foo.py") in edges


def test_ambiguous_suffix_is_skipped() -> None:
    # Two files match the suffix → ambiguous → no edge (never guess a wrong connection).
    repo = {"a/app/foo.py", "b/app/foo.py", "svc/main.py"}
    assert _edges("svc/main.py", "from app.foo import bar\n", repo) == set()
