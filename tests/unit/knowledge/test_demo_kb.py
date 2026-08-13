from pathlib import Path

from l1_support_agent.demo_kb import DEMO_ARTICLE, seed_demo_kb
from l1_support_agent.knowledge.repository import KnowledgeRepository
from l1_support_agent.persistence.database import connect_database


def test_demo_kb_seed_is_searchable_and_idempotent(tmp_path: Path) -> None:
    database_path = tmp_path / "demo.db"

    first = seed_demo_kb(database_path)
    second = seed_demo_kb(database_path)

    connection = connect_database(database_path)
    try:
        repository = KnowledgeRepository(connection)
        matches = repository.search("компьютер пищит")
        row_count = connection.execute(
            "SELECT COUNT(*) FROM knowledge_articles WHERE id = ?",
            (DEMO_ARTICLE.id,),
        ).fetchone()[0]
    finally:
        connection.close()

    assert first == second == DEMO_ARTICLE
    assert [article.id for article in matches] == [DEMO_ARTICLE.id]
    assert row_count == 1
