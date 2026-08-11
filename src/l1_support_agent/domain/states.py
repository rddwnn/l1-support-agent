from enum import StrEnum


class CaseState(StrEnum):
    NEW = "new"
    PROCESSING = "processing"
    AWAITING_USER = "awaiting user"
    RESOLVED = "resolved"
    ESCALATED_L2 = "escalated_l2"
    ESCALATED_DEVELOPMENT = "escalated"
