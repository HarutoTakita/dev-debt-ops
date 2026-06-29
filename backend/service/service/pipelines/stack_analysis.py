"""``stack-analysis`` pipeline — ADK agent that scans a repo and persists its tech stack.

Moved from api's ``app.agent.stack_agent`` (issue 018). The heavy work — GitHub round-trips,
Vertex AI classification, ADK ``Runner`` orchestration — now runs inside the ``service``
container, off the api request path. ``shared.worker.run_task`` calls ``process(request, ctx)``
(idempotency + ``Job`` lifecycle are handled there); ``process`` mints a GitHub token
(method B), runs the agent on ``ctx.session``, and returns a ``StackAnalysisResult`` that the
worker writes into ``Job.result_data``.

The key-file heuristics (``_KEY_FILENAMES`` / ``_MAX_TOOL_FILES`` …) are carried over verbatim
so analysis quality is unchanged.
"""

import logging
import uuid
from datetime import UTC, datetime

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from service import config
from service.services.code_analysis import is_vendored_path
from service.services.gemini_stack_service import analyze_tech_stack
from service.services.github_app import GitHubAppService
from service.services.github_git_client import GitHubGitClient
from shared.enums import JobType, ResultStatus
from shared.models import TechStack
from shared.pipelines.context import PipelineContext
from shared.schemas.stack_analysis import (
    GitHubRef,
    StackAnalysisRequest,
    StackAnalysisResult,
    TechCategories,
    TechItem,
)

logger = logging.getLogger(__name__)


def _vertex_model_name() -> str:
    """Return the Vertex AI full resource path for the configured Gemini model.

    ADK's Gemini.api_client sets vertexai=True when the model name starts with
    'projects/', which triggers ADC-based auth instead of an API key.
    """
    project = config.google_cloud_project()
    if project:
        return (
            f"projects/{project}"
            f"/locations/{config.google_cloud_location()}"
            f"/publishers/google/models/{config.gemini_model()}"
        )
    return config.gemini_model()


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
    """Return True if path is a key configuration file for tech-stack detection.

    Vendored/installed paths (node_modules/*/package.json 等) are excluded — those configs
    belong to dependencies, not the team's own stack.
    """
    if is_vendored_path(path):
        return False
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
        stmt = pg_insert(TechStack).values(
            id=uuid.uuid4(),
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
        await session.flush()  # run_task owns the terminal commit (atomic with the Job, issue-042)
        logger.info("Saved tech stack for %s/%s@%s", owner, repo, branch)
        return f"Saved tech stack for {owner}/{repo}@{branch}"

    return list_key_files, read_file, classify_stack, save_stack


async def populate_tech_stack(
    github_client: GitHubGitClient,
    session: AsyncSession,
    owner: str,
    repo: str,
    branch: str = "main",
) -> None:
    """Detect + persist the repo's tech stack deterministically (no LLM agent).

    The agentic backbone needs ``tech_stacks`` populated *reliably* (it feeds the learning
    plan's "技術スタックを学ぶ" section via ``_stack_terms``). The ADK stack agent
    (``run_stack_analysis``) is not dependable here — it sometimes stops after
    ``classify_stack`` without ever calling ``save_stack``, leaving the table empty. This runs
    the same tools in a fixed sequence (list key files → read → ``analyze_tech_stack`` → upsert),
    so the judgement-free detection always persists. Flushes only; ``run_task`` owns the commit.
    """
    list_key_files, read_file, classify_stack, save_stack = build_tools(github_client, session)
    paths = await list_key_files(owner, repo, branch)
    files: dict[str, str] = {}
    for path in paths:
        content = await read_file(owner, repo, path, branch)
        if content:
            files[path] = content
    result = await classify_stack(files)
    await save_stack(owner, repo, branch, result)


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


async def _mint_installation_token(github: GitHubRef) -> str:
    """Resolve a GitHub installation token (method B: mint from Secret Manager key).

    If the request carries an explicit ``access_token`` (method A), it is used as-is;
    otherwise the service mints a short-lived token from the GitHub App private key so no
    secret ever travels over the queue / GCS.
    """
    if github.access_token is not None:
        return github.access_token.get_secret_value()
    app_service = GitHubAppService(app_id=config.github_app_id(), private_key=config.github_app_private_key())
    return await app_service.get_installation_token(github.installation_id)


async def _read_persisted(session: AsyncSession, owner: str, repo: str) -> tuple[list[TechItem], TechCategories]:
    """Read the just-saved ``TechStack`` row back into result schema objects."""
    result = await session.execute(
        select(TechStack).where(
            TechStack.owner == owner,  # ty: ignore[invalid-argument-type]
            TechStack.repo == repo,  # ty: ignore[invalid-argument-type]
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return [], TechCategories()
    languages = [TechItem.model_validate(item) for item in (row.languages or [])]
    categories = TechCategories.model_validate(row.categories or {})
    return languages, categories


async def process(request: StackAnalysisRequest, ctx: PipelineContext) -> StackAnalysisResult:
    """Run the ADK agent, persist the ``TechStack``, and return the result schema.

    ``shared.worker.run_task`` owns the ``Job`` lifecycle (PROCESSING → COMPLETED/FAILED,
    idempotency) and writes the returned result into ``Job.result_data``. This function runs
    on ``ctx.session`` so the ``TechStack`` upsert lands in the same DB as the Job update.
    """
    if ctx.session is None:
        raise RuntimeError("stack_analysis pipeline requires a DB session in the pipeline context")

    token = await _mint_installation_token(request.github)
    client = GitHubGitClient(access_token=token)
    try:
        trace = await run_stack_analysis(client, ctx.session, request.owner, request.repo, request.branch)
    finally:
        await client.aclose()

    languages, categories = await _read_persisted(ctx.session, request.owner, request.repo)
    return StackAnalysisResult(
        job_id=request.job_id,
        job_type=JobType.STACK_ANALYSIS,
        status=ResultStatus.COMPLETED,
        owner=request.owner,
        repo=request.repo,
        branch=request.branch,
        languages=languages,
        categories=categories,
        agent_trace=trace,
    )
