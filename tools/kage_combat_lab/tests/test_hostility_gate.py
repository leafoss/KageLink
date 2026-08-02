from kage_combat_lab.domain import CandidateObservation, GridCell, ObservationKind
from kage_combat_lab.hostility_gate import (
    EntityState,
    HostilityState,
    PR26HostilityGate,
    StructuralMetrics,
)
from kage_combat_lab.tile_perception import TileClass, TileEvidence


def candidate(
    track_id: int,
    cell: GridCell,
    *,
    bbox: tuple[int, int, int, int] = (0, 0, 32, 48),
) -> CandidateObservation:
    return CandidateObservation(
        track_id=track_id,
        anchor_cell=cell,
        kind=ObservationKind.CONTAMINATED_ACTIVITY,
        visible=True,
        body_like=False,
        confidence=0.65,
        cells_touched=frozenset({cell}),
        bbox=bbox,
        foot_point=(float(bbox[0] + bbox[2] / 2), float(bbox[1] + bbox[3])),
        relative_offset_px=(float(cell.x * 64), float(cell.y * 64)),
        motion_score=0.60,
    )


def tile(
    cell: GridCell,
    *,
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


STRONG = StructuralMetrics(
    changed_pixel_ratio=0.24,
    largest_blob_area=900,
    blob_width=24,
    blob_height=52,
    edge_delta=0.30,
    structural_similarity=0.62,
)

NOISE = StructuralMetrics(
    changed_pixel_ratio=0.02,
    largest_blob_area=30,
    blob_width=5,
    blob_height=6,
    edge_delta=0.01,
    structural_similarity=0.98,
)


def test_floor_noise_never_creates_visual_or_combat_lock() -> None:
    gate = PR26HostilityGate()
    cell = GridCell(4, 2)
    snapshot = gate.observe_candidate(
        candidate=candidate(10, cell),
        evidence=tile(cell, category=TileClass.WALKABLE, confidence=0.99),
        metrics=NOISE,
        player_cell=GridCell(0, 0),
        now=0.0,
    )
    assert snapshot.entity_state is EntityState.TERRAIN_ONLY
    assert not snapshot.visual_lock
    assert not snapshot.combat_lock


def test_danger_is_not_automatically_an_enemy() -> None:
    gate = PR26HostilityGate()
    cell = GridCell(5, 0)
    snapshot = gate.observe_candidate(
        candidate=candidate(11, cell),
        evidence=tile(cell, category=TileClass.DANGER, confidence=0.97),
        metrics=STRONG,
        player_cell=GridCell(0, 0),
        now=0.0,
    )
    assert snapshot.entity_state is EntityState.DANGER_CANDIDATE
    assert not snapshot.visual_lock
    assert not snapshot.combat_lock


def test_two_persistent_frames_create_only_passive_visual_lock() -> None:
    gate = PR26HostilityGate()
    cell = GridCell(5, 0)
    danger = tile(cell, category=TileClass.DANGER, confidence=0.97)
    gate.observe_candidate(
        candidate=candidate(12, cell),
        evidence=danger,
        metrics=STRONG,
        player_cell=GridCell(0, 0),
        now=0.0,
    )
    snapshot = gate.observe_candidate(
        candidate=candidate(12, cell),
        evidence=danger,
        metrics=STRONG,
        player_cell=GridCell(0, 0),
        now=0.5,
    )
    assert snapshot.entity_state is EntityState.ENTITY_CONFIRMED
    assert snapshot.hostility_state is HostilityState.OBSERVE_HOSTILITY
    assert snapshot.visual_lock
    assert not snapshot.combat_lock
    assert snapshot.distance_history == (5,)


def test_three_distance_reductions_are_probable_but_not_combat_lock() -> None:
    gate = PR26HostilityGate()
    player = GridCell(0, 0)
    snapshots = []
    for index, distance in enumerate((5, 4, 3, 2)):
        cell = GridCell(distance, 0)
        snapshots.append(
            gate.observe_candidate(
                candidate=candidate(13, cell),
                evidence=tile(cell, category=TileClass.DANGER, confidence=0.97),
                metrics=STRONG,
                player_cell=player,
                now=float(index) * 0.5,
            )
        )
    final = snapshots[-1]
    assert final.hostility_state is HostilityState.HOSTILE_PROBABLE
    assert final.approach_votes == 3
    assert final.visual_lock
    assert not final.combat_lock


def test_reaching_d1_after_approach_confirms_combat_lock() -> None:
    gate = PR26HostilityGate()
    player = GridCell(0, 0)
    final = None
    for index, distance in enumerate((5, 4, 3, 2, 1)):
        cell = GridCell(distance, 0)
        final = gate.observe_candidate(
            candidate=candidate(14, cell),
            evidence=tile(cell, category=TileClass.DANGER, confidence=0.97),
            metrics=STRONG,
            player_cell=player,
            now=float(index) * 0.5,
        )
    assert final is not None
    assert final.hostility_state is HostilityState.HOSTILE_CONFIRMED
    assert final.combat_lock
    assert final.distance_history[-1] == 1


def test_reaching_d0_confirms_hostility() -> None:
    gate = PR26HostilityGate()
    player = GridCell(0, 0)
    for index, distance in enumerate((2, 1, 0)):
        cell = GridCell(distance, 0)
        snapshot = gate.observe_candidate(
            candidate=candidate(15, cell),
            evidence=tile(cell, category=TileClass.DANGER, confidence=0.97),
            metrics=STRONG,
            player_cell=player,
            now=float(index) * 0.5,
        )
    assert snapshot.hostility_state is HostilityState.HOSTILE_CONFIRMED
    assert snapshot.combat_lock


def test_stationary_similar_npc_becomes_non_aggressive() -> None:
    gate = PR26HostilityGate()
    player = GridCell(0, 0)
    cell = GridCell(4, 0)
    danger = tile(cell, category=TileClass.DANGER, confidence=0.94)
    for now in (0.0, 0.5, 3.2):
        snapshot = gate.observe_candidate(
            candidate=candidate(16, cell),
            evidence=danger,
            metrics=STRONG,
            player_cell=player,
            now=now,
        )
    assert snapshot.entity_state is EntityState.ENTITY_CONFIRMED
    assert snapshot.hostility_state is HostilityState.NON_AGGRESSIVE_ENTITY
    assert snapshot.visual_lock
    assert not snapshot.combat_lock


def test_negative_synthetic_track_has_zero_offensive_authority() -> None:
    gate = PR26HostilityGate()
    cell = GridCell(-3, 0)
    snapshot = gate.observe_candidate(
        candidate=candidate(-1_000_007, cell),
        evidence=tile(cell, category=TileClass.DANGER, confidence=0.99),
        metrics=STRONG,
        player_cell=GridCell(0, 0),
        now=0.0,
    )
    assert not snapshot.visual_lock
    assert not snapshot.combat_lock
    assert snapshot.entity_state is EntityState.TERRAIN_ONLY
    assert "synthetic" in snapshot.reason


def test_visual_lock_and_combat_lock_are_distinct_contracts() -> None:
    gate = PR26HostilityGate()
    cell = GridCell(3, 0)
    danger = tile(cell, category=TileClass.DANGER, confidence=0.97)
    gate.observe_candidate(
        candidate=candidate(17, cell),
        evidence=danger,
        metrics=STRONG,
        player_cell=GridCell(0, 0),
        now=0.0,
    )
    passive = gate.observe_candidate(
        candidate=candidate(17, cell),
        evidence=danger,
        metrics=STRONG,
        player_cell=GridCell(0, 0),
        now=0.5,
    )
    assert passive.visual_lock
    assert not passive.combat_lock
    assert passive.as_log_fields()["visual_lock"] is True
    assert passive.as_log_fields()["combat_lock"] is False
