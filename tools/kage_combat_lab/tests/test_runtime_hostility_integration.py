from pathlib import Path


def source(name: str) -> str:
    return (
        Path(__file__).resolve().parents[1]
        / "kage_combat_lab"
        / name
    ).read_text(encoding="utf-8")


def test_full_round_installs_hostility_gate_before_facing_and_engagement() -> None:
    text = source("full_round_daynight.py")
    assert "install_runtime_tile_perception" in text
    assert text.index("install_runtime_tile_perception(") < text.index(
        "install_runtime_facing_patch(full_round_module)"
    )
    assert text.index("install_runtime_facing_patch(full_round_module)") < text.index(
        "install_runtime_engagement_recovery(full_round_module)"
    )


def test_runtime_uses_pr24_calibrated_offsets_for_cells_and_classification() -> None:
    text = source("runtime_tile_perception.py")
    assert 'calibration_payload.get("offset_x_px", 0)' in text
    assert 'calibration_payload.get("offset_y_px", 0)' in text
    assert "observer.grid_origin = calibrated_origin" in text
    assert "observer.grid_origin = previous_origin" in text


def test_old_unknown_activity_to_clean_body_path_is_not_called() -> None:
    text = source("runtime_tile_perception.py")
    assert "perception.enrich_candidates" not in text
    assert "combat_authorized = gate.filter_candidates" in text
    assert "synthetic_authority=BLOCKED" in text


def test_target_capsule_receives_only_combat_authorized_candidates() -> None:
    text = source("runtime_tile_perception.py")
    assert "candidates=combat_authorized" in text
    gate = source("hostility_gate.py")
    assert "if snapshot.combat_lock:" in gate
    assert "track_id=self._synthetic_id" not in gate


def test_f12_or_session_stop_persists_the_circular_video_buffer() -> None:
    text = source("runtime_tile_perception.py")
    assert '"F12_OR_SESSION_STOP"' in text
    assert "[frame.copy() for frame in buffered]" in text
    assert 'path.with_suffix(".json")' in text
    assert '"includes_f12_shutdown": True' in text


def test_prompt_invariants_remain_explicit() -> None:
    text = source("full_round_daynight.py")
    assert "tile-only and negative synthetic candidates have zero" in text
    assert "HOSTILE_CONFIRMED -> COMBAT_LOCK" in text
    domain = source("domain.py")
    assert "APPROACH_PULSE_MS: Final[int] = 100" in domain
    assert "H_PULSE_MS: Final[int] = 50" in domain
    assert "CELL_SIZE_PX: Final[int] = 64" in domain
