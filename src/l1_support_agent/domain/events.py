from enum import StrEnum


class Events(StrEnum):
    PROCESSING_STARTED = "processing started"
    CLARIFICATION_REQUESTED = "clarification requested"
    USER_REPLIED = "user replied"
    CASE_RESOLVED = "case resolved"
    L2_ESCALATED = "l2 escalated"
    DEVELOPMENT_ESCALATED = "development escalated"
    