from .states import CaseState
from .events import Events
from .errors import InvalidTransitionError


_TRANSITIONS = {
    (CaseState.NEW, Events.PROCESSING_STARTED): CaseState.PROCESSING,
    (CaseState.PROCESSING, Events.CLARIFICATION_REQUESTED): CaseState.AWAITING_USER,
    (CaseState.AWAITING_USER, Events.USER_REPLIED): CaseState.PROCESSING,
    (CaseState.PROCESSING, Events.CASE_RESOLVED): CaseState.RESOLVED,
    (CaseState.PROCESSING, Events.L2_ESCALATED): CaseState.ESCALATED_L2,
    (CaseState.PROCESSING, Events.DEVELOPMENT_ESCALATED): CaseState.ESCALATED_DEVELOPMENT,
}


def transition(state: CaseState, event: Events) -> CaseState:
    """Return the next case state for an event
    
    Raises:
        InvalidTransition
    """

    next_state = _TRANSITIONS.get((state, event))
    if next_state is None:
        raise InvalidTransitionError(
            f"Cannot apply event {event.value!r} to case in state {state.value!r}"
        )

    return next_state
