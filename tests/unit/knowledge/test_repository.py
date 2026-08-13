from pathlib import Path

from l1_support_agent.knowledge.models import KnowledgeArticle
from l1_support_agent.knowledge.repository import KnowledgeRepository
from l1_support_agent.persistence.database import (
    connect_database,
    init_database,
)


def test_search_returns_relevant_article(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "test.db"
    init_database(database_path)

    connection = connect_database(database_path)

    try:
        repository = KnowledgeRepository(connection)

        hardware_article = KnowledgeArticle(
            id="hardware-post-beep",
            title="Computer beep codes during startup",
            content=(
                "If a computer emits beep codes and does not boot, "
                "check the POST code and inspect the RAM."
            ),
            category="hardware",
        )

        network_article = KnowledgeArticle(
            id="network-no-internet",
            title="No internet connection",
            content=(
                "Check the network cable, Wi-Fi connection, "
                "and network adapter."
            ),
            category="network",
        )

        repository.add(hardware_article)
        repository.add(network_article)

        results = repository.search(
            "computer beep",
        )

        assert results
        assert results[0] == hardware_article

    finally:
        connection.close()


def test_get_returns_article_by_id_or_none(tmp_path: Path) -> None:
    database_path = tmp_path / "test.db"
    init_database(database_path)
    connection = connect_database(database_path)

    try:
        repository = KnowledgeRepository(connection)
        article = KnowledgeArticle(
            id="learned-case-42",
            title="Verified VPN recovery",
            content="Restart the gateway after applying the verified firmware.",
            category="network",
        )
        repository.add(article)

        assert repository.get(article.id) == article
        assert repository.get("missing") is None
    finally:
        connection.close()
