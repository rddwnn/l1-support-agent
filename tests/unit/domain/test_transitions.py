import pytest

from l1_support_agent.domain import (
    CaseState,
    Events,
    InvalidTransitionError,
    transition,
)

VALID_TRANSITIONS = {
    (CaseState.NEW, Events.PROCESSING_STARTED): CaseState.PROCESSING,
    (CaseState.PROCESSING, Events.CLARIFICATION_REQUESTED): CaseState.AWAITING_USER,
    (CaseState.AWAITING_USER, Events.USER_REPLIED): CaseState.PROCESSING,
    (CaseState.PROCESSING, Events.CASE_RESOLVED): CaseState.RESOLVED,
    (CaseState.PROCESSING, Events.L2_ESCALATED): CaseState.ESCALATED_L2,
    (CaseState.PROCESSING, Events.DEVELOPMENT_ESCALATED): CaseState.ESCALATED_DEVELOPMENT
}


@pytest.mark.parametrize(
    ("state", "event", "expected"),
    [
        (state, event, expected)
        for (state, event), expected in VALID_TRANSITIONS.items()
    ]
)
def test_valid_transition(state, event, expected):
    assert transition(state, event) == expected


@pytest.mark.parametrize(
    ("state", "event"),
    [
        (state, event)
        for state in CaseState
        for event in Events
        if (state, event) not in VALID_TRANSITIONS
    ],
)
def test_invalid_transition_raises_invalid_transition_error(state, event):
    with pytest.raises(InvalidTransitionError):
        transition(state, event)
