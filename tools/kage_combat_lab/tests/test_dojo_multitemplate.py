from __future__ import annotations

from pathlib import Path
import sys

import cv2
import numpy as np
import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
PC_AGENT_ROOT = REPO_ROOT / "KageLink Installer" / "pc_agent"
if str(PC_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(PC_AGENT_ROOT))

from kage_combat_lab.dojo_multitemplate import (  # noqa: E402
    embedded_trainer_templates,
    install_day_night_dojo_detector,
)


def _detector(tmp_path: Path, *, threshold: float = 0.95):
    detector_class = install_day_night_dojo_detector()
    return detector_class(
        threshold=threshold,
        template_root=tmp_path,
        scales=(1.0,),
    )


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


def test_night_template_alone_is_detected(tmp_path: Path) -> None:
    templates = embedded_trainer_templates()
    detector = _detector(tmp_path)
    match = detector._best_visual(_frame_with((templates["night-64"], 40, 60)))
    assert match is not None
    assert detector.last_accepted_template_mode == "64"
    assert detector.last_accepted_template_source == "night-64"
    assert detector.last_template_scores["night-64"] == pytest.approx(1.0, abs=1e-5)


def test_day_template_alone_is_detected(tmp_path: Path) -> None:
    templates = embedded_trainer_templates()
    detector = _detector(tmp_path)
    match = detector._best_visual(_frame_with((templates["day-64"], 70, 80)))
    assert match is not None
    assert detector.last_accepted_template_mode == "64"
    assert detector.last_accepted_template_source == "day-64"
    assert detector.last_template_scores["day-64"] == pytest.approx(1.0, abs=1e-5)


def test_both_templates_are_scored_and_one_valid_match_is_accepted(tmp_path: Path) -> None:
    templates = embedded_trainer_templates()
    detector = _detector(tmp_path)
    frame = _frame_with(
        (templates["night-64"], 20, 30),
        (templates["day-64"], 150, 120),
    )
    match = detector._best_visual(frame)
    assert match is not None
    assert detector.last_template_scores["night-64"] == pytest.approx(1.0, abs=1e-5)
    assert detector.last_template_scores["day-64"] == pytest.approx(1.0, abs=1e-5)
    assert detector.last_accepted_template_source in {"night-64", "day-64"}


def test_no_template_match_fails_closed(tmp_path: Path) -> None:
    rng = np.random.default_rng(20260801)
    noise = rng.integers(0, 256, size=(220, 260, 3), dtype=np.uint8)
    detector = _detector(tmp_path, threshold=0.98)
    match = detector._best_visual(noise)
    assert match is None
    assert detector.last_accepted_template_source is None
    assert detector.last_rejection_reason == "below-threshold"


def test_highest_score_wins_and_diagnostics_expose_both_scores(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    templates = embedded_trainer_templates()
    degraded_night = cv2.GaussianBlur(templates["night-64"], (9, 9), 0)
    detector = _detector(tmp_path, threshold=0.75)
    frame = _frame_with(
        (degraded_night, 20, 30),
        (templates["day-64"], 150, 120),
    )
    match = detector._best_visual(frame)
    assert match is not None
    assert detector.last_accepted_template_source == "day-64"
    assert detector.last_template_scores["day-64"] > detector.last_template_scores["night-64"]

    diagnostics = detector.diagnostics_text()
    assert "day64=" in diagnostics
    assert "night64=" in diagnostics
    assert "best=" in diagnostics
    assert "winner=day-64" in diagnostics

    output = capsys.readouterr().out
    assert "TRAINER_TEMPLATE_SCORES" in output
    assert "TRAINER_TEMPLATE_MATCH template=day-64 mode=64" in output


def test_same_detector_class_is_installed_for_search_and_post_combat() -> None:
    from pc_agent.kage_pilot import dojo_templates_v35, post_combat_v03c

    detector_class = install_day_night_dojo_detector()
    assert dojo_templates_v35.UserDojoLeaderDetector is detector_class
    assert post_combat_v03c.PersistentDojoLeaderDetector is detector_class
