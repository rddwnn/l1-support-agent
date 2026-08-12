from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Ticket:
    """Support request independent of source"""

    source: str
    source_id: str
    user: str
    title: str
    description: str
    metadata: dict[str, object] = field(default_factory=dict)
    