from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Mapping

import cv2
import numpy as np

from .pr27_fixed_grid import FixedNativeGridCalibration


@dataclass(slots=True)
class CellNoiseProfile:
    ratios: deque[float] = field(default_factory=lambda: deque(maxlen=48))
    noise_mean: float = 0.0
    noise_std: float = 0.0
    noise_p90: float = 0.0
    noise_p95: float = 0.0
    noise_p99: float = 0.0
    change_frequency: float = 0.0
    animated_probability: float = 0.0

    def update(self, ratio: float, *, animated_hint: float = 0.0) -> None:
        value = float(max(0.0, min(1.0, ratio)))
        self.ratios.append(value)
        values = np.asarray(self.ratios, dtype=np.float32)
        self.noise_mean = float(np.mean(values)) if values.size else 0.0
        self.noise_std = float(np.std(values)) if values.size else 0.0
        if values.size:
            self.noise_p90 = float(np.percentile(values, 90))
            self.noise_p95 = float(np.percentile(values, 95))
            self.noise_p99 = float(np.percentile(values, 99))
            self.change_frequency = float(np.mean(values >= 0.03))
        else:
            self.noise_p90 = self.noise_p95 = self.noise_p99 = 0.0
            self.change_frequency = 0.0
        recurrence = min(1.0, self.change_frequency * 1.25)
        variability = min(1.0, self.noise_std / 0.12)
        self.animated_probability = float(
            max(0.0, min(1.0, 0.55 * recurrence + 0.25 * variability + 0.20 * animated_hint))
        )


@dataclass(frozen=True, slots=True)
class NoiseGateEvidence:
    relative_cell: tuple[int, int]
    raw_changed_ratio: float
    effective_threshold: float
    passed_new_candidate_gate: bool
    gate_override_reason: str | None
    noise_probability: float
    animated_probability: float
    raw_active_pixels: int
    gated_active_pixels: int


@dataclass(frozen=True, slots=True)
class NoiseGateResult:
    proposal_mask: np.ndarray
    noise_probability_mask: np.ndarray
    static_terrain_mask: np.ndarray
    evidence: Mapping[tuple[int, int], NoiseGateEvidence]
    raw_active_pixels: int
    noise_gated_active_pixels: int
    noise_removed_pixels: int
    noise_removed_ratio: float
    suppressed_cells: int
    override_cells: int


class PixelVariabilityMap:
    """EMA probability that each pixel changes repeatedly.

    The map learns nuisance animation (water, foam, recurring particles) but it is
    never an authority that permanently blacks out a region. Object/body/track
    evidence may override it on any frame.
    """

    def __init__(self, *, alpha: float = 0.08) -> None:
        self.alpha = float(max(0.005, min(0.50, alpha)))
        self.probability: np.ndarray | None = None

    def observe(self, binary_mask: np.ndarray) -> np.ndarray:
        current = (binary_mask > 0).astype(np.float32)
        if self.probability is None or self.probability.shape != current.shape:
            self.probability = current * self.alpha
        else:
            self.probability *= 1.0 - self.alpha
            self.probability += current * self.alpha
        return self.probability

    def high_variability_mask(self, threshold: float = 0.34) -> np.ndarray:
        if self.probability is None:
            return np.zeros((1, 1), dtype=np.uint8)
        return np.where(self.probability >= float(threshold), 255, 0).astype(np.uint8)


