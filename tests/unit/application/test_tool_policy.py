import pytest

from l1_support_agent.application.tool_policy import (
    AgentContext,
    ToolNotAllowedError,
    allowed_tool_names,
    ensure_tool_allowed,
)
from l1_support_agent.domain import Case, CaseState, Ticket


@pytest.fixture
def case() -> Case:
    ticket = Ticket(
        source="mockapi",
        source_id="42",
        user="alice",
        title="CRM returns 500",
        description="Saving a customer causes HTTP 500.",
    )
    return Case.from_ticket(ticket)


@pytest.mark.parametrize(
    "state",
    [
        CaseState.NEW,
        CaseState.AWAITING_USER,
        CaseState.RESOLVED,
        CaseState.ESCALATED_L2,
        CaseState.ESCALATED_DEVELOPMENT,
    ],
)
def test_non_processing_states_expose_no_tools(
    case: Case,
    state: CaseState,
) -> None:
    case.state = state

    assert allowed_tool_names(case, AgentContext()) == frozenset()


def test_processing_before_kb_search_exposes_only_search_kb(case: Case) -> None:
    case.state = CaseState.PROCESSING

    assert allowed_tool_names(case, AgentContext(kb_searched=False)) == frozenset(
        {"search_kb"}
    )


def test_processing_after_kb_search_exposes_next_stage_tools(case: Case) -> None:
    case.state = CaseState.PROCESSING

    allowed_names = allowed_tool_names(case, AgentContext(kb_searched=True))

    assert allowed_names == frozenset(
        {
            "request_clarification",
            "escalate_l2",
            "create_github_issue",
        }
    )
    assert "search_kb" not in allowed_names


def test_ensure_tool_allowed_accepts_currently_permitted_tool(case: Case) -> None:
    case.state = CaseState.PROCESSING

    ensure_tool_allowed("search_kb", case, AgentContext(kb_searched=False))


def test_ensure_tool_allowed_rejects_forbidden_tool(case: Case) -> None:
    case.state = CaseState.PROCESSING

    with pytest.raises(ToolNotAllowedError, match="create_github_issue"):
        ensure_tool_allowed(
            "create_github_issue",
            case,
            AgentContext(kb_searched=False),
        )


def test_tool_allowed_in_another_context_is_rejected(case: Case) -> None:
    case.state = CaseState.PROCESSING

    with pytest.raises(ToolNotAllowedError, match="search_kb"):
        ensure_tool_allowed(
            "search_kb",
            case,
            AgentContext(kb_searched=True),
        )
