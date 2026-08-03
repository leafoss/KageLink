from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import cv2
import numpy as np

from .pr27_model import (
    CELL_SIZE_PX, ArenaRect, CellBaseline, CellDifference, CellSearchGroup,
    CellState, ComponentEvidence, GridCell, LocalBackgroundState, PR27Config,
)


class ArenaCropper:
    def __init__(self, rect: ArenaRect | None = None, *, left_ratio=.04, top_ratio=.04, right_ratio=.96, bottom_ratio=.86) -> None:
        self.rect = rect
        self.ratios = (left_ratio, top_ratio, right_ratio, bottom_ratio)

    def resolve(self, frame: np.ndarray) -> ArenaRect:
        if self.rect is not None:
            return self.rect.clamp(frame.shape)
        h, w = frame.shape[:2]
        l, t, r, b = self.ratios
        x, y, x2, y2 = round(w*l), round(h*t), round(w*r), round(h*b)
        return ArenaRect(x, y, max(1, x2-x), max(1, y2-y)).clamp(frame.shape)

    def crop(self, frame: np.ndarray) -> tuple[ArenaRect, np.ndarray]:
        rect = self.resolve(frame)
        return rect, frame[rect.y:rect.y+rect.height, rect.x:rect.x+rect.width]


class NativeGrid64:
    """World grid retained only for loading the pre-fight reference image."""

    def __init__(self, cell_size_px=CELL_SIZE_PX, *, phase_x=0, phase_y=0) -> None:
        if int(cell_size_px) != CELL_SIZE_PX:
            raise ValueError("PR27_GRID_MUST_BE_NATIVE_64PX")
        self.set_phase(phase_x, phase_y)

    @property
    def phase(self) -> tuple[int, int]:
        return self.phase_x, self.phase_y

    def set_phase(self, phase_x: int, phase_y: int) -> None:
        self.phase_x = int(phase_x) % CELL_SIZE_PX
        self.phase_y = int(phase_y) % CELL_SIZE_PX

    @staticmethod
    def phase_from_anchor(anchor: tuple[float, float], *, desired_local=(32, 56)) -> tuple[int, int]:
        return (
            round(int(desired_local[0]) % 64 - float(anchor[0])) % 64,
            round(int(desired_local[1]) % 64 - float(anchor[1])) % 64,
        )

    def build(self, shape: Sequence[int]) -> tuple[GridCell, ...]:
        h, w = int(shape[0]), int(shape[1])
        cells: list[GridCell] = []
        world_y, row = -self.phase_y, 0
        while world_y < h:
            y, y2 = max(0, world_y), min(h, world_y+64)
            if y2 > y:
                world_x, column = -self.phase_x, 0
                while world_x < w:
                    x, x2 = max(0, world_x), min(w, world_x+64)
                    if x2 > x:
                        cells.append(GridCell(row, column, x, y, x2-x, y2-y))
                    world_x, column = world_x+64, column+1
            world_y, row = world_y+64, row+1
        return tuple(cells)

    def cell_key_for_point(self, point, shape) -> tuple[int, int] | None:
        x, y = map(float, point)
        h, w = int(shape[0]), int(shape[1])
        if not (0 <= x < w and 0 <= y < h):
            return None
        return int((y+self.phase_y)//64), int((x+self.phase_x)//64)

    @staticmethod
    def cell_for_key(cells: Iterable[GridCell], key) -> GridCell | None:
        return next((cell for cell in cells if (cell.row, cell.column) == key), None) if key is not None else None


class PlayerCentricCombatGrid:
    """Circular native grid whose authoritative player cell is always (0, 0)."""

    def __init__(self, config: PR27Config) -> None:
        self.config = config.normalized()
        self.radius = self.config.roi_radius_cells
        self.offset_x = self.config.player_cell_anchor_offset_x
        self.offset_y = self.config.player_cell_anchor_offset_y
        self.center_anchor: tuple[float, float] | None = None

    @property
    def phase(self) -> tuple[int, int]:
        return self.offset_x, self.offset_y

    @staticmethod
    def _intersection_area(a, b) -> int:
        ax, ay, aw, ah = a; bx, by, bw, bh = b
        return max(0, min(ax+aw, bx+bw)-max(ax, bx)) * max(0, min(ay+ah, by+bh)-max(ay, by))

    def central_bbox(self, anchor=None) -> tuple[int, int, int, int]:
        anchor = anchor or self.center_anchor
        if anchor is None:
            raise RuntimeError("PR27_PLAYER_CENTRIC_GRID_CENTER_MISSING")
        return round(anchor[0]-self.offset_x), round(anchor[1]-self.offset_y), 64, 64

    def containment_ratio(self, body_bbox, anchor=None) -> float:
        if body_bbox is None or (anchor or self.center_anchor) is None:
            return 0.0
        return self._intersection_area(body_bbox, self.central_bbox(anchor)) / max(1, body_bbox[2]*body_bbox[3])

    def calibrate_to_body(self, body_bbox, anchor) -> float:
        current = (self.containment_ratio(body_bbox, anchor), self.offset_x, self.offset_y)
        desired_x, desired_y = self.config.player_cell_anchor_offset_x, self.config.player_cell_anchor_offset_y
        best = current
        for ox in range(max(16, desired_x-16), min(48, desired_x+16)+1):
            for oy in range(max(40, desired_y-20), min(64, desired_y+8)+1):
                cell = (round(anchor[0]-ox), round(anchor[1]-oy), 64, 64)
                ratio = self._intersection_area(body_bbox, cell) / max(1, body_bbox[2]*body_bbox[3])
                score = (ratio, -(abs(ox-self.offset_x)+abs(oy-self.offset_y)), -(abs(ox-desired_x)+abs(oy-desired_y)))
                old_score = (best[0], -(abs(best[1]-self.offset_x)+abs(best[2]-self.offset_y)), -(abs(best[1]-desired_x)+abs(best[2]-desired_y)))
                if score > old_score:
                    best = ratio, ox, oy
        if max(abs(best[1]-self.offset_x), abs(best[2]-self.offset_y)) > self.config.player_cell_hysteresis_px or best[0] < self.config.player_cell_min_containment:
            self.offset_x, self.offset_y = best[1], best[2]
        self.center_anchor = tuple(map(float, anchor))
        return self.containment_ratio(body_bbox, anchor)

    def update_center(self, anchor) -> None:
        candidate = tuple(map(float, anchor))
        if self.center_anchor is None or max(abs(candidate[0]-self.center_anchor[0]), abs(candidate[1]-self.center_anchor[1])) > self.config.player_cell_hysteresis_px:
            self.center_anchor = candidate

    def build(self, shape: Sequence[int], anchor=None) -> tuple[GridCell, ...]:
        if anchor is not None:
            self.update_center(anchor)
        left, top, _, _ = self.central_bbox()
        h, w = int(shape[0]), int(shape[1])
        cells: list[GridCell] = []
        for dy in range(-self.radius, self.radius+1):
            for dx in range(-self.radius, self.radius+1):
                if dx*dx + dy*dy > self.radius*self.radius:
                    continue
                rx, ry = left+dx*64, top+dy*64
                x, y, x2, y2 = max(0, rx), max(0, ry), min(w, rx+64), min(h, ry+64)
                if x2 > x and y2 > y:
                    cells.append(GridCell(dy, dx, x, y, x2-x, y2-y))
        return tuple(sorted(cells))

    @staticmethod
    def cell_for_key(cells, key):
        return next((cell for cell in cells if (cell.row, cell.column) == key), None) if key is not None else None

    @staticmethod
    def cell_key_for_point(point, cells) -> tuple[int, int] | None:
        return next(((cell.row, cell.column) for cell in cells if cell.contains(point)), None)

    def contains_relative_key(self, key) -> bool:
        return key is not None and key[0]*key[0] + key[1]*key[1] <= self.radius*self.radius


class CellBaselineStore:
    def __init__(self) -> None:
        self._baselines: dict[tuple[int, int], CellBaseline] = {}
        self.metadata: dict[str, object] = {}

    def __len__(self) -> int:
        return len(self._baselines)

    def get(self, cell: GridCell) -> CellBaseline | None:
        return self._baselines.get((cell.row, cell.column))

    def set(self, cell: GridCell, image: np.ndarray, *, stability_score=0.0) -> None:
        if image.shape[:2] != (cell.height, cell.width):
            raise ValueError(f"PR27_BASELINE_SHAPE_MISMATCH:{cell.cell_id}:{image.shape[:2]}")
        stored = np.ascontiguousarray(image.copy())
        self._baselines[(cell.row, cell.column)] = CellBaseline(
            cell, stored, np.ascontiguousarray(cv2.cvtColor(stored, cv2.COLOR_BGR2LAB)),
            time.time(), True, float(stability_score),
        )

    def invalidate_all(self) -> None:
        for baseline in self._baselines.values():
            baseline.valid = False

    def render_arena(self, shape: Sequence[int]) -> tuple[np.ndarray, np.ndarray]:
        h, w = int(shape[0]), int(shape[1])
        image = np.zeros((h, w, 3), np.uint8)
        valid = np.zeros((h, w), np.uint8)
        for baseline in self._baselines.values():
            cell = baseline.cell
            if not baseline.valid or cell.x >= w or cell.y >= h:
                continue
            x2, y2 = min(w, cell.x+cell.width), min(h, cell.y+cell.height)
            ch, cw = y2-cell.y, x2-cell.x
            image[cell.y:y2, cell.x:x2] = baseline.image[:ch, :cw]
            valid[cell.y:y2, cell.x:x2] = 255
        return image, valid

    @staticmethod
    def read_metadata(path: Path) -> dict[str, object]:
        if not path.is_file():
            raise RuntimeError(f"PR27_NATIVE_BASELINE_MISSING:{path}")
        with np.load(path, allow_pickle=False) as archive:
            try:
                return dict(json.loads(str(archive["metadata"].item()))) if "metadata" in archive.files else {}
            except Exception:
                return {}

    def load_npz(self, path: Path, cells: Iterable[GridCell]) -> int:
        if not path.is_file():
            raise RuntimeError(f"PR27_NATIVE_BASELINE_MISSING:{path}")
        by_key = {(c.row, c.column): c for c in cells}
        count = 0
        with np.load(path, allow_pickle=False) as archive:
            try:
                self.metadata = json.loads(str(archive["metadata"].item())) if "metadata" in archive.files else {}
            except Exception:
                self.metadata = {}
            for name in archive.files:
                if not name.startswith("cell_r"):
                    continue
                try:
                    row, col = name.removeprefix("cell_r").split("_c", 1)
                    cell = by_key.get((int(row), int(col)))
                except (TypeError, ValueError):
                    continue
                if cell is not None and archive[name].shape[:2] == (cell.height, cell.width):
                    self.set(cell, archive[name]); count += 1
        if count == 0:
            raise RuntimeError("PR27_NATIVE_BASELINE_EMPTY")
        return count

    def save_npz(self, path: Path, *, metadata: Mapping[str, object] | None = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {f"cell_r{r}_c{c}": b.image for (r, c), b in self._baselines.items() if b.valid}
        payload["metadata"] = np.asarray(json.dumps(dict(metadata or self.metadata)))
        np.savez_compressed(path, **payload)


class LocalBackgroundModel:
    """Incremental references keyed only by relative cells inside the combat ROI."""

    def __init__(self, config: PR27Config) -> None:
        self.config = config.normalized()
        self.baselines = CellBaselineStore()
        self.states: dict[tuple[int, int], LocalBackgroundState] = {}
        self.stable_counts: dict[tuple[int, int], int] = {}
        self.previous: dict[tuple[int, int], np.ndarray] = {}

    def sync_from_reference(self, reference, valid, current, cells) -> None:
        active = {(c.row, c.column) for c in cells}
        for key in tuple(self.states):
            if key not in active:
                self.states.pop(key, None); self.stable_counts.pop(key, None)
                self.previous.pop(key, None); self.baselines._baselines.pop(key, None)
        for cell in cells:
            key = cell.row, cell.column
            existing = self.baselines.get(cell)
            if existing is not None and existing.cell.bbox == cell.bbox:
                continue
            ref = reference[cell.y:cell.y+cell.height, cell.x:cell.x+cell.width]
            ok = valid[cell.y:cell.y+cell.height, cell.x:cell.x+cell.width]
            crop = current[cell.y:cell.y+cell.height, cell.x:cell.x+cell.width]
            if ref.shape[:2] == (cell.height, cell.width) and ok.size and np.all(ok):
                self.baselines.set(cell, ref); self.states[key] = LocalBackgroundState.KNOWN_BACKGROUND
            else:
                self.baselines.set(cell, crop); self.states[key] = LocalBackgroundState.LEARNING_BACKGROUND
            self.stable_counts[key] = 0
            self.previous[key] = crop.copy()

    def begin_learning(self, keys: set[tuple[int, int]]) -> None:
        for key in keys:
            if key in self.states:
                self.states[key] = LocalBackgroundState.LEARNING_BACKGROUND
                self.stable_counts[key] = 0

    def mark_occupancy(self, *, player_cells, enemy_cells, effect_cells) -> None:
        transient = {LocalBackgroundState.OCCLUDED_BY_EFFECT, LocalBackgroundState.OCCUPIED_BY_PLAYER, LocalBackgroundState.OCCUPIED_BY_ENEMY}
        for key in tuple(self.states):
            if key in effect_cells:
                self.states[key] = LocalBackgroundState.OCCLUDED_BY_EFFECT
            elif key in player_cells:
                self.states[key] = LocalBackgroundState.OCCUPIED_BY_PLAYER
            elif key in enemy_cells:
                self.states[key] = LocalBackgroundState.OCCUPIED_BY_ENEMY
            elif self.states[key] in transient:
                self.states[key] = LocalBackgroundState.KNOWN_BACKGROUND

    def learn(self, arena, cells, differences, *, protected_cells, effect_cells) -> None:
        for cell in cells:
            key = cell.row, cell.column
            crop = arena[cell.y:cell.y+cell.height, cell.x:cell.x+cell.width].copy()
            old = self.previous.get(key); self.previous[key] = crop
            if key in protected_cells or key in effect_cells:
                self.stable_counts[key] = 0; continue
            temporal = 0.0 if old is None else float(np.mean(np.abs(crop.astype(np.int16)-old.astype(np.int16))))/255.0
            if temporal > .010:
                self.stable_counts[key] = 0; continue
            self.stable_counts[key] = self.stable_counts.get(key, 0)+1
            if self.stable_counts[key] < self.config.local_background_learning_frames:
                if differences.get(key) is None or differences[key].state is CellState.BASELINE_INVALID:
                    self.states[key] = LocalBackgroundState.LEARNING_BACKGROUND
                continue
            baseline = self.baselines.get(cell)
            learning = self.states.get(key) in {LocalBackgroundState.UNKNOWN, LocalBackgroundState.LEARNING_BACKGROUND}
            if baseline is None or baseline.image.shape != crop.shape or learning:
                self.baselines.set(cell, crop)
            else:
                a = self.config.local_background_alpha
                self.baselines.set(cell, cv2.addWeighted(crop, a, baseline.image, 1-a, 0))
            self.states[key] = LocalBackgroundState.KNOWN_BACKGROUND

    @property
    def unknown_count(self) -> int:
        return sum(s in {LocalBackgroundState.UNKNOWN, LocalBackgroundState.LEARNING_BACKGROUND} for s in self.states.values())


class CellDifferenceDetector:
    def __init__(self, config: PR27Config) -> None:
        self.config = config.normalized()
        self.kernel = np.ones((self.config.morphology_kernel,)*2, np.uint8)

    def compare(self, arena, cells: Iterable[GridCell], baselines: CellBaselineStore):
        cells = tuple(cells)
        if not cells:
            return {}
        min_x, min_y = min(c.x for c in cells), min(c.y for c in cells)
        max_x, max_y = max(c.x+c.width for c in cells), max(c.y+c.height for c in cells)
        local_lab = cv2.cvtColor(arena[min_y:max_y, min_x:max_x], cv2.COLOR_BGR2LAB)
        result = {}
        for cell in cells:
            current = local_lab[cell.y-min_y:cell.y-min_y+cell.height, cell.x-min_x:cell.x-min_x+cell.width]
            baseline = baselines.get(cell)
            if baseline is None or not baseline.valid or baseline.lab_image.shape != current.shape:
                result[(cell.row, cell.column)] = CellDifference(cell, np.zeros((cell.height, cell.width), np.uint8), 0, 0.0, (), CellState.BASELINE_INVALID)
                continue
            magnitude = np.max(cv2.absdiff(current, baseline.lab_image), axis=2)
            mask = np.where(magnitude >= self.config.pixel_delta_threshold, 255, 0).astype(np.uint8)
            mask = cv2.morphologyEx(cv2.morphologyEx(mask, cv2.MORPH_OPEN, self.kernel), cv2.MORPH_CLOSE, self.kernel)
            count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
            cleaned, components = np.zeros_like(mask), []
            for label in range(1, count):
                x, y, w, h, area = map(int, stats[label])
                if area >= self.config.minimum_component_area:
                    cleaned[labels == label] = 255
                    components.append(ComponentEvidence((x, y, w, h), area))
            changed = int(np.count_nonzero(cleaned)); ratio = changed/max(1, cell.width*cell.height)
            state = CellState.CHANGED if ratio >= self.config.changed_ratio_threshold else CellState.UNCERTAIN if ratio >= self.config.uncertain_ratio_threshold else CellState.STABLE
            result[(cell.row, cell.column)] = CellDifference(cell, cleaned, changed, ratio, tuple(components), state)
        return result


class ChangedCellGrouper:
    def group(self, differences) -> tuple[CellSearchGroup, ...]:
        changed = {key: value.cell for key, value in differences.items() if value.state is CellState.CHANGED}
        unvisited, groups = set(changed), []
        while unvisited:
            queue, cells = [min(unvisited)], []; unvisited.remove(queue[0])
            while queue:
                key = queue.pop(); cells.append(changed[key]); row, col = key
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        neighbour = row+dr, col+dc
                        if (dr or dc) and neighbour in unvisited:
                            unvisited.remove(neighbour); queue.append(neighbour)
            groups.append(CellSearchGroup(len(groups)+1, tuple(sorted(cells))))
        return tuple(groups)
