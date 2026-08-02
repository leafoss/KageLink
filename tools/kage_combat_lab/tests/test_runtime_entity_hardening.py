from __future__ import annotations

from types import SimpleNamespace

from kage_combat_lab.domain import GridCell
from kage_combat_lab.occupancy_model import DiffSource
from kage_combat_lab.runtime_entity_hardening import (
    cluster_artifact_reason,
    danger_has_authority,
    global_scene_change_cells,
)


def _cluster(*, cells, bbox, ratio=0.25, area=500):
    return SimpleNamespace(
        cells=frozenset(cells),
        bbox=bbox,
        true_changed_ratio=ratio,
        largest_blob_area=area,
    )


def _cell(*, ratio, area, width, height):
    return SimpleNamespace(
        diff_source=DiffSource.EXACT_CELL_BASELINE,
        true_changed_ratio=ratio,
        largest_blob_area=area,
        blob_width=width,
        blob_height=height,
    )


def test_log_proven_horizontal_strip_is_rejected() -> None:
    cluster = _cluster(
        cells={GridCell(2, 0), GridCell(3, 0)},
        bbox=(128, 0, 128, 34),
        ratio=0.511,
        area=1900,
    )
    assert cluster_artifact_reason(
        cluster,
        min_x=0,
        max_x=13,
        min_y=0,
        max_y=5,
    ) in {"HORIZONTAL_UI_STRIP", "TOP_BORDER_STRIP"}


def test_vertical_central_body_remains_eligible() -> None:
    cluster = _cluster(
        cells={GridCell(6, 1)},
        bbox=(420, 64, 24, 64),
        ratio=0.204,
        area=840,
    )
    assert cluster_artifact_reason(
        cluster,
        min_x=0,
        max_x=13,
        min_y=0,
        max_y=5,
    ) is None


def test_thin_vertical_border_strip_is_rejected() -> None:
    cluster = _cluster(
        cells={GridCell(13, 3), GridCell(13, 4), GridCell(13, 5)},
        bbox=(900, 192, 11, 192),
        ratio=0.169,
        area=620,
    )
    assert cluster_artifact_reason(
        cluster,
        min_x=0,
        max_x=13,
        min_y=0,
        max_y=5,
    ) == "VERTICAL_BORDER_STRIP"


def test_danger_weak_prior_has_no_authority() -> None:
    assert not danger_has_authority(0.72)
    assert not danger_has_authority(0.81)
    assert danger_has_authority(0.82)
    assert danger_has_authority(0.95)


def test_distributed_baseline_failure_is_global_scene_change() -> None:
    cells = {
        GridCell(x, y): _cell(ratio=0.95, area=3000, width=60, height=60)
        for x, y in ((1, 0), (3, 0), (5, 0), (2, 1), (4, 1), (6, 1))
    }
    cells[GridCell(8, 3)] = _cell(ratio=0.20, area=500, width=24, height=48)
    severe = global_scene_change_cells(cells)
    assert len(severe) == 6
    assert GridCell(8, 3) not in severe


def test_single_body_does_not_trigger_global_scene_change() -> None:
    cells = {
        GridCell(6, 1): _cell(ratio=0.26, area=900, width=25, height=64),
        GridCell(6, 2): _cell(ratio=0.18, area=550, width=23, height=42),
    }
    assert global_scene_change_cells(cells) == set()
