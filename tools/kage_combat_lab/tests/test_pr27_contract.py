from __future__ import annotations

import inspect
from pathlib import Path

from kage_combat_lab import full_loop_pr27, full_round_daynight_pr27
from kage_combat_lab.pr27_native_grid import CellSearchGroup


def test_pr27_round_entry_does_not_install_pr26_combat_patch_chain() -> None:
    source = inspect.getsource(full_round_daynight_pr27)
    forbidden = (
        "runtime_mask_cluster_guard",
        "runtime_semantic_entity",
        "runtime_entity_hardening",
        "runtime_camera_compensation",
        "runtime_near_enemy_focus",
        "runtime_combat_target_memory",
        "runtime_tile_perception",
        "TargetCapsuleMemory",
        "GridFocusStrategy",
    )
    assert all(name not in source for name in forbidden)
    assert "full_round_pr27" in source


def test_outer_loop_routes_only_round_subprocess_to_pr27() -> None:
    replaced = full_loop_pr27.replace_source_round_command(
        ["python.exe", "legacy_round.py", "--seconds", "120"]
    )
    assert replaced[:4] == [
        "python.exe",
        "-m",
        "kage_combat_lab.full_round_daynight_pr27",
        "--pr27-post-ok",
    ]
    assert replaced[4:] == ["--seconds", "120"]


def test_cluster_contract_exposes_only_search_addresses() -> None:
    assert set(CellSearchGroup.__annotations__) == {"group_id", "cells"}


def test_native_capture_source_contains_explicit_uncompressed_path() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    capture_path = repo_root / "KageLink Installer" / "pc_agent" / "pc_agent" / "game_capture.py"
    if not capture_path.is_file():
        capture_path = Path(__file__).resolve().parents[1] / "game_capture.py"
    source = capture_path.read_text(encoding="utf-8")
    assert "def capture_native" in source
    native_section = source.split("def capture_native", 1)[1].split("def capture(", 1)[0]
    assert "transform_frame" not in native_section
    assert "format=\"JPEG\"" not in native_section
    assert "COLOR_RGB2BGR" in native_section
