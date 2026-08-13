import pytest

from l1_support_agent.integrations.side_effects import (
    SideEffectMode,
    SideEffectModeError,
    side_effect_mode_from_env,
)


def test_side_effect_mode_defaults_to_mock() -> None:
    assert side_effect_mode_from_env({}) is SideEffectMode.MOCK


def test_side_effect_mode_accepts_real() -> None:
    assert side_effect_mode_from_env(
        {"SUPPORT_SIDE_EFFECT_MODE": "real"}
    ) is SideEffectMode.REAL


def test_side_effect_mode_rejects_invalid_value() -> None:
    with pytest.raises(
        SideEffectModeError,
        match="SUPPORT_SIDE_EFFECT_MODE must be 'mock' or 'real'",
    ):
        side_effect_mode_from_env({"SUPPORT_SIDE_EFFECT_MODE": "unsafe"})
