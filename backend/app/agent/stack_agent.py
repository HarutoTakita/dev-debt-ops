"""ADK Stack Analysis Agent for autonomous repository tech-stack detection."""

import logging
from datetime import UTC, datetime

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.base import generate_uuid7
from app.models.tech_stack import TechStack
from app.services.gemini_stack_service import analyze_tech_stack
from app.services.github_git_client import GitHubGitClient


def _vertex_model_name() -> str:
    """Return the Vertex AI full resource path for the configured Gemini model.

    ADK's Gemini.api_client sets vertexai=True when the model name starts with
    'projects/', which triggers ADC-based auth instead of an API key.
    """
    if settings.GOOGLE_CLOUD_PROJECT:
        return (
            f"projects/{settings.GOOGLE_CLOUD_PROJECT}"
            f"/locations/{settings.GOOGLE_CLOUD_LOCATION}"
            f"/publishers/google/models/{settings.GEMINI_MODEL}"
        )
    return settings.GEMINI_MODEL


logger = logging.getLogger(__name__)

_KEY_FILENAMES: frozenset[str] = frozenset(
    {
        "package.json",
        "pyproject.toml",
        "requirements.txt",
        "requirements-dev.txt",
        "go.mod",
        "Cargo.toml",
        "Gemfile",
        "pom.xml",
        "build.gradle",
        "Dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
        "vitest.config.ts",
        "vitest.config.js",
        "jest.config.ts",
        "jest.config.js",
        "pytest.ini",
        "setup.cfg",
        "terraform.tfvars",
    }
)

_KEY_EXTENSIONS: frozenset[str] = frozenset({".tf", ".bicep"})

_MAX_TOOL_FILES = 10
_MAX_FILE_CHARS = 5_000


def _is_key_file(path: str) -> bool:
    """Return True if path is a key configuration file for tech-stack detection."""
    filename = path.rsplit("/", 1)[-1]
    ext = ("." + filename.rsplit(".", 1)[-1]) if "." in filename else ""
    return (
        filename in _KEY_FILENAMES
        or ext in _KEY_EXTENSIONS
        or (".github/workflows/" in path and path.endswith((".yml", ".yaml")))
    )


def _summarize_args(args: dict) -> str:
    """Return a compact one-line summary of tool-call arguments for trace logging."""
    parts: list[str] = []
    for k, v in (args or {}).items():
        if isinstance(v, str) and len(v) > 80:
            parts.append(f"{k}=<{len(v)}chars>")
        elif isinstance(v, dict):
            parts.append(f"{k}=<dict:{len(v)}keys>")
        elif isinstance(v, list):
            parts.append(f"{k}=<list:{len(v)}items>")
        else:
            parts.append(f"{k}={v!r}")
    return ", ".join(parts)


def build_tools(github_client: GitHubGitClient, session: AsyncSession):
    """Build ADK tool functions with injected GitHub client and DB session.

    Returns a tuple of (list_key_files, read_file, classify_stack, save_stack).
    """

    async def list_key_files(owner: str, repo: str, branch: str = "main") -> list[str]:
        """List key configuration files in a repository for tech-stack analysis.

        Fetches the repository file tree and filters for configuration files such as
        package.json, pyproject.toml, Dockerfile, Terraform files, and CI workflows.
        Call this tool first to discover what configuration files are present.

        Args:
            owner: Repository owner or organisation name.
            repo: Repository name.
            branch: Branch to scan (defaults to main).

        Returns:
            List of file paths relevant for tech-stack detection.
        """
        try:
            tree = await github_client.get_repository_tree(owner, repo, branch)
            paths = [item.path for item in tree if item.type == "blob" and _is_key_file(item.path)]
            return paths[:_MAX_TOOL_FILES]
        except Exception as exc:
            logger.warning("list_key_files failed: %s", exc)
            return []

    async def read_file(owner: str, repo: str, path: str, ref: str = "main") -> str:
        """Read the content of a specific file from a GitHub repository.

        Retrieves the decoded text content of a file. Binary files return an empty
        string. Large files are truncated at 5000 characters.

        Args:
            owner: Repository owner or organisation name.
            repo: Repository name.
            path: File path within the repository (e.g. "package.json").
            ref: Git ref (branch, tag, or commit SHA) to read from.

        Returns:
            File content as text, or an empty string if the file cannot be read.
        """
        try:
            fc = await github_client.get_file_content(owner, repo, path, ref)
            content = fc.content or ""
            if len(content) > _MAX_FILE_CHARS:
                content = content[:_MAX_FILE_CHARS] + "\n... (truncated)"
            return content
        except Exception as exc:
            logger.warning("read_file %s failed: %s", path, exc)
            return ""

    async def classify_stack(files: dict[str, str]) -> dict:
        """Classify the technology stack from repository configuration file contents.

        Analyses the provided file contents and returns a structured classification
        of the technologies detected (languages, frameworks, databases, etc.) with
        confidence levels. Pass ALL file contents collected by read_file in one call.

        Args:
            files: Mapping of file paths to their text contents.

        Returns:
            Dict with two keys:
            - "languages": list of {"name": str, "confidence": "high"|"medium"|"low"}
            - "categories": dict mapping category names (frameworks, databases, auth,
              container, infra, cicd, monitoring, testing, other) to lists of tech items.
        """
        if not files:
            _cats = ("frameworks", "databases", "auth", "container", "infra", "cicd", "monitoring", "testing", "other")
            return {"languages": [], "categories": {k: [] for k in _cats}}
        try:
            return await analyze_tech_stack(files)
        except Exception as exc:
            logger.error("classify_stack failed: %s", exc)
            raise

    async def save_stack(owner: str, repo: str, branch: str, stack_result: dict) -> str:
        """Save the tech-stack analysis result to the database.

        Upserts the analysis result for the given repository. If a previous result
        exists for the same owner/repo, it is overwritten with the new data.

        Args:
            owner: Repository owner or organisation name.
            repo: Repository name.
            branch: Branch that was analysed.
            stack_result: Classification result with "languages" and "categories" keys,
                as returned by classify_stack.

        Returns:
            Confirmation message indicating the result was saved successfully.
        """
        now = datetime.now(UTC)
        new_id = generate_uuid7()
        stmt = pg_insert(TechStack).values(
            id=new_id,
            owner=owner,
            repo=repo,
            analyzed_at=now,
            languages=stack_result.get("languages", []),
            categories=stack_result.get("categories", {}),
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_tech_stacks_owner_repo",
            set_={
                "analyzed_at": now,
                "languages": stack_result.get("languages", []),
                "categories": stack_result.get("categories", {}),
            },
        )
        await session.execute(stmt)
        await session.commit()
        logger.info("Saved tech stack for %s/%s@%s", owner, repo, branch)
        return f"Saved tech stack for {owner}/{repo}@{branch}"

    return list_key_files, read_file, classify_stack, save_stack


