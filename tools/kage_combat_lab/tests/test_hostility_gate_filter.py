from types import SimpleNamespace

import numpy as np

from kage_combat_lab.domain import CandidateObservation, GridCell, ObservationKind
from kage_combat_lab.hostility_gate import PR26HostilityGate
from kage_combat_lab.tile_perception import TileClass, TileEvidence


def evidence(cell: GridCell) -> TileEvidence:
    return TileEvidence(
        cell=cell,
        bbox=(cell.x * 64, cell.y * 64, 64, 64),
        category=TileClass.DANGER,
        similarity=0.97,
        novelty=0.03,
        known_terrain=True,
        temporal_activity=0.20,
        activity_bbox=(cell.x * 64 + 16, cell.y * 64 + 6, 24, 52),
        matched_example_id="danger-example",
    )


def candidate(track_id: int, cell: GridCell) -> CandidateObservation:
    bbox = (cell.x * 64 + 16, cell.y * 64 + 6, 24, 52)
    return CandidateObservation(
        track_id=track_id,
        anchor_cell=cell,
        kind=ObservationKind.CONTAMINATED_ACTIVITY,
        visible=True,
        body_like=False,
        confidence=0.60,
        cells_touched=frozenset({cell}),
        bbox=bbox,
        foot_point=(float(bbox[0] + 12), float(bbox[1] + 52)),
        relative_offset_px=(float(cell.x * 64), float(cell.y * 64)),
        motion_score=0.60,
    )


def runtime_context():
    frame = np.zeros((128, 512, 3), dtype=np.uint8)
    state = SimpleNamespace(
        arena_rect=(0, 0, 512, 128),
        player_center=(32.0, 32.0),
    )
    observer = SimpleNamespace(grid_origin=(0.0, 0.0))
    return frame, state, observer


def test_danger_tile_without_positive_track_never_creates_candidate() -> None:
    gate = PR26HostilityGate()
    frame, state, observer = runtime_context()
    cell = GridCell(4, 0)
    result = gate.filter_candidates(
        frame_bgr=frame,
        state=state,
        observer=observer,
        candidates=(),
        evidence={cell: evidence(cell)},
        now=0.0,
    )
    assert result == ()
    assert not gate.last_snapshot.visual_lock
    assert not gate.last_snapshot.combat_lock


def test_real_track_is_hidden_from_pr25_until_hostile_confirmed() -> None:
    gate = PR26HostilityGate()
    frame, state, observer = runtime_context()
    outputs = []
    for index, distance in enumerate((5, 4, 3, 2, 1)):
        cell = GridCell(distance, 0)
        outputs.append(
            gate.filter_candidates(
                frame_bgr=frame,
                state=state,
                observer=observer,
                candidates=(candidate(42, cell),),
                evidence={cell: evidence(cell)},
                now=float(index) * 0.5,
            )
        )

    assert outputs[0] == ()
    assert outputs[1] == ()
    assert outputs[2] == ()
    assert outputs[3] == ()
    assert len(outputs[4]) == 1
    authorized = outputs[4][0]
    assert authorized.track_id == 42
    assert authorized.track_id > 0
    assert authorized.kind is ObservationKind.CLEAN_BODY
    assert authorized.body_like
    assert gate.last_snapshot.combat_lock


def test_negative_track_is_never_forwarded_even_on_danger() -> None:
    gate = PR26HostilityGate()
    frame, state, observer = runtime_context()
    cell = GridCell(3, 0)
    result = gate.filter_candidates(
        frame_bgr=frame,
        state=state,
        observer=observer,
        candidates=(candidate(-1_000_007, cell),),
        evidence={cell: evidence(cell)},
        now=0.0,
    )
    assert result == ()
    assert not gate.last_snapshot.combat_lock
