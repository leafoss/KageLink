from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..combat_strategy_v351 import (
    AttackVisualContext,
    CombatStrategyFrame,
    GridObservation,
    ObservationClass,
)


Cell = tuple[int, int]


@dataclass(frozen=True, slots=True)
class CombatLabScenario:
    name: str
    frames: tuple[CombatStrategyFrame, ...]
    valid_enemy_track_ids: frozenset[int]
    expect_target: bool = True
    expected_final_cell: Cell | None = None
    expected_final_direction: str | None = None
    require_post_ko_disabled: bool = False
    description: str = ""


def observation(
    frame_index: int,
    track_id: int,
    cell: Cell,
    *,
    timestamp: float | None = None,
    visible: bool = True,
    body_like: bool = True,
    contaminated: bool = False,
    score: float = 82.0,
    appearance: tuple[float, ...] = (0.8, 0.2, 0.1),
    size: tuple[float, float] = (0.45, 0.90),
    classification: str = ObservationClass.CLEAN_SINGLE_CELL_BODY.value,
    bbox_cells: Iterable[Cell] | None = None,
    base_selected: bool = True,
    motion_burst: bool = False,
) -> GridObservation:
    cells = frozenset(bbox_cells or {cell})
    return GridObservation(
        frame_index=frame_index,
        timestamp=float(frame_index * 0.10 if timestamp is None else timestamp),
        track_id=track_id,
        anchor_cell=cell,
        bbox_cells=cells,
        visible=visible,
        body_like=body_like,
        contaminated=contaminated,
        enemy_score=score,
        appearance_signature=appearance,
        body_size=size,
        body_cell_coverage=0.82 if len(cells) == 1 else 0.42,
        classification=classification,
        context_state="VISIBLE" if visible else "OCCLUDED",
        anchor_point=(float(cell[0]), float(cell[1])),
        base_selected=base_selected,
        motion_burst=motion_burst,
    )


def frame(
    index: int,
    player: Cell,
    *items: GridObservation,
    timestamp: float | None = None,
    attack: AttackVisualContext | None = None,
    camera_shift: Cell = (0, 0),
    motion_burst: bool = False,
    ko: bool = False,
) -> CombatStrategyFrame:
    return CombatStrategyFrame(
        frame_index=index,
        timestamp=float(index * 0.10 if timestamp is None else timestamp),
        player_cell=player,
        observations=tuple(items),
        attack_context=attack,
        camera_shift=camera_shift,
        motion_burst=motion_burst,
        ko=ko,
    )


def _stable(name: str, enemy: Cell, direction: str) -> CombatLabScenario:
    return CombatLabScenario(
        name=name,
        frames=(
            frame(0, (0, 0), observation(0, 10, enemy)),
            frame(1, (0, 0), observation(1, 10, enemy)),
            frame(2, (0, 0), observation(2, 10, enemy)),
        ),
        valid_enemy_track_ids=frozenset({10}),
        expected_final_cell=enemy,
        expected_final_direction=direction,
        description=f"clean enemy remains {name.replace('_', ' ')}",
    )


