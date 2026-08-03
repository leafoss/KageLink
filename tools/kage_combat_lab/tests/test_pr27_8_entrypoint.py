from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from kage_combat_lab.full_loop_pr27_8 import _perception_runtime_argv


def test_pr278_runtime_argv_does_not_forward_legacy_post_ok_marker() -> None:
    args = SimpleNamespace(
        combat_seconds=120.0,
        post_combat_timeout=240.0,
        round_startup_delay=1.0,
        chat_poll_seconds=0.15,
        recovery_hp_percent=90.0,
        recovery_chakra_percent=50.0,
        leader_threshold=0.88,
    )
    values = _perception_runtime_argv(args, Path("round_001.jsonl"))
    assert values[0] == "full_round_pr27_8"
    assert "--pr27-post-ok" not in values
    assert values[values.index("--seconds") + 1] == "120.0"
    assert values[values.index("--log") + 1] == "round_001.jsonl"
