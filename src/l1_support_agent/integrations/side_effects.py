import os
from collections.abc import Mapping
from enum import StrEnum


class SideEffectMode(StrEnum):
    MOCK = "mock"
    REAL = "real"


class SideEffectModeError(RuntimeError):
    """The external side-effect mode is not configured correctly."""


def side_effect_mode_from_env(
    environment: Mapping[str, str] | None = None,
) -> SideEffectMode:
    values = os.environ if environment is None else environment
    configured = values.get("SUPPORT_SIDE_EFFECT_MODE", SideEffectMode.MOCK).strip()
    try:
        return SideEffectMode(configured)
    except ValueError as error:
        raise SideEffectModeError(
            "SUPPORT_SIDE_EFFECT_MODE must be 'mock' or 'real'"
        ) from error
