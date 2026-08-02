from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

from kage_combat_lab.full_loop import (
    BASELINE_SECONDS_ENV,
    install_full_loop_round,
    replace_source_round_command,
)
from kage_combat_lab.full_round_daynight import _consume_transferred_startup_delay


def test_round_command_transfers_baseline_duration_to_child(monkeypatch) -> None:
    monkeypatch.setenv(BASELINE_SECONDS_ENV, "5.0")
    command = [
        "python.exe",
        "round.py",
        "--seconds",
        "60",
        "--startup-delay",
        "1.0",
    ]

    replaced = replace_source_round_command(command)

    assert replaced[:4] == [
        "python.exe",
        "-m",
        "kage_combat_lab.full_round_daynight",
        "--pr25-post-ok",
    ]
    index = replaced.index("--startup-delay")
    assert replaced[index + 1] == "5.0"


def test_full_loop_zeroes_outer_spawn_wait_and_preserves_duration(
    monkeypatch,
    tmp_path: Path,
) -> None:
    class Legacy:
        @staticmethod
        def _request_kwargs(args, *, round_number: int):
            return {"spawn_delay_seconds": 5.0, "round_number": round_number}

    def original_round(args, *, round_number: int):
        return (
            ["python.exe", "round.py", "--startup-delay", "1.0"],
            tmp_path,
        )

    engine = SimpleNamespace(
        _round_command=original_round,
        legacy_loop=Legacy,
        sys=SimpleNamespace(frozen=False),
    )
    install_full_loop_round(engine)

    values = engine.legacy_loop._request_kwargs(SimpleNamespace(), round_number=1)
    command, _ = engine._round_command(SimpleNamespace(), round_number=1)

    assert values["spawn_delay_seconds"] == 0.0
    assert os.environ[BASELINE_SECONDS_ENV] == "5.0"
    index = command.index("--startup-delay")
    assert command[index + 1] == "5.0"


def test_child_consumes_transferred_delay_only_once(monkeypatch) -> None:
    monkeypatch.setenv(BASELINE_SECONDS_ENV, "5.0")

    result = _consume_transferred_startup_delay(
        ["--seconds", "60", "--startup-delay", "5.0"]
    )

    index = result.index("--startup-delay")
    assert result[index + 1] == "0.0"
