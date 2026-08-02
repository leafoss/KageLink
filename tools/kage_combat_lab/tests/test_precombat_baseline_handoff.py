from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

from kage_combat_lab.full_loop import (
    BASELINE_SECONDS_ENV,
    install_full_loop_round,
    replace_source_round_command,
)


def test_round_command_preserves_normal_child_startup_delay(monkeypatch) -> None:
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
    assert replaced[index + 1] == "1.0"


def test_full_loop_reserves_pre_ok_duration_and_preserves_spawn_wait(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

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

    assert values["spawn_delay_seconds"] == 5.0
    assert os.environ[BASELINE_SECONDS_ENV] == "5.0"
    index = command.index("--startup-delay")
    assert command[index + 1] == "1.0"


def test_each_round_resets_stale_pre_ok_baseline_file(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "baseline.npz"
    path.write_bytes(b"stale")
    monkeypatch.setenv("KAGE_PR26_PREOK_BASELINE_FILE", str(path))

    from kage_combat_lab.pre_ok_baseline import reset_pre_ok_baseline_capture

    reset_pre_ok_baseline_capture()

    assert not path.exists()