def all_scenarios() -> tuple[CombatLabScenario, ...]:
    scenarios: list[CombatLabScenario] = [
        _stable("enemy_right", (1, 0), "RIGHT"),
        _stable("enemy_left", (-1, 0), "LEFT"),
        _stable("enemy_up", (0, -1), "UP"),
        _stable("enemy_down", (0, 1), "DOWN"),
        _stable("enemy_diagonal_up_left", (-1, -1), "LEFT"),
        _stable("enemy_diagonal_up_right", (1, -1), "RIGHT"),
        _stable("enemy_diagonal_down_left", (-1, 1), "LEFT"),
        _stable("enemy_diagonal_down_right", (1, 1), "RIGHT"),
    ]

    scenarios.extend(
        [
            CombatLabScenario(
                name="enemy_stationary",
                frames=tuple(
                    frame(i, (0, 0), observation(i, 20, (2, 0))) for i in range(6)
                ),
                valid_enemy_track_ids=frozenset({20}),
                expected_final_cell=(2, 0),
                expected_final_direction="RIGHT",
            ),
            CombatLabScenario(
                name="enemy_crosses_player",
                frames=(
                    frame(0, (0, 0), observation(0, 21, (-1, 0))),
                    frame(1, (0, 0), observation(1, 21, (-1, 0))),
                    frame(2, (0, 0), observation(2, 21, (0, 0))),
                    frame(3, (0, 0), observation(3, 21, (1, 0))),
                    frame(4, (0, 0), observation(4, 21, (1, 0))),
                ),
                valid_enemy_track_ids=frozenset({21}),
                expected_final_cell=(1, 0),
                expected_final_direction="RIGHT",
            ),
            CombatLabScenario(
                name="enemy_overlaps_player",
                frames=(
                    frame(0, (0, 0), observation(0, 22, (0, 0))),
                    frame(1, (0, 0), observation(1, 22, (0, 0))),
                    frame(2, (0, 0), observation(2, 22, (0, 0))),
                ),
                valid_enemy_track_ids=frozenset({22}),
                expected_final_cell=(0, 0),
            ),
            CombatLabScenario(
                name="enemy_missing_three_frames",
                frames=(
                    frame(0, (0, 0), observation(0, 23, (1, 0))),
                    frame(1, (0, 0), observation(1, 23, (1, 0))),
                    frame(2, (0, 0)),
                    frame(3, (0, 0)),
                    frame(4, (0, 0)),
                    frame(5, (0, 0), observation(5, 23, (1, 0))),
                    frame(6, (0, 0), observation(6, 23, (1, 0))),
                ),
                valid_enemy_track_ids=frozenset({23}),
                expected_final_cell=(1, 0),
            ),
            CombatLabScenario(
                name="enemy_missing_ten_frames",
                frames=(
                    frame(0, (0, 0), observation(0, 24, (1, 0))),
                    frame(1, (0, 0), observation(1, 24, (1, 0))),
                    *tuple(frame(i, (0, 0)) for i in range(2, 12)),
                    frame(12, (0, 0), observation(12, 24, (1, 0))),
                    frame(13, (0, 0), observation(13, 24, (1, 0))),
                ),
                valid_enemy_track_ids=frozenset({24}),
                expected_final_cell=(1, 0),
            ),
            CombatLabScenario(
                name="horizontal_effect_covers_player_and_enemy",
                frames=(
                    frame(0, (0, 0), observation(0, 25, (1, 0))),
                    frame(1, (0, 0), observation(1, 25, (1, 0))),
                    frame(
                        2,
                        (0, 0),
                        observation(
                            2,
                            90,
                            (0, 0),
                            body_like=False,
                            contaminated=True,
                            score=99.0,
                            classification=ObservationClass.MULTI_CELL_EFFECT.value,
                            bbox_cells={(-1, 0), (0, 0), (1, 0), (2, 0)},
                        ),
                    ),
                    frame(3, (0, 0), observation(3, 25, (1, 0))),
                ),
                valid_enemy_track_ids=frozenset({25}),
                expected_final_cell=(1, 0),
            ),
            CombatLabScenario(
                name="large_blob_three_cells",
                frames=(
                    frame(
                        0,
                        (0, 0),
                        observation(
                            0,
                            91,
                            (1, 0),
                            body_like=False,
                            contaminated=True,
                            score=99.0,
                            classification=ObservationClass.MULTI_CELL_EFFECT.value,
                            bbox_cells={(0, 0), (1, 0), (2, 0)},
                        ),
                    ),
                    frame(
                        1,
                        (0, 0),
                        observation(
                            1,
                            91,
                            (1, 0),
                            body_like=False,
                            contaminated=True,
                            score=99.0,
                            classification=ObservationClass.MULTI_CELL_EFFECT.value,
                            bbox_cells={(0, 0), (1, 0), (2, 0)},
                        ),
                    ),
                ),
                valid_enemy_track_ids=frozenset(),
                expect_target=False,
            ),
            CombatLabScenario(
                name="false_blob_next_to_player",
                frames=(
                    frame(
                        0,
                        (0, 0),
                        observation(
                            0,
                            92,
                            (1, 0),
                            body_like=False,
                            contaminated=True,
                            score=99.0,
                            classification=ObservationClass.UNKNOWN_BLOB.value,
                        ),
                    ),
                    frame(1, (0, 0), observation(1, 26, (2, 0), score=80.0)),
                    frame(2, (0, 0), observation(2, 26, (2, 0), score=80.0)),
                ),
                valid_enemy_track_ids=frozenset({26}),
                expected_final_cell=(2, 0),
            ),
            CombatLabScenario(
                name="false_blob_at_previous_enemy_cell",
                frames=(
                    frame(0, (0, 0), observation(0, 27, (1, 0))),
                    frame(1, (0, 0), observation(1, 27, (1, 0))),
                    frame(
                        2,
                        (0, 0),
                        observation(
                            2,
                            93,
                            (1, 0),
                            body_like=False,
                            contaminated=True,
                            score=99.0,
                            classification=ObservationClass.TARGET_EFFECT_CONTAMINATED.value,
                        ),
                    ),
                    frame(3, (0, 0), observation(3, 27, (1, 0))),
                ),
                valid_enemy_track_ids=frozenset({27}),
                expected_final_cell=(1, 0),
            ),
            CombatLabScenario(
                name="track_id_changes_same_cell",
                frames=(
                    frame(0, (0, 0), observation(0, 28, (1, 0))),
                    frame(1, (0, 0), observation(1, 28, (1, 0))),
                    frame(2, (0, 0), observation(2, 29, (1, 0))),
                    frame(3, (0, 0), observation(3, 30, (1, 0))),
                ),
                valid_enemy_track_ids=frozenset({28, 29, 30}),
                expected_final_cell=(1, 0),
            ),
            CombatLabScenario(
                name="track_id_changes_impossible_cell",
                frames=(
                    frame(0, (0, 0), observation(0, 31, (1, 0))),
                    frame(1, (0, 0), observation(1, 31, (1, 0))),
                    frame(2, (0, 0), observation(2, 94, (5, 4), score=99.0)),
                    frame(3, (0, 0), observation(3, 31, (1, 0))),
                ),
                valid_enemy_track_ids=frozenset({31}),
                expected_final_cell=(1, 0),
            ),
            CombatLabScenario(
                name="two_candidates_same_region",
                frames=(
                    frame(
                        0,
                        (0, 0),
                        observation(0, 32, (1, 0), score=82.0),
                        observation(0, 33, (1, 0), score=78.0, base_selected=False),
                    ),
                    frame(
                        1,
                        (0, 0),
                        observation(1, 32, (1, 0), score=82.0),
                        observation(1, 33, (1, 0), score=78.0, base_selected=False),
                    ),
                ),
                valid_enemy_track_ids=frozenset({32, 33}),
                expected_final_cell=(1, 0),
            ),
            CombatLabScenario(
                name="camera_shift",
                frames=(
                    frame(0, (0, 0), observation(0, 34, (2, 0))),
                    frame(1, (0, 0), observation(1, 34, (2, 0))),
                    frame(2, (0, 0), observation(2, 34, (2, 0)), camera_shift=(1, 0)),
                    frame(3, (0, 0), observation(3, 34, (2, 0)), camera_shift=(1, 0)),
                ),
                valid_enemy_track_ids=frozenset({34}),
                expected_final_cell=(2, 0),
            ),
            CombatLabScenario(
                name="player_knockback",
                frames=(
                    frame(0, (0, 0), observation(0, 35, (1, 0))),
                    frame(1, (0, 0), observation(1, 35, (1, 0))),
                    frame(2, (-1, 0), observation(2, 35, (1, 0))),
                    frame(3, (-1, 0), observation(3, 35, (1, 0))),
                ),
                valid_enemy_track_ids=frozenset({35}),
                expected_final_cell=(1, 0),
                expected_final_direction="RIGHT",
            ),
            CombatLabScenario(
                name="ko_ends_round",
                frames=(
                    frame(0, (0, 0), observation(0, 36, (1, 0))),
                    frame(1, (0, 0), observation(1, 36, (1, 0))),
                    frame(2, (0, 0), ko=True),
                ),
                valid_enemy_track_ids=frozenset({36}),
                expect_target=False,
                require_post_ko_disabled=True,
            ),
            CombatLabScenario(
                name="new_blob_after_ko",
                frames=(
                    frame(0, (0, 0), observation(0, 37, (1, 0))),
                    frame(1, (0, 0), observation(1, 37, (1, 0))),
                    frame(2, (0, 0), ko=True),
                    frame(3, (0, 0), observation(3, 95, (1, 0), score=99.0)),
                    frame(4, (0, 0), observation(4, 95, (1, 0), score=99.0)),
                ),
                valid_enemy_track_ids=frozenset({37}),
                expect_target=False,
                require_post_ko_disabled=True,
            ),
            CombatLabScenario(
                name="second_enemy_after_real_first_loss",
                frames=(
                    frame(0, (0, 0), observation(0, 38, (1, 0))),
                    frame(1, (0, 0), observation(1, 38, (1, 0))),
                    frame(2, (0, 0), timestamp=0.5),
                    frame(3, (0, 0), timestamp=1.5),
                    frame(4, (0, 0), timestamp=3.2),
                    frame(5, (0, 0), observation(5, 39, (-2, 0), timestamp=3.3)),
                    frame(6, (0, 0), observation(6, 39, (-2, 0), timestamp=3.4)),
                ),
                valid_enemy_track_ids=frozenset({38, 39}),
                expected_final_cell=(-2, 0),
                expected_final_direction="LEFT",
            ),
        ]
    )
    return tuple(scenarios)


__all__ = ["CombatLabScenario", "all_scenarios", "frame", "observation"]
