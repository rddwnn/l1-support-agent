import asyncio
import json

import httpx
import pytest

from l1_support_agent.integrations.github import (
    GitHubClient,
    GitHubConfig,
    GitHubError,
)


def test_create_support_issue_posts_complete_issue() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            201,
            json={"html_url": "https://github.test/acme/app/issues/17"},
        )

    async def exercise() -> str:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
        ) as http_client:
            return await GitHubClient(
                http_client,
                GitHubConfig(
                    token="secret",
                    repository="acme/app",
                    api_url="https://github.test",
                ),
            ).create_support_issue(
                title="Login returns HTTP 500",
                technical_context="Failure occurs after valid credentials are sent.",
                ticket_description="User cannot sign in.",
                errors_logs="HTTP 500: database timeout",
                ticket_reference="https://support.test/tickets/17",
            )

    issue_url = asyncio.run(exercise())

    assert issue_url == "https://github.test/acme/app/issues/17"
    assert [(request.method, str(request.url)) for request in requests] == [
        ("POST", "https://github.test/repos/acme/app/issues")
    ]
    assert requests[0].headers["authorization"] == "Bearer secret"
    payload = json.loads(requests[0].content)
    assert payload["title"] == "Login returns HTTP 500"
    assert "Failure occurs after valid credentials" in payload["body"]
    assert "User cannot sign in" in payload["body"]
    assert "HTTP 500: database timeout" in payload["body"]
    assert "https://support.test/tickets/17" in payload["body"]


def test_create_support_issue_propagates_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "forbidden"})

    async def exercise() -> str:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
        ) as http_client:
            return await GitHubClient(
                http_client,
                GitHubConfig(token="token", repository="acme/app"),
            ).create_support_issue(
                title="Bug",
                technical_context="Context",
                ticket_description="Description",
                errors_logs="No logs",
                ticket_reference="mockapi:17",
            )

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(exercise())


def test_github_config_requires_owner_and_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "invalid")

    with pytest.raises(GitHubError, match="owner/repository"):
        GitHubConfig.from_env()
