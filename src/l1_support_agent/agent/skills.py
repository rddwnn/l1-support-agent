from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Skill:
    name: str
    instructions: str


class SkillLoadError(RuntimeError):
    """A required operational skill cannot be loaded."""


_SKILL_FILES = {
    "triage": Path("triage/SKILL.md"),
    "kb-investigation": Path("kb-investigation/SKILL.md"),
    "l2-escalation": Path("l2-escalation/SKILL.md"),
    "development-escalation": Path("development-escalation/SKILL.md"),
    "knowledge-update": Path("knowledge-update/SKILL.md"),
}
KNOWN_SKILL_NAMES = tuple(_SKILL_FILES)

SKILLS_DIRECTORY = Path(__file__).resolve().parents[1] / "skills"


def load_skill(
    name: str,
    *,
    skills_directory: Path = SKILLS_DIRECTORY,
) -> Skill:
    """Load one explicitly supported repository skill."""

    relative_path = _SKILL_FILES.get(name)
    if relative_path is None:
        known_names = ", ".join(sorted(_SKILL_FILES))
        raise SkillLoadError(
            f"Unknown skill {name!r}; expected one of: {known_names}"
        )

    path = skills_directory / relative_path
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise SkillLoadError(
            f"Required skill {name!r} is missing at {path}"
        ) from error

    parts = content.split("---", maxsplit=2)
    if len(parts) != 3 or parts[0].strip():
        raise SkillLoadError(f"Skill {name!r} has invalid SKILL.md frontmatter")

    instructions = parts[2].strip()
    if not instructions:
        raise SkillLoadError(f"Skill {name!r} contains no instructions")

    return Skill(name=name, instructions=instructions)
