import os
from pathlib import Path

from l1_support_agent.knowledge.models import KnowledgeArticle
from l1_support_agent.knowledge.repository import KnowledgeRepository
from l1_support_agent.persistence.database import connect_database, init_database

DEMO_ARTICLE = KnowledgeArticle(
    id="demo-hardware-post-beep",
    title="Компьютер пищит при включении и не загружается",
    content=(
        "Отключите питание компьютера. Переустановите модули оперативной памяти, "
        "подключите питание и повторите запуск. Если компьютер продолжает пищать "
        "и не загружается, запишите код POST-сигнала и передайте его специалисту."
    ),
    category="hardware",
)


def seed_demo_kb(database_path: str | Path) -> KnowledgeArticle:
    """Add the small synthetic demo article to a local support database."""

    init_database(database_path)
    connection = connect_database(database_path)
    try:
        KnowledgeRepository(connection).add(DEMO_ARTICLE)
    finally:
        connection.close()
    return DEMO_ARTICLE


def main() -> None:
    database_path = Path(os.environ.get("SUPPORT_DB_PATH", "support.db"))
    article = seed_demo_kb(database_path)
    print(f"Seeded {article.id} into {database_path}")


if __name__ == "__main__":
    main()
