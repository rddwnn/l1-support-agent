import sqlite3

from .models import KnowledgeArticle


class KnowledgeRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def add(self, article: KnowledgeArticle) -> None:
        self._connection.execute(
            """
            INSERT INTO knowledge_articles (
                id,
                title,
                content,
                category
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                content = excluded.content,
                category = excluded.category
            """,
            (
                article.id,
                article.title,
                article.content,
                article.category,
            ),
        )

        self._connection.execute(
            """
            DELETE FROM knowledge_articles_fts
            WHERE article_id = ?
            """,
            (article.id,),
        )

        self._connection.execute(
            """
            INSERT INTO knowledge_articles_fts (
                article_id,
                title,
                content
            )
            VALUES (?, ?, ?)
            """,
            (
                article.id,
                article.title,
                article.content,
            ),
        )

        self._connection.commit()

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
    ) -> list[KnowledgeArticle]:
        rows = self._connection.execute(
            """
            SELECT
                a.id,
                a.title,
                a.content,
                a.category
            FROM knowledge_articles_fts AS fts
            JOIN knowledge_articles AS a
                ON a.id = fts.article_id
            WHERE knowledge_articles_fts MATCH ?
            ORDER BY bm25(knowledge_articles_fts)
            LIMIT ?
            """,
            (
                query,
                limit,
            ),
        ).fetchall()

        return [
            KnowledgeArticle(
                id=row["id"],
                title=row["title"],
                content=row["content"],
                category=row["category"],
            )
            for row in rows
        ]