from pathlib import Path
from types import SimpleNamespace

import pytest

from kage_combat_lab.full_loop import (
    ROUND_MODULE,
    install_full_loop_round,
    replace_source_round_command,
)
from kage_combat_lab.full_round import (
    MIN_MEDITATION_SECONDS,
    enforce_min_meditation_seconds,
)


def test_source_round_replacement_preserves_every_validated_argument() -> None:
    original = [
        "C:/Python/python.exe",
        "C:/repo/kage_pilot_round.py",
        "--seconds",
        "120",
        "--post-combat-timeout",
        "240",
        "--previous-ko-name",
        "Jounin: Example",
    ]
    replaced = replace_source_round_command(original)
    assert replaced[:3] == ["C:/Python/python.exe", "-m", ROUND_MODULE]
    assert replaced[3:] == original[2:]


def test_non_source_round_is_rejected_fail_closed() -> None:
    with pytest.raises(RuntimeError, match="SOURCE_CHECKOUT_ONLY"):
        replace_source_round_command(["KagePilotRound.exe", "--seconds", "120"])


def test_install_full_loop_round_replaces_only_round_entrypoint() -> None:
    calls = []

    def original(args, *, round_number: int):
        calls.append((args, round_number))
        return ["python", "kage_pilot_round.py", "--seconds", "80"], Path("C:/repo")

    engine = SimpleNamespace(
        _round_command=original,
        sys=SimpleNamespace(frozen=False),
    )
    wrapped = install_full_loop_round(engine)
    command, cwd = wrapped(SimpleNamespace(), round_number=3)
    assert calls and calls[0][1] == 3
    assert command == ["python", "-m", ROUND_MODULE, "--seconds", "80"]
    assert cwd == Path("C:/repo")


def test_meditation_exit_is_never_allowed_before_physical_delay() -> None:
    engine = SimpleNamespace(min_meditation_seconds=0.75)
    protected = enforce_min_meditation_seconds(engine)
    assert protected == MIN_MEDITATION_SECONDS == 5.25
    assert engine.min_meditation_seconds == 5.25


def test_longer_existing_meditation_guard_is_preserved() -> None:
    engine = SimpleNamespace(min_meditation_seconds=6.0)
    protected = enforce_min_meditation_seconds(engine)
    assert protected == 6.0
    assert engine.min_meditation_seconds == 6.0
