from __future__ import annotations

from pathlib import Path

from kage_combat_lab.post_ok_facing import control_mode_allows_post_ok_pulse


def test_perception_only_blocks_external_post_ok_turn(monkeypatch) -> None:
    monkeypatch.setenv("KAGE_PR26_CONTROL_MODE", "PERCEPTION_ONLY")
    assert not control_mode_allows_post_ok_pulse()


def test_face_only_starts_neutral_until_cluster_lock(monkeypatch) -> None:
    monkeypatch.setenv("KAGE_PR26_CONTROL_MODE", "FACE_ONLY")
    assert not control_mode_allows_post_ok_pulse()


def test_full_combat_preserves_validated_pr25_startup_pulse(monkeypatch) -> None:
    monkeypatch.setenv("KAGE_PR26_CONTROL_MODE", "FULL_COMBAT")
    assert control_mode_allows_post_ok_pulse()


def test_child_does_not_inherit_a_pulse_blocked_by_validation_mode() -> None:
    root = Path(__file__).resolve().parents[1] / "kage_combat_lab"
    source = (root / "runtime_startup_inherited.py").read_text(encoding="utf-8")
    assert 'mode != "FULL_COMBAT"' in source
    assert "inherited=false" in source
    assert "facing_source=UNKNOWN" in source
