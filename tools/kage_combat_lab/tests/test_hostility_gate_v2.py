from __future__ import annotations

from dataclasses import replace

from kage_combat_lab.domain import CandidateObservation, GridCell, ObservationKind
from kage_combat_lab.hostility_gate import EntityState, HostilityState, StructuralMetrics
from kage_combat_lab.hostility_gate_v2 import PR26ContinuityHostilityGate
from kage_combat_lab.tile_perception import TileClass, TileEvidence


STRONG = StructuralMetrics(
    changed_pixel_ratio=0.24,
    largest_blob_area=900,
    blob_width=24,
    blob_height=52,
    edge_delta=0.30,
    structural_similarity=0.62,
)


def candidate(
    track_id: int,
    cell: GridCell,
    *,
    visible: bool = True,
) -> CandidateObservation:
    bbox = (cell.x * 64, cell.y * 64, 32, 48)
    return CandidateObservation(
        track_id=track_id,
        anchor_cell=cell,
        kind=ObservationKind.CONTAMINATED_ACTIVITY,
        visible=visible,
        body_like=False,
        confidence=0.70,
        cells_touched=frozenset({cell}),
        bbox=bbox,
        foot_point=(float(bbox[0] + 16), float(bbox[1] + 48)),
        relative_offset_px=(float(cell.x * 64), float(cell.y * 64)),
        motion_score=0.60,
    )


def tile(
    cell: GridCell,
    category: TileClass,
    confidence: float,
) -> TileEvidence:
    return TileEvidence(
        cell=cell,
        bbox=(cell.x * 64, cell.y * 64, 64, 64),
        category=category,
        similarity=confidence,
        novelty=1.0 - confidence,
        known_terrain=category is not TileClass.UNKNOWN,
        temporal_activity=0.20,
        activity_bbox=(cell.x * 64, cell.y * 64, 32, 48),
        matched_example_id="example",
    )


def test_danger_then_unknown_strong_confirms_visual_lock() -> None:
    gate = PR26ContinuityHostilityGate()
    cell = GridCell(5, 0)
    first = gate.observe_candidate(
        candidate=candidate(10, cell),
        evidence=tile(cell, TileClass.DANGER, 0.92),
        metrics=STRONG,
        player_cell=GridCell(0, 0),
        now=0.0,
    )
    assert first.entity_state is EntityState.DANGER_CANDIDATE
    assert not first.visual_lock

    second = gate.observe_candidate(
        candidate=candidate(10, cell),
        evidence=tile(cell, TileClass.UNKNOWN, 0.85),
        metrics=STRONG,
        player_cell=GridCell(0, 0),
        now=0.5,
    )
    assert second.entity_state is EntityState.ENTITY_CONFIRMED
    assert second.hostility_state is HostilityState.OBSERVE_HOSTILITY
    assert second.visual_lock
    assert not second.combat_lock


def test_danger_occluded_danger_confirms_with_two_of_three_votes() -> None:
    gate = PR26ContinuityHostilityGate()
    cell = GridCell(4, 0)
    danger = tile(cell, TileClass.DANGER, 0.94)
    gate.observe_candidate(
        candidate=candidate(11, cell),
        evidence=danger,
        metrics=STRONG,
        player_cell=GridCell(0, 0),
        now=0.0,
    )
    middle = gate.observe_candidate(
        candidate=candidate(11, cell, visible=False),
        evidence=danger,
        metrics=STRONG,
        player_cell=GridCell(0, 0),
        now=0.3,
    )
    assert not middle.visual_lock

    final = gate.observe_candidate(
        candidate=candidate(11, cell),
        evidence=danger,
        metrics=STRONG,
        player_cell=GridCell(0, 0),
        now=0.6,
    )
    assert final.entity_state is EntityState.ENTITY_CONFIRMED
    assert final.visual_lock
    assert not final.combat_lock


def test_raw_track_id_change_preserves_logical_entity() -> None:
    gate = PR26ContinuityHostilityGate()
    cell = GridCell(5, 0)
    danger = tile(cell, TileClass.DANGER, 0.96)
    gate.observe_candidate(
        candidate=candidate(20, cell),
        evidence=danger,
        metrics=STRONG,
        player_cell=GridCell(0, 0),
        now=0.0,
    )
    snapshot = gate.observe_candidate(
        candidate=candidate(21, cell),
        evidence=tile(cell, TileClass.UNKNOWN, 0.86),
        metrics=STRONG,
        player_cell=GridCell(0, 0),
        now=0.4,
    )
    assert snapshot.raw_track_id == 21
    assert snapshot.entity_state is EntityState.ENTITY_CONFIRMED
    assert snapshot.visual_lock


def test_unseeded_unknown_strong_cannot_create_entity() -> None:
    gate = PR26ContinuityHostilityGate()
    cell = GridCell(5, 0)
    snapshot = gate.observe_candidate(
        candidate=candidate(30, cell),
        evidence=tile(cell, TileClass.UNKNOWN, 0.88),
        metrics=STRONG,
        player_cell=GridCell(0, 0),
        now=0.0,
    )
    assert snapshot.entity_state is EntityState.TERRAIN_ONLY
    assert not snapshot.visual_lock
    assert not snapshot.combat_lock
    assert "NO_DANGER_SEED" in snapshot.reason


def test_autonomous_approach_reaches_combat_lock() -> None:
    gate = PR26ContinuityHostilityGate()
    player = GridCell(0, 0)
    snapshot = None
    for index, distance in enumerate((5, 4, 3, 2, 1)):
        cell = GridCell(distance, 0)
        snapshot = gate.observe_candidate(
            candidate=candidate(40, cell),
            evidence=tile(cell, TileClass.DANGER, 0.95),
            metrics=STRONG,
            player_cell=player,
            now=float(index) * 0.4,
        )
    assert snapshot is not None
    assert snapshot.hostility_state is HostilityState.HOSTILE_CONFIRMED
    assert snapshot.combat_lock
    assert snapshot.distance_history[-1] == 1


def test_negative_synthetic_id_remains_blocked() -> None:
    gate = PR26ContinuityHostilityGate()
    cell = GridCell(-2, 0)
    snapshot = gate.observe_candidate(
        candidate=candidate(-1_000_007, cell),
        evidence=tile(cell, TileClass.DANGER, 0.99),
        metrics=STRONG,
        player_cell=GridCell(0, 0),
        now=0.0,
    )
    assert snapshot.entity_state is EntityState.TERRAIN_ONLY
    assert not snapshot.visual_lock
    assert not snapshot.combat_lock


def test_entity_cell_prefers_foot_point_over_anchor_cell() -> None:
    raw = candidate(50, GridCell(7, 2))
    shifted = replace(raw, foot_point=(170.0, 130.0))
    cell = PR26ContinuityHostilityGate._entity_cell(shifted, (26.0, 42.0))
    assert cell == GridCell(2, 1)
