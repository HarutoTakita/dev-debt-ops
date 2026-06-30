"""Shallow git checkout of a repository to a temp dir (issue 069, for Serena/LSP).

Serena's language-server backend needs the repository as a real on-disk project tree (with config
files like ``pyproject.toml`` / ``tsconfig.json`` so the LSP resolves correctly) — the REST-only
``GitHubGitClient`` can't provide that. This shallow-clones the repo (``--depth 1``) into a temp
directory using the installation token, so the agentic run can point Serena at it and discard it
afterwards.

Graceful: any failure (git missing, auth/clone error, timeout) returns ``None`` so the Twin Agent
falls back to the REST-based repo tools. The caller owns deleting the returned directory.
"""

import asyncio
import base64
import logging
import shutil
import tempfile

logger = logging.getLogger(__name__)

_CLONE_TIMEOUT = 180.0  # seconds; bounds a slow/large clone


def _cleanup(path: str) -> None:
    shutil.rmtree(path, ignore_errors=True)


async def shallow_clone(owner: str, repo: str, branch: str, token: str) -> str | None:
    """Shallow-clone ``owner/repo@branch`` to a temp dir; return its path or ``None`` on failure.

    The token is passed via an ``http.extraHeader`` (not embedded in the remote URL or written to
    on-disk git config) to keep it out of the stored repo configuration.
    """
    if not (owner and repo and branch and token):
        return None
    tmp = tempfile.mkdtemp(prefix="repo-")
    url = f"https://github.com/{owner}/{repo}.git"
    auth = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    args = [
        "git",
        "-c",
        f"http.extraHeader=Authorization: Basic {auth}",
        "clone",
        "--depth",
        "1",
        "--single-branch",
        "--branch",
        branch,
        url,
        tmp,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
    except (FileNotFoundError, OSError):
        logger.warning("git not available; skipping repo checkout (Serena disabled this run)")
        _cleanup(tmp)
        return None
    try:
        async with asyncio.timeout(_CLONE_TIMEOUT):
            await proc.communicate()  # drain pipes; stderr is not logged (may echo the auth header)
    except TimeoutError:
        proc.kill()
        logger.warning("git clone timed out after %ss; skipping repo checkout", _CLONE_TIMEOUT)
        _cleanup(tmp)
        return None
    if proc.returncode != 0:
        # Don't log stderr verbatim — it may echo the auth header. Log only the code.
        logger.warning("git clone failed (rc=%s); skipping repo checkout", proc.returncode)
        _cleanup(tmp)
        return None
    return tmp
