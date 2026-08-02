from __future__ import annotations

from types import SimpleNamespace

import cv2
import numpy as np

from kage_combat_lab.domain import CandidateObservation, GridCell, ObservationKind
from kage_combat_lab.runtime_camera_compensation import (
    candidate_matches_cluster,
    estimate_camera_translation,
    proportional_artifact_reason,
)


def _reference() -> np.ndarray:
    image = np.zeros((256, 512, 3), dtype=np.uint8)
    for x in range(20, 490, 47):
        cv2.line(image, (x, 15), (x - 18, 235), (80 + x % 140, 120, 190), 3)
    for y in range(24, 240, 39):
        cv2.rectangle(image, (12, y), (498, y + 7), (35, 80 + y % 120, 145), -1)
    cv2.circle(image, (288, 156), 31, (210, 70, 45), -1)
    return image


def test_phase_registration_recovers_log_sized_camera_translation() -> None:
    reference = _reference()
    matrix = np.float32([[1.0, 0.0, -46.0], [0.0, 1.0, 3.0]])
    current = cv2.warpAffine(
        reference,
        matrix,
        (reference.shape[1], reference.shape[0]),
        flags=cv2.INTER_NEAREST,
    )
    mask = np.full(reference.shape[:2], 255, dtype=np.uint8)
    dx, dy, response, authoritative = estimate_camera_translation(
        reference,
        current,
        mask,
    )
    assert authoritative
    assert response >= 0.075
    assert abs(dx + 46.0) <= 2.0
    assert abs(dy - 3.0) <= 2.0


def test_phase_registration_blocks_shift_outside_physical_limit() -> None:
    reference = _reference()
    matrix = np.float32([[1.0, 0.0, 140.0], [0.0, 1.0, 0.0]])
    current = cv2.warpAffine(reference, matrix, (512, 256))
    mask = np.full(reference.shape[:2], 255, dtype=np.uint8)
    _, _, _, authoritative = estimate_camera_translation(reference, current, mask)
    assert not authoritative


def _cluster(*, cells, bbox, foot=(0.0, 0.0), mask_bbox=None):
    observations = []
    for cell in cells:
        mask = np.zeros((64, 64), dtype=np.uint8)
        if mask_bbox is not None:
            x, y, width, height = mask_bbox
            mask[y : y + height, x : x + width] = 255
        observations.append(
            SimpleNamespace(
                cell=cell,
                mask=mask,
                evidence=SimpleNamespace(bbox=(cell.x * 64, cell.y * 64, 64, 64)),
            )
        )
    return SimpleNamespace(
        cells=frozenset(cells),
        bbox=bbox,
        foot_point=foot,
        cell_observations=tuple(observations),
    )


def test_log_proven_128x44_top_band_is_rejected() -> None:
    cluster = _cluster(
        cells={GridCell(5, 0), GridCell(6, 0)},
        bbox=(320, 0, 128, 44),
    )
    assert proportional_artifact_reason(
        cluster,
        min_x=0,
        max_x=13,
        min_y=0,
        max_y=5,
    ) in {"PROPORTIONAL_HORIZONTAL_BAND", "TOP_CAMERA_BAND"}


def test_log_proven_48x192_edge_column_is_rejected() -> None:
    cluster = _cluster(
        cells={GridCell(0, 2), GridCell(0, 3), GridCell(0, 4)},
        bbox=(0, 128, 48, 192),
    )
    assert proportional_artifact_reason(
        cluster,
        min_x=0,
        max_x=13,
        min_y=0,
        max_y=5,
    ) == "EDGE_MULTI_CELL_COLUMN"


def test_central_vertical_body_remains_eligible() -> None:
    cluster = _cluster(
        cells={GridCell(7, 2)},
        bbox=(480, 128, 24, 64),
    )
    assert proportional_artifact_reason(
        cluster,
        min_x=0,
        max_x=13,
        min_y=0,
        max_y=5,
    ) is None


def test_raw_bbox_must_overlap_component_or_foot() -> None:
    cluster = _cluster(
        cells={GridCell(7, 2)},
        bbox=(456, 128, 24, 64),
        foot=(468.0, 191.0),
        mask_bbox=(18, 12, 24, 50),
    )
    far = CandidateObservation(
        track_id=8,
        anchor_cell=GridCell(7, 2),
        kind=ObservationKind.CLEAN_BODY,
        bbox=(520, 128, 20, 50),
        foot_point=(530.0, 178.0),
    )
    matched = CandidateObservation(
        track_id=9,
        anchor_cell=GridCell(7, 2),
        kind=ObservationKind.CLEAN_BODY,
        bbox=(457, 130, 22, 58),
        foot_point=(468.0, 187.0),
    )
    assert not candidate_matches_cluster(far, cluster)
    assert candidate_matches_cluster(matched, cluster)
