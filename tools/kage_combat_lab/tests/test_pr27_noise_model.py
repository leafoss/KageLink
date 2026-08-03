from __future__ import annotations

import cv2
import numpy as np

from kage_combat_lab.pr27_fixed_grid import DEFAULT_FIXED_GRID
from kage_combat_lab.pr27_noise_model import NoiseAwareDifferenceGate


def test_new_candidate_requires_twelve_percent_cell_activity() -> None:
    gate = NoiseAwareDifferenceGate(DEFAULT_FIXED_GRID)
    mask = np.zeros((1037, 1920), dtype=np.uint8)
    cell = DEFAULT_FIXED_GRID.roi_cells()[0]
    rect = cell.native_rect
    pixels = int(rect.width * rect.height * 0.094)
    patch = mask[rect.top:rect.bottom, rect.left:rect.right].reshape(-1)
    patch[:pixels] = 255
    result = gate.observe(mask)
    evidence = result.evidence[cell.relative_key]
    assert evidence.raw_changed_ratio < 0.12
    assert not evidence.passed_new_candidate_gate
    assert np.count_nonzero(result.proposal_mask[rect.top:rect.bottom, rect.left:rect.right]) == 0


def test_frame_128_body_cells_survive_noise_gate() -> None:
    gate = NoiseAwareDifferenceGate(DEFAULT_FIXED_GRID)
    mask = np.zeros((1037, 1920), dtype=np.uint8)
    keys = ((0, 0), (0, 1), (0, 2))
    ratios = (0.2842, 0.3423, 0.3442)
    for key, ratio in zip(keys, ratios):
        cell = next(item for item in DEFAULT_FIXED_GRID.roi_cells() if item.relative_key == key)
        rect = cell.native_rect
        patch = mask[rect.top:rect.bottom, rect.left:rect.right].reshape(-1)
        patch[: int(patch.size * ratio)] = 255
    result = gate.observe(mask)
    for key in keys:
        assert result.evidence[key].passed_new_candidate_gate
    assert result.noise_removed_ratio < 0.80


def test_existing_track_survives_below_twelve_percent() -> None:
    gate = NoiseAwareDifferenceGate(DEFAULT_FIXED_GRID)
    mask = np.zeros((1037, 1920), dtype=np.uint8)
    tracked = np.zeros_like(mask)
    cell = next(item for item in DEFAULT_FIXED_GRID.roi_cells() if item.relative_key == (0, 2))
    rect = cell.native_rect
    cv2.rectangle(mask, (rect.left + 20, rect.top + 15), (rect.left + 34, rect.top + 34), 255, -1)
    cv2.rectangle(tracked, (rect.left + 18, rect.top + 10), (rect.left + 38, rect.top + 40), 255, -1)
    result = gate.observe(mask, tracked_object_mask=tracked)
    evidence = result.evidence[cell.relative_key]
    assert evidence.raw_changed_ratio < 0.12
    assert evidence.passed_new_candidate_gate
    assert evidence.gate_override_reason == "TRACK_OVERRIDE_NOISE_GATE"
    assert np.count_nonzero(result.proposal_mask[rect.top:rect.bottom, rect.left:rect.right]) > 0


def test_noise_gate_does_not_blackout_entire_cell() -> None:
    gate = NoiseAwareDifferenceGate(DEFAULT_FIXED_GRID)
    mask = np.zeros((1037, 1920), dtype=np.uint8)
    cell = next(item for item in DEFAULT_FIXED_GRID.roi_cells() if item.relative_key == (0, 0))
    rect = cell.native_rect
    cv2.rectangle(mask, (rect.left + 8, rect.top + 8), (rect.left + 47, rect.top + 31), 255, -1)
    result = gate.observe(mask)
    patch = result.proposal_mask[rect.top:rect.bottom, rect.left:rect.right]
    assert 0 < np.count_nonzero(patch) < patch.size


def test_noise_model_reduces_water_but_keeps_body_override() -> None:
    gate = NoiseAwareDifferenceGate(DEFAULT_FIXED_GRID)
    mask = np.zeros((1037, 1920), dtype=np.uint8)
    body = np.zeros_like(mask)
    water = next(item for item in DEFAULT_FIXED_GRID.roi_cells() if item.relative_key == (-2, -2))
    body_cell = next(item for item in DEFAULT_FIXED_GRID.roi_cells() if item.relative_key == (0, 2))
    wp = mask[water.native_rect.top:water.native_rect.bottom, water.native_rect.left:water.native_rect.right].reshape(-1)
    wp[: int(wp.size * 0.095)] = 255
    cv2.rectangle(mask, (body_cell.native_rect.left + 22, body_cell.native_rect.top + 10), (body_cell.native_rect.left + 34, body_cell.native_rect.top + 42), 255, -1)
    cv2.rectangle(body, (body_cell.native_rect.left + 18, body_cell.native_rect.top + 6), (body_cell.native_rect.left + 38, body_cell.native_rect.top + 48), 255, -1)
    result = gate.observe(mask, body_override_mask=body)
    assert np.count_nonzero(result.proposal_mask[water.native_rect.top:water.native_rect.bottom, water.native_rect.left:water.native_rect.right]) == 0
    assert np.count_nonzero(result.proposal_mask[body_cell.native_rect.top:body_cell.native_rect.bottom, body_cell.native_rect.left:body_cell.native_rect.right]) > 0
