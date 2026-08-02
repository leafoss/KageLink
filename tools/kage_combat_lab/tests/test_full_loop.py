from pathlib import Path
from types import SimpleNamespace

import pytest

from kage_combat_lab.full_loop import (
    POST_OK_GATE_ARG,
    ROUND_MODULE,
    install_full_loop_round,
    replace_source_round_command,
)
from kage_combat_lab.full_round import (
    MIN_MEDITATION_SECONDS,
    enforce_min_meditation_seconds,
)
from kage_combat_lab.full_round_daynight import extract_post_ok_gate


def test_round_replacement_adds_post_ok_gate_before_runtime_arguments():
    original = ["python", "kage_pilot_round.py", "--seconds", "120"]
    replaced = replace_source_round_command(original)
    assert replaced[:4] == ["python", "-m", ROUND_MODULE, POST_OK_GATE_ARG]
    assert replaced[4:] == original[2:]


def test_internal_post_ok_gate_is_removed_before_validated_parser():
    found, remaining = extract_post_ok_gate([POST_OK_GATE_ARG, "--seconds", "120"])
    assert found
    assert remaining == ["--seconds", "120"]


def test_missing_post_ok_gate_fails_closed():
    found, remaining = extract_post_ok_gate(["--seconds", "120"])
    assert not found
    assert remaining == ["--seconds", "120"]


def test_non_source_round_is_rejected_fail_closed():
    with pytest.raises(RuntimeError, match="SOURCE_CHECKOUT_ONLY"):
        replace_source_round_command(["KagePilotRound.exe", "--seconds", "120"])


def test_install_full_loop_round_preserves_arguments_and_adds_gate():
    def original(args, *, round_number: int):
        return ["python", "kage_pilot_round.py", "--seconds", "80"], Path("C:/repo")

    engine = SimpleNamespace(
        _round_command=original,
        sys=SimpleNamespace(frozen=False),
    )
    wrapped = install_full_loop_round(engine)
    command, cwd = wrapped(SimpleNamespace(), round_number=3)
    assert command == [
        "python",
        "-m",
        ROUND_MODULE,
        POST_OK_GATE_ARG,
        "--seconds",
        "80",
    ]
    assert cwd == Path("C:/repo")


def test_meditation_exit_is_never_allowed_before_physical_delay():
    engine = SimpleNamespace(min_meditation_seconds=0.75)
    protected = enforce_min_meditation_seconds(engine)
    assert protected == MIN_MEDITATION_SECONDS == 5.25
    assert engine.min_meditation_seconds == 5.25


def test_longer_existing_meditation_guard_is_preserved():
    engine = SimpleNamespace(min_meditation_seconds=6.0)
    protected = enforce_min_meditation_seconds(engine)
    assert protected == 6.0
    assert engine.min_meditation_seconds == 6.0
