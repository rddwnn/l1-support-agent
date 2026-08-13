import os
from dataclasses import dataclass
from hashlib import sha256

import httpx


class GitHubError(RuntimeError):
    """GitHub configuration or issue response is invalid."""


@dataclass(frozen=True, slots=True)
class GitHubConfig:
    token: str
    repository: str
    api_url: str = "https://api.github.com"

    @classmethod
    def from_env(cls) -> "GitHubConfig":
        token = os.environ.get("GITHUB_TOKEN", "").strip()
        repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
        api_url = os.environ.get("GITHUB_API_URL", "https://api.github.com").strip()
        if not token or not repository or not api_url:
            raise GitHubError(
                "GITHUB_TOKEN, GITHUB_REPOSITORY, and GITHUB_API_URL must be configured"
            )
        if repository.count("/") != 1:
            raise GitHubError("GITHUB_REPOSITORY must use the owner/repository format")
        return cls(token=token, repository=repository, api_url=api_url.rstrip("/"))


class GitHubClient:
    def __init__(
        self,
        client: httpx.AsyncClient,
        config: GitHubConfig,
    ) -> None:
        self._client = client
        self._config = config

    async def create_support_issue(
        self,
        *,
        title: str,
        technical_context: str,
        ticket_description: str,
        errors_logs: str,
        ticket_reference: str,
    ) -> str:
        body = (
            "## Technical context\n"
            f"{technical_context}\n\n"
            "## Support ticket description\n"
            f"{ticket_description}\n\n"
            "## Errors / logs\n"
            f"{errors_logs}\n\n"
            "## Support ticket\n"
            f"{ticket_reference}"
        )
        response = await self._client.post(
            (
                f"{self._config.api_url}/repos/"
                f"{self._config.repository}/issues"
            ),
            headers={
                "Authorization": f"Bearer {self._config.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={"title": title, "body": body},
        )
        response.raise_for_status()

        payload = response.json()
        if not isinstance(payload, dict):
            raise GitHubError("GitHub issue response must be an object")
        issue_url = payload.get("html_url")
        if not isinstance(issue_url, str) or not issue_url.strip():
            raise GitHubError("GitHub issue response must contain an issue URL")

        return issue_url


class MockGitHubClient:
    """Deterministic network-free GitHub adapter for safe demos."""

    async def create_support_issue(
        self,
        *,
        title: str,
        technical_context: str,
        ticket_description: str,
        errors_logs: str,
        ticket_reference: str,
    ) -> str:
        payload = (
            f"{title}\0{technical_context}\0{ticket_description}\0"
            f"{errors_logs}\0{ticket_reference}"
        ).encode()
        stable_id = sha256(payload).hexdigest()[:16]
        return f"https://mock.invalid/github/issues/{stable_id}"
