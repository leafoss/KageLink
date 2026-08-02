from __future__ import annotations

from pathlib import Path


def test_pr26_power_shell_launcher_has_no_shadow_mode() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "run_pr26_tile_combat.ps1").read_text(encoding="utf-8")
    assert "-FullLoop" in text
    assert "PreflightOnly" in text
    assert "shadow" not in text.casefold()


def test_physical_round_installs_tile_perception_before_main() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (
        root / "kage_combat_lab" / "full_round_daynight.py"
    ).read_text(encoding="utf-8")
    install_index = text.index("install_runtime_tile_perception")
    main_index = text.index("full_round_module.main()")
    assert install_index < main_index
