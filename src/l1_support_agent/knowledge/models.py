from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class KnowledgeArticle:
    id: str
    title: str
    content: str
    category: str | None = None
