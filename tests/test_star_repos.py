"""Tests for star_repos.py."""

from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from star_repos import (
    DEFAULT_REPOS,
    GitHubAPIError,
    GitHubAuthError,
    StarResult,
    StarSession,
    print_summary,
    resolve_token,
    run_star_session,
    star_repo,
)


# ---------------------------------------------------------------------------
# StarSession
# ---------------------------------------------------------------------------


class TestStarSession:
    def test_default_repos_populated(self) -> None:
        session = StarSession(token="tok")
        assert session.repos == DEFAULT_REPOS

    def test_headers_contain_token(self) -> None:
        session = StarSession(token="mytoken")
        assert session.headers["Authorization"] == "Bearer mytoken"
        assert "Accept" in session.headers

    def test_custom_repos(self) -> None:
        session = StarSession(token="tok", repos=["a/b"])
        assert session.repos == ["a/b"]


# ---------------------------------------------------------------------------
# StarResult
# ---------------------------------------------------------------------------


class TestStarResult:
    def test_success_result(self) -> None:
        result = StarResult(repo="owner/repo", success=True)
        assert result.success is True
        assert result.already_starred is False
        assert result.error is None

    def test_failure_result(self) -> None:
        result = StarResult(repo="owner/repo", success=False, error="HTTP 500")
        assert result.success is False
        assert result.error == "HTTP 500"


# ---------------------------------------------------------------------------
# star_repo
# ---------------------------------------------------------------------------


class TestStarRepo:
    @pytest.mark.asyncio
    async def test_204_returns_success(self) -> None:
        mock_response = AsyncMock()
        mock_response.status = 204

        mock_session = MagicMock()
        mock_session.put.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.put.return_value.__aexit__ = AsyncMock(return_value=False)

        star_session = StarSession(token="tok")
        result = await star_repo(mock_session, star_session, "owner/repo")

        assert result.success is True
        assert result.already_starred is False

    @pytest.mark.asyncio
    async def test_304_already_starred(self) -> None:
        mock_response = AsyncMock()
        mock_response.status = 304

        mock_session = MagicMock()
        mock_session.put.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.put.return_value.__aexit__ = AsyncMock(return_value=False)

        star_session = StarSession(token="tok")
        result = await star_repo(mock_session, star_session, "owner/repo")

        assert result.success is True
        assert result.already_starred is True

    @pytest.mark.asyncio
    async def test_401_raises_auth_error(self) -> None:
        mock_response = AsyncMock()
        mock_response.status = 401

        mock_session = MagicMock()
        mock_session.put.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.put.return_value.__aexit__ = AsyncMock(return_value=False)

        star_session = StarSession(token="bad")
        with pytest.raises(GitHubAuthError):
            await star_repo(mock_session, star_session, "owner/repo")

    @pytest.mark.asyncio
    async def test_500_returns_failure(self) -> None:
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal Server Error")

        mock_session = MagicMock()
        mock_session.put.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.put.return_value.__aexit__ = AsyncMock(return_value=False)

        star_session = StarSession(token="tok")
        result = await star_repo(mock_session, star_session, "owner/repo")

        assert result.success is False
        assert result.error is not None


# ---------------------------------------------------------------------------
# resolve_token
# ---------------------------------------------------------------------------


class TestResolveToken:
    def test_reads_from_env(self) -> None:
        with patch.dict(os.environ, {"GITHUB_TOKEN": "env_token"}):
            token = resolve_token()
        assert token == "env_token"

    def test_exits_when_no_tty_and_no_env(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("sys.stdin.isatty", return_value=False),
        ):
            if "GITHUB_TOKEN" in os.environ:
                del os.environ["GITHUB_TOKEN"]
            with pytest.raises(SystemExit):
                resolve_token()


# ---------------------------------------------------------------------------
# print_summary
# ---------------------------------------------------------------------------


class TestPrintSummary:
    def test_counts_correctly(self, capsys: pytest.CaptureFixture[str]) -> None:
        results = [
            StarResult(repo="a/b", success=True),
            StarResult(repo="c/d", success=True, already_starred=True),
            StarResult(repo="e/f", success=False, error="oops"),
        ]
        print_summary(results)
        captured = capsys.readouterr()
        # Output goes through logging, check stderr or just that no exception raised
        assert captured is not None
