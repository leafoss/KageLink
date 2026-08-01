from __future__ import annotations

from .scenarios import (
    CombatLabScenario,
    all_scenarios as legacy_all_scenarios,
    frame,
    observation,
)
from ..combat_strategy_v351 import ObservationClass


def _contaminated(
    index: int,
    track_id: int,
    cell: tuple[int, int],
    *,
    visible: bool = True,
    base_selected: bool = True,
    score: float = 88.0,
):
    return observation(
        index,
        track_id,
        cell,
        visible=visible,
        body_like=False,
        contaminated=True,
        score=score,
        appearance=(),
        classification=ObservationClass.UNKNOWN_BLOB.value,
        base_selected=base_selected,
    )


def incremental_scenarios() -> tuple[CombatLabScenario, ...]:
    return (
        CombatLabScenario(
            name="visible_tracker_without_combat_lock",
            frames=(
                frame(0, (0, 0), _contaminated(0, 112, (1, 0))),
                frame(1, (0, 0), observation(1, 112, (1, 0))),
                frame(2, (0, 0), observation(2, 112, (1, 0))),
                frame(3, (0, 0), _contaminated(3, 112, (1, 0), visible=False)),
                frame(4, (0, 0), observation(4, 112, (1, 0))),
            ),
            valid_enemy_track_ids=frozenset({112}),
            expected_final_cell=(1, 0),
            expected_final_direction="RIGHT",
            description=(
                "visual tracker survives initial body-gate rejection, enters ATTENTION, "
                "locks after two clean observations and preserves identity through contact"
            ),
        ),
        CombatLabScenario(
            name="rejected_primary_valid_secondary",
            frames=(
                frame(
                    0,
                    (0, 0),
                    _contaminated(0, 190, (0, 0), base_selected=True, score=99.0),
                    observation(0, 113, (1, 0), base_selected=False),
                ),
                frame(
                    1,
                    (0, 0),
                    _contaminated(1, 190, (0, 0), base_selected=True, score=99.0),
                    observation(1, 113, (1, 0), base_selected=False),
                ),
            ),
            valid_enemy_track_ids=frozenset({113}),
            expected_final_cell=(1, 0),
            description="a rejected state.target cannot monopolize acquisition",
        ),
        CombatLabScenario(
            name="player_only_d0",
            frames=tuple(
                frame(index, (0, 0), observation(index, 1, (0, 0)))
                for index in range(8)
            ),
            valid_enemy_track_ids=frozenset(),
            expect_target=False,
            description="player/shadow-only d=0 evidence never creates a Combat Target",
        ),
        CombatLabScenario(
            name="confirmed_enemy_d0_overlap",
            frames=(
                frame(0, (0, 0), observation(0, 114, (1, 0))),
                frame(1, (0, 0), observation(1, 114, (1, 0))),
                frame(2, (0, 0), _contaminated(2, 114, (0, 0), visible=False)),
                frame(3, (0, 0), _contaminated(3, 114, (0, 0), visible=False)),
                frame(4, (0, 0), observation(4, 114, (1, 0))),
            ),
            valid_enemy_track_ids=frozenset({114}),
            expected_final_cell=(1, 0),
            expected_final_direction="RIGHT",
            description="confirmed enemy overlap preserves identity but has no MOVE/H authority",
        ),
        CombatLabScenario(
            name="false_blob_near_player_far_from_prediction",
            frames=(
                frame(0, (0, 0), observation(0, 115, (2, 0))),
                frame(1, (0, 0), observation(1, 115, (2, 0))),
                frame(2, (0, 0), observation(2, 191, (-1, 0), score=99.0)),
                frame(3, (0, 0), observation(3, 191, (-1, 0), score=99.0)),
                frame(4, (0, 0), observation(4, 115, (2, 0))),
            ),
            valid_enemy_track_ids=frozenset({115}),
            expected_final_cell=(2, 0),
            expected_final_direction="RIGHT",
            description="player proximity cannot replace a target outside the spatial hypothesis",
        ),
        CombatLabScenario(
            name="same_track_short_occlusion",
            frames=(
                frame(0, (0, 0), observation(0, 116, (1, 0))),
                frame(1, (0, 0), observation(1, 116, (1, 0))),
                frame(2, (0, 0), _contaminated(2, 116, (1, 0), visible=False)),
                frame(3, (0, 0), _contaminated(3, 116, (1, 0), visible=False)),
                frame(4, (0, 0), _contaminated(4, 116, (1, 0), visible=False)),
                frame(5, (0, 0), observation(5, 116, (1, 0))),
            ),
            valid_enemy_track_ids=frozenset({116}),
            expected_final_cell=(1, 0),
            expected_final_direction="RIGHT",
            description="same visual tracker retains one logical identity through melee occlusion",
        ),
        CombatLabScenario(
            name="same_track_impossible_cell_jump",
            frames=(
                frame(0, (0, 0), observation(0, 117, (1, 0))),
                frame(1, (0, 0), observation(1, 117, (1, 0))),
                frame(2, (0, 0), observation(2, 117, (6, 4), score=99.0)),
                frame(3, (0, 0), observation(3, 117, (6, 4), score=99.0)),
                frame(4, (0, 0), observation(4, 117, (1, 0))),
            ),
            valid_enemy_track_ids=frozenset({117}),
            expected_final_cell=(1, 0),
            expected_final_direction="RIGHT",
            description="same track ID cannot teleport the confirmed cell",
        ),
        CombatLabScenario(
            name="missing_appearance_evidence",
            frames=(
                frame(0, (0, 0), observation(0, 118, (1, 0), appearance=())),
                frame(1, (0, 0), observation(1, 118, (1, 0), appearance=())),
                frame(2, (0, 0), observation(2, 119, (1, 0), appearance=())),
                frame(3, (0, 0), observation(3, 119, (1, 0), appearance=())),
            ),
            valid_enemy_track_ids=frozenset({118, 119}),
            expected_final_cell=(1, 0),
            description="missing appearance contributes zero and remaining evidence is renormalized",
        ),
        CombatLabScenario(
            name="incident_20260731_lock_starvation_approximation",
            frames=(
                frame(0, (0, 0), _contaminated(0, 120, (0, 0))),
                frame(1, (0, 0), _contaminated(1, 120, (1, 0))),
                frame(2, (0, 0), _contaminated(2, 120, (1, 0))),
                frame(3, (0, 0), _contaminated(3, 120, (0, 0))),
                frame(4, (0, 0), observation(4, 120, (1, 0))),
                frame(5, (0, 0), observation(5, 120, (1, 0))),
                frame(6, (0, 0), _contaminated(6, 120, (1, 0), visible=False)),
                frame(7, (0, 0), _contaminated(7, 120, (0, 0), visible=False)),
                frame(8, (0, 0), _contaminated(8, 120, (1, 0), visible=False)),
                frame(9, (0, 0), observation(9, 120, (1, 0))),
            ),
            valid_enemy_track_ids=frozenset({120}),
            expected_final_cell=(1, 0),
            expected_final_direction="RIGHT",
            description=(
                "approximation reconstructed from the processed AVI/overlay summary; "
                "not a literal RAW replay"
            ),
        ),
    )


def all_scenarios() -> tuple[CombatLabScenario, ...]:
    original = [
        scenario
        for scenario in legacy_all_scenarios()
        if scenario.name != "enemy_overlaps_player"
    ]
    return tuple(original) + incremental_scenarios()


__all__ = ["CombatLabScenario", "all_scenarios", "incremental_scenarios"]
