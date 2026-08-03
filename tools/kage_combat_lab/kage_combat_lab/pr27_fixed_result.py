from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Mapping

import numpy as np

from .pr27_animated_background import BackgroundClass, BackgroundEvidence
from .pr27_camera_motion import CameraMotionResult
from .pr27_entity_validation import CandidateClass, EntityCandidate
from .pr27_fixed_grid import NativeRect
from .pr27_fixed_self import SelfVisualObservation
from .pr27_hostility import HostilityState, HostilityTrack
from .pr27_trainer_mask import TrainerMaskEvidence


@dataclass(slots=True)
class FixedPerceptionResult:
    frame_index: int
    native_size: tuple[int, int]
    fixed_self_cell: tuple[int, int]
    fixed_self_bbox: NativeRect
    self_observation: SelfVisualObservation
    camera_motion: CameraMotionResult
    camera_compensated: bool
    background_evidence: Mapping[tuple[int, int], BackgroundEvidence]
    candidates: tuple[EntityCandidate, ...]
    hostility_tracks: tuple[HostilityTrack, ...]
    trainer_bbox: NativeRect | None
    trainer_evidence: TrainerMaskEvidence
    trainer_mask_only: bool
    trainer_rgb_replaced: bool
    planned_action: str
    action_block_reason: str
    original_bgr: np.ndarray
    overlay_bgr: np.ndarray
    raw_difference_mask: np.ndarray
    compensated_residual_mask: np.ndarray
    animated_background_mask: np.ndarray
    body_mask: np.ndarray
    source_reconstructed: bool = False
    source_has_legacy_overlay: bool = False
    timings_ms: Mapping[str, float] = field(default_factory=dict)

    def to_json_dict(self) -> dict[str, object]:
        self_obs = self.self_observation
        hostiles = [
            {
                "track_id": track.track_id,
                "state": track.hostility_state.value,
                "score": track.hostility_score,
                "evidence": list(track.hostility_evidence),
                "bbox": asdict(track.candidate.bbox),
                "feet_anchor": list(track.candidate.feet_anchor),
            }
            for track in self.hostility_tracks
        ]
        candidates = [
            {
                "candidate_id": candidate.candidate_id,
                "class": candidate.candidate_class.value,
                "bbox": asdict(candidate.bbox),
                "feet_anchor": list(candidate.feet_anchor),
                "relative_cell": candidate.relative_cell,
                "entity_confidence": candidate.entity_confidence,
                "humanoid_confidence": candidate.humanoid_confidence,
                "rejection_reason": candidate.rejection_reason,
            }
            for candidate in self.candidates
        ]
        return {
            "frame_index": self.frame_index,
            "native_size": list(self.native_size),
            "fixed_self_cell": list(self.fixed_self_cell),
            "fixed_self_bbox": asdict(self.fixed_self_bbox),
            "self_body_found": self_obs.found,
            "self_body_bbox": None if self_obs.bbox is None else asdict(self_obs.bbox),
            "self_feet_anchor": self_obs.feet_anchor,
            "self_anchor_inside_cell": self_obs.anchor_inside_fixed_cell,
            "self_template_score": self_obs.template_score,
            "self_state": self_obs.state.value,
            "camera_dx": self.camera_motion.dx_px,
            "camera_dy": self.camera_motion.dy_px,
            "camera_confidence": self.camera_motion.confidence,
            "camera_motion_source": self.camera_motion.source,
            "camera_motion_consensus": self.camera_motion.consensus,
            "camera_compensated": self.camera_compensated,
            "animated_background_regions": [
                list(key)
                for key, evidence in self.background_evidence.items()
                if evidence.background_class is BackgroundClass.ANIMATED_BACKGROUND
            ],
            "entity_candidates": candidates,
            "humanoid_candidates": [
                item
                for item in candidates
                if item["class"] == CandidateClass.HUMANOID_CANDIDATE.value
            ],
            "opponent_candidates": hostiles,
            "hostile_confirmed": any(
                track.hostility_state is HostilityState.HOSTILE_CONFIRMED
                for track in self.hostility_tracks
            ),
            "trainer_bbox": None if self.trainer_bbox is None else asdict(self.trainer_bbox),
            "trainer_mask_confidence": self.trainer_evidence.confidence,
            "trainer_mask_source": self.trainer_evidence.source,
            "trainer_mask_only": self.trainer_mask_only,
            "trainer_rgb_replaced": self.trainer_rgb_replaced,
            "planned_action": self.planned_action,
            "action_block_reason": self.action_block_reason,
            "source_reconstructed": self.source_reconstructed,
            "source_has_legacy_overlay": self.source_has_legacy_overlay,
            "timings_ms": dict(self.timings_ms),
        }


__all__ = ["FixedPerceptionResult"]
