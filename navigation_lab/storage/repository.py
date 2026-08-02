from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..mapping import OccupancyGrid, WorldGraph
from ..simulator import SimulationResult


def default_data_root() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
        return base / "KageNavigationLab"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "kage-navigation-lab"


class JsonRepository:
    def __init__(self, root: Path | None = None, profile: str = "default") -> None:
        self.root = (root or default_data_root()) / "profiles" / profile
        self.root.mkdir(parents=True, exist_ok=True)

    def save_grid(self, region_id: str, grid: OccupancyGrid) -> Path:
        path = self.root / "regions" / f"{region_id}.json"
        _atomic_json_write(path, grid.to_dict())
        return path

    def load_grid(self, region_id: str) -> OccupancyGrid:
        path = self.root / "regions" / f"{region_id}.json"
        return OccupancyGrid.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save_mapping_state(self, region_id: str, payload: dict[str, Any]) -> Path:
        path = self.mapping_state_path(region_id)
        _atomic_json_write(path, payload)
        return path

    def load_mapping_state(self, region_id: str) -> dict[str, Any]:
        return json.loads(self.mapping_state_path(region_id).read_text(encoding="utf-8"))

    def mapping_state_path(self, region_id: str) -> Path:
        safe_region_id = self._safe_name(region_id)
        return self.root / "mappings" / f"{safe_region_id}.json"

    def has_mapping_state(self, region_id: str) -> bool:
        return self.mapping_state_path(region_id).is_file()

    def save_continuous_mapping(self, region_id: str, payload: dict[str, Any]) -> Path:
        path = self.continuous_mapping_path(region_id)
        _atomic_json_write(path, payload)
        return path

    def load_continuous_mapping(self, region_id: str) -> dict[str, Any]:
        return json.loads(self.continuous_mapping_path(region_id).read_text(encoding="utf-8"))

    def continuous_mapping_path(self, region_id: str) -> Path:
        return self.root / "continuous_mappings" / f"{self._safe_name(region_id)}.json"

    def has_continuous_mapping(self, region_id: str) -> bool:
        return self.continuous_mapping_path(region_id).is_file()

    def save_grid_calibration(self, region_id: str, payload: dict[str, Any]) -> Path:
        path = self.grid_calibration_path(region_id)
        _atomic_json_write(path, payload)
        return path

    def load_grid_calibration(self, region_id: str) -> dict[str, Any]:
        return json.loads(self.grid_calibration_path(region_id).read_text(encoding="utf-8"))

    def grid_calibration_path(self, region_id: str) -> Path:
        return self.root / "calibrations" / f"{self._safe_name(region_id)}_grid.json"

    def has_grid_calibration(self, region_id: str) -> bool:
        return self.grid_calibration_path(region_id).is_file()

    def save_tile_knowledge(self, region_id: str, payload: dict[str, Any]) -> Path:
        path = self.tile_knowledge_path(region_id)
        _atomic_json_write(path, payload)
        return path

    def load_tile_knowledge(self, region_id: str) -> dict[str, Any]:
        return json.loads(self.tile_knowledge_path(region_id).read_text(encoding="utf-8"))

    def tile_knowledge_path(self, region_id: str) -> Path:
        return self.root / "tile_knowledge" / f"{self._safe_name(region_id)}.json"

    def has_tile_knowledge(self, region_id: str) -> bool:
        return self.tile_knowledge_path(region_id).is_file()

    def save_tile_example_crop(self, region_id: str, example_id: str, crop: Any) -> Path:
        directory = self.root / "tile_knowledge" / self._safe_name(region_id) / "examples"
        return self._save_crop(directory, example_id, crop)

    def save_unknown_group_crop(self, region_id: str, group_id: str, crop: Any) -> Path:
        directory = self.root / "continuous_mappings" / self._safe_name(region_id) / "unknown_groups"
        return self._save_crop(directory, group_id, crop)

    def save_world(self, graph: WorldGraph) -> Path:
        path = self.root / "world_graph.json"
        _atomic_json_write(path, graph.to_dict())
        return path

    def load_world(self) -> WorldGraph:
        path = self.root / "world_graph.json"
        return WorldGraph.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save_simulation(self, result: SimulationResult) -> Path:
        path = self.root / "sessions" / f"{result.scenario_id}.json"
        payload: dict[str, Any] = {
            "scenario_id": result.scenario_id,
            "outcome": result.outcome,
            "steps": result.steps,
            "recoveries": result.recoveries,
            "replans": result.replans,
            "message": result.message,
            "snapshots": [
                {
                    "step": item.step,
                    "pose": item.pose.as_dict(),
                    "actual_position": asdict(item.actual_position),
                    "goal": asdict(item.goal),
                    "path": [asdict(point) for point in item.path],
                    "decision": item.decision.as_dict(),
                    "state": item.state.value,
                    "events": item.events,
                    "arrived": item.arrived,
                    "aborted": item.aborted,
                    "recoveries": item.recoveries,
                }
                for item in result.snapshots
            ],
        }
        _atomic_json_write(path, payload)
        return path

    def _save_crop(self, directory: Path, identifier: str, crop: Any) -> Path:
        import cv2

        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self._safe_name(identifier)}.png"
        if crop is None or not hasattr(crop, "shape") or crop.size == 0:
            raise ValueError("crop must be a non-empty image")
        if not cv2.imwrite(str(path), crop):
            raise OSError(f"Failed to write crop: {path}")
        return path

    @staticmethod
    def _safe_name(value: str) -> str:
        return "".join(character if character.isalnum() or character in "-_" else "_" for character in value)


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
