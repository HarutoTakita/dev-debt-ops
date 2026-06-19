"""Unit tests for the ADK stack analysis agent tools."""

from unittest.mock import AsyncMock

from app.agent.stack_agent import _is_key_file, build_tools
from app.services.github_git_client import FileContent, TreeItem

# ---------------------------------------------------------------------------
# _is_key_file
# ---------------------------------------------------------------------------


class TestIsKeyFile:
    """Tests for the key-file detection helper."""

    def test_package_json(self):
        """Root-level package.json is a key file."""
        assert _is_key_file("package.json")

    def test_nested_package_json(self):
        """Nested package.json is also a key file."""
        assert _is_key_file("frontend/package.json")

    def test_dockerfile(self):
        """Dockerfile is a key file."""
        assert _is_key_file("Dockerfile")

    def test_compose_yml(self):
        """compose.yml is a key file."""
        assert _is_key_file("compose.yml")

    def test_terraform_file(self):
        """*.tf extension is a key file."""
        assert _is_key_file("infra/main.tf")

    def test_github_workflow(self):
        """.github/workflows/*.yml is a key file."""
        assert _is_key_file(".github/workflows/ci.yml")

    def test_github_workflow_yaml(self):
        """.github/workflows/*.yaml is a key file."""
        assert _is_key_file(".github/workflows/deploy.yaml")

    def test_source_file_is_not_key(self):
        """Source code files are not key files."""
        assert not _is_key_file("src/main.ts")

    def test_test_file_is_not_key(self):
        """Test files are not key files."""
        assert not _is_key_file("tests/test_api.py")

    def test_readme_is_not_key(self):
        """README is not a key file."""
        assert not _is_key_file("README.md")

    def test_bicep_extension(self):
        """*.bicep extension is a key file."""
        assert _is_key_file("infra/main.bicep")


# ---------------------------------------------------------------------------
# list_key_files tool
# ---------------------------------------------------------------------------


class TestListKeyFiles:
    """Tests for the list_key_files tool."""

    async def test_returns_only_key_files(self):
        """Filters out non-config files from the tree."""
        mock_client = AsyncMock()
        mock_client.get_repository_tree.return_value = [
            TreeItem(path="package.json", type="blob", size=100),
            TreeItem(path="src/main.ts", type="blob", size=500),
            TreeItem(path="Dockerfile", type="blob", size=200),
            TreeItem(path="src", type="tree", size=None),
        ]
        list_key_files, _, _, _ = build_tools(mock_client, AsyncMock())

        result = await list_key_files("owner", "repo", "main")

        assert "package.json" in result
        assert "Dockerfile" in result
        assert "src/main.ts" not in result
        assert "src" not in result

    async def test_respects_max_files_limit(self):
        """Returns at most 10 files."""
        mock_client = AsyncMock()
        mock_client.get_repository_tree.return_value = [
            TreeItem(path=f"infra/file{i}.tf", type="blob", size=100) for i in range(20)
        ]
        list_key_files, _, _, _ = build_tools(mock_client, AsyncMock())

        result = await list_key_files("owner", "repo", "main")

        assert len(result) <= 10

    async def test_returns_empty_on_api_error(self):
        """Returns an empty list if the GitHub API fails."""
        mock_client = AsyncMock()
        mock_client.get_repository_tree.side_effect = Exception("GitHub API error")
        list_key_files, _, _, _ = build_tools(mock_client, AsyncMock())

        result = await list_key_files("owner", "repo", "main")

        assert result == []


# ---------------------------------------------------------------------------
# read_file tool
# ---------------------------------------------------------------------------


class TestReadFile:
    """Tests for the read_file tool."""

    async def test_returns_file_content(self):
        """Returns the decoded file content."""
        mock_client = AsyncMock()
        mock_client.get_file_content.return_value = FileContent(
            path="package.json",
            content='{"name": "test"}',
            sha="abc123",
            size=16,
        )
        _, read_file, _, _ = build_tools(mock_client, AsyncMock())

        result = await read_file("owner", "repo", "package.json")

        assert result == '{"name": "test"}'

    async def test_truncates_large_files(self):
        """Truncates content exceeding 5000 characters."""
        large_content = "x" * 10_000
        mock_client = AsyncMock()
        mock_client.get_file_content.return_value = FileContent(
            path="big.tf",
            content=large_content,
            sha="abc123",
            size=10_000,
        )
        _, read_file, _, _ = build_tools(mock_client, AsyncMock())

        result = await read_file("owner", "repo", "big.tf")

        assert len(result) <= 5_100
        assert "(truncated)" in result

    async def test_returns_empty_for_binary_file(self):
        """Returns an empty string for binary files (content=None)."""
        mock_client = AsyncMock()
        mock_client.get_file_content.return_value = FileContent(
            path="image.png",
            content=None,
            sha="abc123",
            size=1_000,
        )
        _, read_file, _, _ = build_tools(mock_client, AsyncMock())

        result = await read_file("owner", "repo", "image.png")

        assert result == ""

    async def test_returns_empty_on_error(self):
        """Returns an empty string if the file cannot be fetched."""
        mock_client = AsyncMock()
        mock_client.get_file_content.side_effect = Exception("Not found")
        _, read_file, _, _ = build_tools(mock_client, AsyncMock())

        result = await read_file("owner", "repo", "missing.json")

        assert result == ""


# ---------------------------------------------------------------------------
# classify_stack tool
# ---------------------------------------------------------------------------


class TestClassifyStack:
    """Tests for the classify_stack tool."""

    async def test_delegates_to_analyze_tech_stack(self, mocker):
        """Calls analyze_tech_stack with the provided file map."""
        _cat_keys = ("frameworks", "databases", "auth", "container", "infra", "cicd", "monitoring", "testing", "other")
        expected = {
            "languages": [{"name": "Python", "confidence": "high"}],
            "categories": {k: [] for k in _cat_keys},
        }
        mocker.patch("app.agent.stack_agent.analyze_tech_stack", return_value=expected)
        _, _, classify_stack, _ = build_tools(AsyncMock(), AsyncMock())

        result = await classify_stack({"pyproject.toml": '[project]\nname = "test"'})

        assert result["languages"][0]["name"] == "Python"

    async def test_returns_empty_result_for_no_files(self):
        """Returns an empty structure when no files are provided."""
        _, _, classify_stack, _ = build_tools(AsyncMock(), AsyncMock())

        result = await classify_stack({})

        assert result["languages"] == []
        assert "frameworks" in result["categories"]


# ---------------------------------------------------------------------------
# save_stack tool
# ---------------------------------------------------------------------------


class TestSaveStack:
    """Tests for the save_stack tool."""

    async def test_executes_upsert_and_commits(self):
        """Executes the upsert statement and commits the session."""
        mock_session = AsyncMock()
        _, _, _, save_stack = build_tools(AsyncMock(), mock_session)

        _cat_keys = ("frameworks", "databases", "auth", "container", "infra", "cicd", "monitoring", "testing", "other")
        stack_result = {
            "languages": [{"name": "TypeScript", "confidence": "high"}],
            "categories": {k: [] for k in _cat_keys},
        }

        result = await save_stack("owner", "repo", "main", stack_result)

        assert "owner/repo" in result
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    async def test_confirmation_message_contains_owner_repo(self):
        """The return message includes owner and repo."""
        mock_session = AsyncMock()
        _, _, _, save_stack = build_tools(AsyncMock(), mock_session)

        result = await save_stack("myorg", "myrepo", "develop", {"languages": [], "categories": {}})

        assert "myorg/myrepo" in result
