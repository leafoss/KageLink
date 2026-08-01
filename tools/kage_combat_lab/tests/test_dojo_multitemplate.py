from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from kage_combat_lab.dojo_multitemplate import (
    EmbeddedTrainerMatcher,
    embedded_trainer_templates,
)


def _matcher(*, threshold: float = 0.95) -> EmbeddedTrainerMatcher:
    return EmbeddedTrainerMatcher(threshold=threshold, scales=(1.0,))


def _frame_with(*placements: tuple[np.ndarray, int, int]) -> np.ndarray:
    frame = np.zeros((220, 260, 3), dtype=np.uint8)
    for image, left, top in placements:
        height, width = image.shape[:2]
        frame[top : top + height, left : left + width] = image
    return frame


def test_official_templates_are_distinct_canonical_64px_images() -> None:
    templates = embedded_trainer_templates()
    assert set(templates) == {"day-64", "night-64"}
    assert templates["day-64"].shape == (64, 64, 3)
    assert templates["night-64"].shape == (64, 64, 3)
    assert not np.array_equal(templates["day-64"], templates["night-64"])


def test_night_template_alone_is_detected() -> None:
    templates = embedded_trainer_templates()
    matcher = _matcher()
    match = matcher.match(_frame_with((templates["night-64"], 40, 60)))
    assert match is not None
    assert match.mode == "64"
    assert match.source_name == "night-64"
    assert matcher.last_scan.scores["night-64"] == pytest.approx(1.0, abs=1e-5)


def test_day_template_alone_is_detected() -> None:
    templates = embedded_trainer_templates()
    matcher = _matcher()
    match = matcher.match(_frame_with((templates["day-64"], 70, 80)))
    assert match is not None
    assert match.mode == "64"
    assert match.source_name == "day-64"
    assert matcher.last_scan.scores["day-64"] == pytest.approx(1.0, abs=1e-5)


def test_both_templates_are_scored_and_one_valid_match_is_accepted() -> None:
    templates = embedded_trainer_templates()
    matcher = _matcher()
    frame = _frame_with(
        (templates["night-64"], 20, 30),
        (templates["day-64"], 150, 120),
    )
    match = matcher.match(frame)
    assert match is not None
    assert matcher.last_scan.scores["night-64"] == pytest.approx(1.0, abs=1e-5)
    assert matcher.last_scan.scores["day-64"] == pytest.approx(1.0, abs=1e-5)
    assert match.source_name in {"night-64", "day-64"}


def test_no_template_match_fails_closed() -> None:
    rng = np.random.default_rng(20260801)
    noise = rng.integers(0, 256, size=(220, 260, 3), dtype=np.uint8)
    matcher = _matcher(threshold=0.98)
    match = matcher.match(noise)
    assert match is None
    assert matcher.last_scan.accepted is None
    assert matcher.last_scan.rejection_reason == "below-threshold"


def test_highest_score_wins_and_diagnostics_expose_both_scores() -> None:
    templates = embedded_trainer_templates()
    degraded_night = cv2.GaussianBlur(templates["night-64"], (9, 9), 0)
    matcher = _matcher(threshold=0.75)
    frame = _frame_with(
        (degraded_night, 20, 30),
        (templates["day-64"], 150, 120),
    )
    match = matcher.match(frame)
    assert match is not None
    assert match.source_name == "day-64"
    assert matcher.last_scan.scores["day-64"] > matcher.last_scan.scores["night-64"]

    diagnostics = matcher.diagnostics_text()
    assert "day64=" in diagnostics
    assert "night64=" in diagnostics
    assert "best=" in diagnostics
    assert "winner=day-64" in diagnostics


def test_windows_adapter_declares_winner_logs_and_installs_before_both_flows() -> None:
    package_root = Path(__file__).resolve().parents[1] / "kage_combat_lab"
    detector_source = (package_root / "dojo_multitemplate.py").read_text(encoding="utf-8")
    full_loop_source = (package_root / "full_loop.py").read_text(encoding="utf-8")
    full_round_source = (package_root / "full_round_daynight.py").read_text(encoding="utf-8")

    assert "TRAINER_TEMPLATE_SCORES" in detector_source
    assert "TRAINER_TEMPLATE_MATCH" in detector_source
    assert "selection=max(score)" in detector_source

    assert full_loop_source.index("install_day_night_dojo_detector()") < full_loop_source.index(
        "import kage_pilot_loop as canonical_loop"
    )
    assert full_round_source.index("install_day_night_dojo_detector()") < full_round_source.index(
        "from .full_round import main as full_round_main"
    )
