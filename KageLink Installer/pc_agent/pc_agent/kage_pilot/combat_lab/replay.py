from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Iterable, Mapping

from ..combat_strategy_v351 import (
    AttackVisualContext,
    CombatStrategyConfig,
    CombatStrategyFrame,
    GridObservation,
    create_combat_target_strategy,
)


def observation_to_dict(value: GridObservation) -> dict[str, object]:
    result = asdict(value)
    result["anchor_cell"] = list(value.anchor_cell)
    result["bbox_cells"] = [list(cell) for cell in sorted(value.bbox_cells)]
    result["appearance_signature"] = list(value.appearance_signature)
    result["body_size"] = list(value.body_size)
    result["anchor_point"] = list(value.anchor_point) if value.anchor_point is not None else None
    return result


def observation_from_dict(value: Mapping[str, object]) -> GridObservation:
    return GridObservation(
        frame_index=int(value.get("frame_index", 0)),
        timestamp=float(value.get("timestamp", 0.0)),
        track_id=int(value.get("track_id", 0)),
        anchor_cell=tuple(int(item) for item in value.get("anchor_cell", (0, 0))),
        bbox_cells=frozenset(
            tuple(int(item) for item in cell)
            for cell in value.get("bbox_cells", ())
        ),
        visible=bool(value.get("visible", False)),
        body_like=bool(value.get("body_like", False)),
        contaminated=bool(value.get("contaminated", False)),
        enemy_score=float(value.get("enemy_score", 0.0)),
        appearance_signature=tuple(
            float(item) for item in value.get("appearance_signature", ())
        ),
        body_size=tuple(float(item) for item in value.get("body_size", (1.0, 1.0))),
        body_cell_coverage=float(value.get("body_cell_coverage", 0.0)),
        classification=str(value.get("classification", "UNKNOWN_BLOB")),
        context_state=str(value.get("context_state", "LOST")),
        anchor_point=(
            tuple(float(item) for item in value.get("anchor_point", (0.0, 0.0)))
            if value.get("anchor_point") is not None
            else None
        ),
        base_selected=bool(value.get("base_selected", False)),
        motion_burst=bool(value.get("motion_burst", False)),
    )


def frame_to_dict(value: CombatStrategyFrame) -> dict[str, object]:
    context = value.attack_context
    return {
        "frame_index": value.frame_index,
        "timestamp": value.timestamp,
        "player_cell": list(value.player_cell),
        "observations": [observation_to_dict(item) for item in value.observations],
        "attack_context": (
            {
                "attack_id": context.attack_id,
                "started_at": context.started_at,
                "origin_cell": list(context.origin_cell),
                "direction": context.direction,
                "expected_cells": [list(cell) for cell in sorted(context.expected_cells)],
                "expires_at": context.expires_at,
            }
            if context is not None
            else None
        ),
        "camera_shift": list(value.camera_shift),
        "motion_burst": value.motion_burst,
        "ko": value.ko,
    }


def frame_from_dict(value: Mapping[str, object]) -> CombatStrategyFrame:
    context_value = value.get("attack_context")
    context = None
    if isinstance(context_value, Mapping):
        context = AttackVisualContext(
            attack_id=int(context_value.get("attack_id", 0)),
            started_at=float(context_value.get("started_at", 0.0)),
            origin_cell=tuple(
                int(item) for item in context_value.get("origin_cell", (0, 0))
            ),
            direction=str(context_value.get("direction", "-")),
            expected_cells=frozenset(
                tuple(int(item) for item in cell)
                for cell in context_value.get("expected_cells", ())
            ),
            expires_at=float(context_value.get("expires_at", 0.0)),
        )
    rows = value.get("observations", ())
    return CombatStrategyFrame(
        frame_index=int(value.get("frame_index", 0)),
        timestamp=float(value.get("timestamp", 0.0)),
        player_cell=tuple(int(item) for item in value.get("player_cell", (0, 0))),
        observations=tuple(
            observation_from_dict(item) for item in rows if isinstance(item, Mapping)
        ),
        attack_context=context,
        camera_shift=tuple(int(item) for item in value.get("camera_shift", (0, 0))),
        motion_burst=bool(value.get("motion_burst", False)),
        ko=bool(value.get("ko", False)),
    )


class CombatReplay:
    def __init__(self, frames: Iterable[CombatStrategyFrame]) -> None:
        self.frames = tuple(frames)

    @classmethod
    def read(cls, path: str | Path) -> "CombatReplay":
        source = Path(path)
        payload = json.loads(source.read_text(encoding="utf-8"))
        rows = payload.get("frames", payload) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise ValueError("COMBAT_REPLAY_FRAMES_INVALID")
        return cls(frame_from_dict(item) for item in rows if isinstance(item, Mapping))

    def write(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(
                {"version": 1, "frames": [frame_to_dict(item) for item in self.frames]},
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return destination

    def run(
        self,
        strategy_name: str,
        *,
        config: CombatStrategyConfig | None = None,
    ) -> tuple[dict[str, object], ...]:
        settings = config or CombatStrategyConfig(strategy=strategy_name)
        strategy = create_combat_target_strategy(strategy_name, settings)
        return tuple(asdict(strategy.update(frame)) for frame in self.frames)

    def assert_deterministic(
        self,
        strategy_name: str,
        *,
        repeats: int = 3,
        config: CombatStrategyConfig | None = None,
    ) -> tuple[dict[str, object], ...]:
        expected = self.run(strategy_name, config=config)
        for _ in range(max(2, int(repeats)) - 1):
            current = self.run(strategy_name, config=config)
            if current != expected:
                raise AssertionError(
                    f"NON_DETERMINISTIC_COMBAT_REPLAY strategy={strategy_name}"
                )
        return expected


__all__ = [
    "CombatReplay",
    "frame_from_dict",
    "frame_to_dict",
    "observation_from_dict",
    "observation_to_dict",
]
