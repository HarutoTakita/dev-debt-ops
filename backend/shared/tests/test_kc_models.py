"""shared KC models (issue 029) — schema-level defaults / tablenames (DB 不要)."""

import uuid

from shared.models import Dependency, FileKc


def test_file_kc_defaults() -> None:
    fk = FileKc(run_id=uuid.uuid4(), file_path="pkg/a.py", kc=0.5, mastery="dim_star")
    assert FileKc.__tablename__ == "file_kc"
    assert isinstance(fk.id, uuid.UUID)
    assert fk.dev_id is None
    assert fk.github_handle is None
    assert fk.certified_via is None
    assert fk.module == ""


def test_dependency_defaults() -> None:
    dep = Dependency(run_id=uuid.uuid4(), from_path="a.py", to_path="b.py")
    assert Dependency.__tablename__ == "dependencies"
    assert isinstance(dep.id, uuid.UUID)
