"""GitHub repository starring script.

Stars a curated list of popular GitHub repositories using the GitHub API.
Reads credentials from environment variables or prompts interactively.

Usage:
    python star_repos.py
    GITHUB_TOKEN=<token> python star_repos.py

Environment Variables:
    GITHUB_TOKEN: Personal access token with 'public_repo' scope.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from dataclasses import dataclass, field
from getpass import getpass

import aiohttp

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GITHUB_API_BASE = "https://api.github.com"
GITHUB_API_VERSION = "application/vnd.github.v3+json"

DEFAULT_REPOS: list[str] = [
    "torvalds/linux",
    "octocat/Hello-World",
    "github/gitignore",
    "microsoft/vscode",
    "facebook/react",
    "vuejs/vue",
    "angular/angular",
    "tensorflow/tensorflow",
    "twbs/bootstrap",
    "ohmyzsh/ohmyzsh",
    "freeCodeCamp/freeCodeCamp",
    "sindresorhus/awesome",
    "kamranahmedse/developer-roadmap",
    "EbookFoundation/free-programming-books",
    "jwasham/coding-interview-university",
    "donnemartin/system-design-primer",
]

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class GitHubAuthError(Exception):
    """Raised when authentication with the GitHub API fails."""


class GitHubAPIError(Exception):
    """Raised when a GitHub API request returns an unexpected error."""

    def __init__(self, repo: str, status: int, message: str) -> None:
        super().__init__(f"Failed to star '{repo}': HTTP {status} – {message}")
        self.repo = repo
        self.status = status
        self.message = message


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class StarResult:
    """Result of a single star operation.

    Attributes:
        repo: The ``owner/name`` repository slug.
        success: Whether the operation succeeded.
        already_starred: Whether the repo was already starred before this run.
        error: Optional error message on failure.
    """

    repo: str
    success: bool
    already_starred: bool = False
    error: str | None = None


@dataclass
class StarSession:
    """Holds shared state for a starring run.

    Attributes:
        token: GitHub personal access token.
        repos: List of ``owner/name`` repository slugs to star.
        results: Accumulated results populated during the run.
    """

    token: str
    repos: list[str] = field(default_factory=lambda: list(DEFAULT_REPOS))
    results: list[StarResult] = field(default_factory=list)

    @property
    def headers(self) -> dict[str, str]:
        """Build the HTTP headers required by the GitHub API."""
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": GITHUB_API_VERSION,
        }


# ---------------------------------------------------------------------------
# Core async logic
# ---------------------------------------------------------------------------


async def star_repo(
    session: aiohttp.ClientSession,
    star_session: StarSession,
    repo: str,
) -> StarResult:
    """Star a single repository via the GitHub API.

    Args:
        session: An active ``aiohttp.ClientSession``.
        star_session: The current :class:`StarSession` containing credentials.
        repo: Repository slug in ``owner/name`` format.

    Returns:
        A :class:`StarResult` describing the outcome.

    Raises:
        GitHubAuthError: If the token is invalid or lacks required scopes.
    """
    url = f"{GITHUB_API_BASE}/user/starred/{repo}"
    async with session.put(url, headers=star_session.headers) as response:
        match response.status:
            case 204:
                logger.info("✅ Starred %s", repo)
                return StarResult(repo=repo, success=True)
            case 304:
                logger.info("⏭️  Already starred %s", repo)
                return StarResult(repo=repo, success=True, already_starred=True)
            case 401 | 403:
                raise GitHubAuthError(
                    "Authentication failed. Verify your token has 'public_repo' scope."
                )
            case _:
                body = await response.text()
                error_msg = f"HTTP {response.status} – {body}"
                logger.error("❌ Failed to star %s: %s", repo, error_msg)
                return StarResult(repo=repo, success=False, error=error_msg)


async def run_star_session(star_session: StarSession) -> list[StarResult]:
    """Star all repositories in the session concurrently.

    Args:
        star_session: A configured :class:`StarSession`.

    Returns:
        A list of :class:`StarResult` objects, one per repository.
    """
    async with aiohttp.ClientSession() as http_session:
        tasks = [
            star_repo(http_session, star_session, repo) for repo in star_session.repos
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    processed: list[StarResult] = []
    for repo, result in zip(star_session.repos, results):
        if isinstance(result, GitHubAuthError):
            raise result
        if isinstance(result, Exception):
            logger.error("Unexpected error for %s: %s", repo, result)
            processed.append(StarResult(repo=repo, success=False, error=str(result)))
        else:
            assert isinstance(result, StarResult)
            processed.append(result)

    return processed


# ---------------------------------------------------------------------------
# Credential helpers
# ---------------------------------------------------------------------------


def resolve_token() -> str:
    """Resolve the GitHub personal access token.

    Checks the ``GITHUB_TOKEN`` environment variable first; falls back to an
    interactive prompt so the script can be used both in CI and locally.

    Returns:
        The token string.

    Raises:
        SystemExit: If running non-interactively and no token is available.
    """
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        logger.debug("Using GITHUB_TOKEN from environment.")
        return token

    if not sys.stdin.isatty():
        logger.error(
            "No GITHUB_TOKEN environment variable found and stdin is not a TTY. "
            "Set GITHUB_TOKEN before running this script in non-interactive mode."
        )
        sys.exit(1)

    return getpass("Personal access token (with public_repo scope): ")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def print_summary(results: list[StarResult]) -> None:
    """Print a summary of all star operations.

    Args:
        results: The list of :class:`StarResult` objects returned by the run.
    """
    succeeded = sum(1 for r in results if r.success and not r.already_starred)
    already = sum(1 for r in results if r.already_starred)
    failed = sum(1 for r in results if not r.success)

    logger.info(
        "\nSummary: %d newly starred | %d already starred | %d failed",
        succeeded,
        already,
        failed,
    )


def main() -> None:
    """Main entry point for the starring script."""
    token = resolve_token()
    session = StarSession(token=token)

    try:
        results = asyncio.run(run_star_session(session))
    except GitHubAuthError as exc:
        logger.error("Authentication error: %s", exc)
        sys.exit(1)

    print_summary(results)


if __name__ == "__main__":
    main()
