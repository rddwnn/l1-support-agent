import os
from pathlib import Path

from l1_support_agent.knowledge.models import KnowledgeArticle
from l1_support_agent.knowledge.repository import KnowledgeRepository
from l1_support_agent.persistence.database import connect_database, init_database

DEMO_ARTICLE = KnowledgeArticle(
    id="demo-hardware-post-beep",
    title=(
        "Computer beeps during startup and does not boot / "
        "Компьютер пищит и не загружается"
    ),
    content=(
        "Power off the computer. Reseat the RAM modules, reconnect power, and "
        "retry startup. If the computer still emits POST beeps and does not boot, "
        "record the POST beep code and escalate for hardware diagnosis. "
        "Отключите питание компьютера, переустановите модули оперативной памяти "
        "и повторите запуск. Если компьютер продолжает пищать и не загружается, "
        "запишите код POST-сигнала и передайте его на аппаратную диагностику."
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
