from dataclasses import dataclass

from l1_support_agent.domain import Case, CaseState


@dataclass(frozen=True, slots=True)
class AgentContext:
    """Transient facts used to authorize tools during an agent run."""

    kb_searched: bool = False


class ToolNotAllowedError(RuntimeError):
    """The requested tool is not permitted for the current runtime state."""


_KB_INVESTIGATION_TOOLS = frozenset({"search_kb"})
_NEXT_STAGE_TOOLS = frozenset(
    {
        "request_clarification",
        "escalate_l2",
        "create_github_issue",
    }
)


def allowed_tool_names(
    case: Case,
    context: AgentContext,
) -> frozenset[str]:
    """Return tool names permitted for the current case and runtime context."""

    if case.state is not CaseState.PROCESSING:
        return frozenset()

    if not context.kb_searched:
        return _KB_INVESTIGATION_TOOLS

    return _NEXT_STAGE_TOOLS


def ensure_tool_allowed(
    tool_name: str,
    case: Case,
    context: AgentContext,
) -> None:
    """Reject a tool call unless it is currently authorized."""

    if tool_name not in allowed_tool_names(case, context):
        raise ToolNotAllowedError(
            f"Tool {tool_name!r} is not allowed for case state {case.state.value!r}"
        )