def create_stack_agent(
    github_client: GitHubGitClient,
    session: AsyncSession,
) -> tuple[Agent, InMemorySessionService]:
    """Create the ADK Stack Analysis Agent with injected GitHub and DB dependencies."""
    list_key_files, read_file, classify_stack, save_stack = build_tools(github_client, session)

    agent = Agent(
        model=_vertex_model_name(),
        name="stack_analysis_agent",
        instruction="""\
あなたはリポジトリのテックスタックを自律的に解析するエージェントです。
以下の手順を順番に実行してください。

1. list_key_files を呼び出して、リポジトリの設定ファイル一覧を取得する。
2. 一覧に含まれる各ファイルを read_file で取得する (最大10ファイル)。
3. 取得した全ファイルのパスと内容を {"パス": "内容", ...} の辞書にまとめて classify_stack に渡す。
4. classify_stack の返却結果 (dict) をそのまま save_stack の stack_result 引数に渡して DB に保存する。

全ステップを完了したら、検出したテックスタックの概要を日本語で簡潔に報告してください。
""",
        tools=[list_key_files, read_file, classify_stack, save_stack],
    )

    session_service = InMemorySessionService()
    return agent, session_service


async def run_stack_analysis(
    github_client: GitHubGitClient,
    session: AsyncSession,
    owner: str,
    repo: str,
    branch: str = "main",
) -> list[str]:
    """Run the ADK stack analysis agent for the given repository.

    The agent autonomously calls list_key_files, read_file, classify_stack, and
    save_stack tools in sequence, committing the result to the database.

    Args:
        github_client: Authenticated GitHub API client.
        session: SQLAlchemy async session (must stay open until this coroutine returns).
        owner: Repository owner.
        repo: Repository name.
        branch: Branch to analyse.

    Returns:
        List of trace strings describing each tool call and the agent's final summary.

    Raises:
        ValueError: If Gemini credentials or project are not configured.
        RuntimeError: If the agent fails to complete the analysis.
    """
    agent, session_service = create_stack_agent(github_client, session)

    runner = Runner(
        agent=agent,
        app_name="rosetta",
        session_service=session_service,
    )

    adk_session = await session_service.create_session(
        app_name="rosetta",
        user_id=f"{owner}_{repo}",
    )

    user_message = Content(
        role="user",
        parts=[Part(text=f"リポジトリ {owner}/{repo} のブランチ {branch} のテックスタックを解析してください。")],
    )

    trace: list[str] = []

    async for event in runner.run_async(
        user_id=f"{owner}_{repo}",
        session_id=adk_session.id,
        new_message=user_message,
    ):
        if not event.content or not event.content.parts:
            continue
        for part in event.content.parts:
            if hasattr(part, "function_call") and part.function_call:
                fc = part.function_call
                trace.append(f"[call] {fc.name}({_summarize_args(fc.args or {})})")
            elif hasattr(part, "function_response") and part.function_response:
                fr = part.function_response
                trace.append(f"[done] {fr.name}")
            elif event.is_final_response() and hasattr(part, "text") and part.text:
                trace.append(f"[summary] {part.text[:500]}")

    return trace
