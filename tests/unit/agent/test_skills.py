from pathlib import Path

import pytest

from l1_support_agent.agent.skills import (
    KNOWN_SKILL_NAMES,
    SkillLoadError,
    load_skill,
)
from l1_support_agent.application.tool_policy import AgentContext, allowed_tool_names
from l1_support_agent.domain import Case, CaseState, Ticket


@pytest.mark.parametrize("skill_name", KNOWN_SKILL_NAMES)
def test_required_skill_loads(skill_name: str) -> None:
    skill = load_skill(skill_name)

    assert skill.name == skill_name
    assert skill.instructions.startswith("# ")
    assert "## Purpose" in skill.instructions
    assert "## Constraints / forbidden behavior" in skill.instructions


def test_unknown_skill_has_clear_error() -> None:
    with pytest.raises(SkillLoadError, match="Unknown skill 'not-a-skill'"):
        load_skill("not-a-skill")


def test_missing_required_skill_has_clear_error(tmp_path: Path) -> None:
    with pytest.raises(
        SkillLoadError,
        match="Required skill 'triage' is missing",
    ):
        load_skill("triage", skills_directory=tmp_path)


def test_skill_text_does_not_grant_tool_access() -> None:
    case = Case.from_ticket(
        Ticket(
            source="mockapi",
            source_id="42",
            user="alice",
            title="Office network unavailable",
            description="No user can reach the office network.",
        )
    )
    case.state = CaseState.PROCESSING
    l2_skill = load_skill("l2-escalation")

    assert "`escalate_l2`" in l2_skill.instructions
    assert allowed_tool_names(case, AgentContext(kb_searched=False)) == frozenset(
        {"search_kb"}
    )