class NoiseAwareDifferenceGate:
    """PR27.9 two-route difference gate.

    Route A observes every changed pixel to learn nuisance/background behavior.
    Route B emits a filtered proposal mask. A cell below 12% may not open a new
    object solely from raw difference, but existing tracks, spawn evidence,
    humanoid objectness and connected strong neighbors can override the gate.
    """

    def __init__(
        self,
        grid: FixedNativeGridCalibration,
        *,
        new_candidate_cell_ratio: float = 0.12,
        tracked_candidate_keep_ratio: float = 0.04,
        quiet_cell_floor_ratio: float = 0.03,
        noise_percentile_margin: float = 0.025,
    ) -> None:
        self.grid = grid
        self.new_candidate_cell_ratio = float(max(0.01, min(0.90, new_candidate_cell_ratio)))
        self.tracked_candidate_keep_ratio = float(max(0.005, min(self.new_candidate_cell_ratio, tracked_candidate_keep_ratio)))
        self.quiet_cell_floor_ratio = float(max(0.001, min(self.new_candidate_cell_ratio, quiet_cell_floor_ratio)))
        self.noise_percentile_margin = float(max(0.0, min(0.25, noise_percentile_margin)))
        self.profiles: dict[tuple[int, int], CellNoiseProfile] = defaultdict(CellNoiseProfile)
        self.pixel_variability = PixelVariabilityMap()
        self.last_result: NoiseGateResult | None = None

    @staticmethod
    def _mask_overlap(mask: np.ndarray | None, rect) -> int:
        if mask is None:
            return 0
        patch = mask[rect.top:rect.bottom, rect.left:rect.right]
        return int(np.count_nonzero(patch))

    def observe(
        self,
        raw_difference_mask: np.ndarray,
        *,
        animated_hint_mask: np.ndarray | None = None,
        body_override_mask: np.ndarray | None = None,
        tracked_object_mask: np.ndarray | None = None,
        spawn_delta_mask: np.ndarray | None = None,
    ) -> NoiseGateResult:
        if raw_difference_mask.ndim != 2:
            raise ValueError("PR27_NOISE_MASK_MUST_BE_GRAYSCALE")
        binary = np.where(raw_difference_mask > 0, 255, 0).astype(np.uint8)
        probability = self.pixel_variability.observe(binary)
        variability_mask = np.where(probability >= 0.34, 255, 0).astype(np.uint8)

        ratios: dict[tuple[int, int], float] = {}
        active_counts: dict[tuple[int, int], int] = {}
        thresholds: dict[tuple[int, int], float] = {}
        animated_hints: dict[tuple[int, int], float] = {}
        for cell in self.grid.roi_cells():
            rect = cell.native_rect
            patch = binary[rect.top:rect.bottom, rect.left:rect.right]
            ratio = float(np.count_nonzero(patch) / max(1, patch.size))
            animated_hint = 0.0
            if animated_hint_mask is not None:
                animated_patch = animated_hint_mask[rect.top:rect.bottom, rect.left:rect.right]
                animated_hint = float(np.count_nonzero(animated_patch) / max(1, animated_patch.size))
            profile = self.profiles[cell.relative_key]
            threshold = max(
                self.new_candidate_cell_ratio,
                profile.noise_p95 + self.noise_percentile_margin,
            )
            threshold = float(min(0.80, threshold))
            ratios[cell.relative_key] = ratio
            active_counts[cell.relative_key] = int(np.count_nonzero(patch))
            thresholds[cell.relative_key] = threshold
            animated_hints[cell.relative_key] = animated_hint

        strong_cells = {key for key, ratio in ratios.items() if ratio >= thresholds[key]}
        proposal = np.zeros_like(binary)
        evidence: dict[tuple[int, int], NoiseGateEvidence] = {}
        suppressed_cells = 0
        override_cells = 0

        for cell in self.grid.roi_cells():
            key = cell.relative_key
            rect = cell.native_rect
            patch = binary[rect.top:rect.bottom, rect.left:rect.right]
            ratio = ratios[key]
            threshold = thresholds[key]
            passed = key in strong_cells
            override: str | None = None

            body_pixels = self._mask_overlap(body_override_mask, rect)
            track_pixels = self._mask_overlap(tracked_object_mask, rect)
            spawn_pixels = self._mask_overlap(spawn_delta_mask, rect)
            row, column = key
            connected_strong = any(
                (row + dy, column + dx) in strong_cells
                for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1))
            )

            if not passed and body_pixels > 0:
                passed = True
                override = "OBJECT_OVERRIDE_NOISE_GATE"
            elif not passed and track_pixels > 0 and ratio >= self.tracked_candidate_keep_ratio:
                passed = True
                override = "TRACK_OVERRIDE_NOISE_GATE"
            elif not passed and spawn_pixels > 0:
                passed = True
                override = "SPAWN_DELTA_OVERRIDE_NOISE_GATE"
            elif not passed and connected_strong and ratio >= self.quiet_cell_floor_ratio:
                passed = True
                override = "CONNECTED_STRONG_NEIGHBOR_OVERRIDE"

            gated_patch = patch.copy() if passed else np.zeros_like(patch)
            if passed and override is None:
                noisy = variability_mask[rect.top:rect.bottom, rect.left:rect.right] > 0
                gated_patch[noisy] = 0
            if passed:
                proposal[rect.top:rect.bottom, rect.left:rect.right] = gated_patch
                override_cells += int(override is not None)
            else:
                suppressed_cells += int(active_counts[key] > 0)

            profile = self.profiles[key]
            profile.update(ratio, animated_hint=animated_hints[key])
            evidence[key] = NoiseGateEvidence(
                relative_cell=key,
                raw_changed_ratio=ratio,
                effective_threshold=threshold,
                passed_new_candidate_gate=passed,
                gate_override_reason=override,
                noise_probability=float(np.mean(probability[rect.top:rect.bottom, rect.left:rect.right])),
                animated_probability=profile.animated_probability,
                raw_active_pixels=active_counts[key],
                gated_active_pixels=int(np.count_nonzero(gated_patch)),
            )

        raw_active = int(np.count_nonzero(binary))
        gated_active = int(np.count_nonzero(proposal))
        removed = max(0, raw_active - gated_active)
        removed_ratio = float(removed / max(1, raw_active))

        static_terrain = np.where(probability < 0.22, 255, 0).astype(np.uint8)
        static_terrain = cv2.morphologyEx(
            static_terrain,
            cv2.MORPH_OPEN,
            np.ones((3, 3), np.uint8),
        )

        probability_u8 = np.clip(probability * 255.0, 0, 255).astype(np.uint8)
        result = NoiseGateResult(
            proposal_mask=proposal,
            noise_probability_mask=probability_u8,
            static_terrain_mask=static_terrain,
            evidence=evidence,
            raw_active_pixels=raw_active,
            noise_gated_active_pixels=gated_active,
            noise_removed_pixels=removed,
            noise_removed_ratio=removed_ratio,
            suppressed_cells=suppressed_cells,
            override_cells=override_cells,
        )
        self.last_result = result
        return result


__all__ = [
    "CellNoiseProfile",
    "NoiseAwareDifferenceGate",
    "NoiseGateEvidence",
    "NoiseGateResult",
    "PixelVariabilityMap",
]
