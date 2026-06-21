"""shared feature-clustering models / enum unit tests (issue 052, DB-free)."""

import uuid

from shared.enums import Granularity, JobType
from shared.models import Feature, FeatureFile


def test_granularity_values() -> None:
    assert Granularity.FEATURE == "feature"
    assert Granularity.FOLDER == "folder"
    assert Granularity.FILE == "file"
    assert Granularity.CLASS == "class"
    assert Granularity.FUNCTION == "function"


def test_feature_clustering_job_type() -> None:
    assert JobType.FEATURE_CLUSTERING == "feature_clustering"


def test_feature_defaults() -> None:
    f = Feature(project_id=uuid.uuid4(), run_id=uuid.uuid4(), key="auth", name="認証")
    assert isinstance(f.id, uuid.UUID)
    assert f.description == ""
    assert f.source == "ai"


def test_feature_file_defaults() -> None:
    ff = FeatureFile(run_id=uuid.uuid4(), feature_id=uuid.uuid4(), file_path="src/auth.py")
    assert isinstance(ff.id, uuid.UUID)
    assert ff.confidence == 1.0


def test_tablenames_and_constraints() -> None:
    assert Feature.__tablename__ == "features"
    assert FeatureFile.__tablename__ == "feature_files"
    assert {c.name for c in Feature.__table__.constraints if c.name} >= {"uq_features_run_key"}
    assert {c.name for c in FeatureFile.__table__.constraints if c.name} >= {"uq_feature_files_run_feature_path"}
