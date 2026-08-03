from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Mapping

import numpy as np

from .pr27_animated_background import BackgroundClass, BackgroundEvidence
from .pr27_camera_motion import CameraMotionResult
from .pr27_entity_validation import CandidateClass, EntityCandidate
from .pr27_fixed_grid import NativeRect
from .pr27_fixed_self import SelfVisualObservation
from .pr27_hostility import HostilityState, HostilityTrack
from .pr27_noise_model import NoiseGateResult
from .pr27_object_tracking import PersistentObjectTrack
from .pr27_spawn_delta import SpawnDeltaEvidence
from .pr27_trainer_identity import TrainerEvidence


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
    trainer_evidence: TrainerEvidence
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
    noise_gate: NoiseGateResult | None = None
    object_tracks: tuple[PersistentObjectTrack, ...] = ()
    spawn_evidence: SpawnDeltaEvidence | None = None
    self_protected_mask: np.ndarray | None = None
    trainer_identity_match_mask: np.ndarray | None = None
    object_proposal_mask: np.ndarray | None = None
    camera_static_terrain_mask: np.ndarray | None = None
    source_reconstructed: bool = False
    source_has_legacy_overlay: bool = False
    timings_ms: Mapping[str, float] = field(default_factory=dict)

    def to_json_dict(self) -> dict[str, object]:
        self_obs = self.self_observation
        hostility = [
            {
                "track_id": track.track_id,
                "object_track_id": track.object_track_id,
                "state": track.hostility_state.value,
                "score": track.hostility_score,
                "evidence": list(track.hostility_evidence),
                "bbox": asdict(track.candidate.bbox),
                "feet_anchor": list(track.candidate.feet_anchor),
                "distance_history": list(track.distances_to_self),
                "approach_history": track.approach_confirm_frames,
                "spawned_after_dojo": track.spawned_after_dojo,
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
        rejection_counts = Counter(
            candidate.rejection_reason or "ACCEPTED_BODY_CORE"
            for candidate in self.candidates
        )
        object_tracks = [
            {
                "track_id": track.track_id,
                "state": track.state.value,
                "bbox": asdict(track.bbox),
                "feet_anchor": list(track.feet_anchor),
                "relative_cell": track.relative_cell,
                "source": track.source,
                "observations": track.observations,
                "missing_frames": track.missing_frames,
                "visible": track.visible,
                "confirmed": track.confirmed,
                "trainer_score": track.trainer_similarity,
                "self_score": track.self_similarity,
                "lineage": list(track.lineage),
                "spawned_after_dojo": track.spawned_after_dojo,
            }
            for track in self.object_tracks
        ]
        cell_activity = []
        if self.noise_gate is not None:
            for key, evidence in sorted(self.noise_gate.evidence.items()):
                cell_activity.append(
                    {
                        "relative_cell": list(key),
                        "raw_changed_ratio": evidence.raw_changed_ratio,
                        "effective_threshold": evidence.effective_threshold,
                        "noise_probability": evidence.noise_probability,
                        "animated_probability": evidence.animated_probability,
                        "passed_new_candidate_gate": evidence.passed_new_candidate_gate,
                        "override_reason": evidence.gate_override_reason,
                        "raw_active_pixels": evidence.raw_active_pixels,
                        "gated_active_pixels": evidence.gated_active_pixels,
                    }
                )
        camera = self.camera_motion
        trainer = self.trainer_evidence
        raw_active = int(np.count_nonzero(self.raw_difference_mask))
        gated_active = (
            int(np.count_nonzero(self.object_proposal_mask))
            if self.object_proposal_mask is not None
            else raw_active
        )
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
            "self": {
                "score": self_obs.template_score,
                "matched_template_id": self_obs.matched_template_id,
                "preserved_from_frame": self_obs.preserved_from_frame,
                "missing_frames": self_obs.missing_frames,
                "protected_mask_pixels": self_obs.protected_mask_pixels,
                "template_update_allowed": self_obs.template_update_allowed,
                "template_update_block_reason": self_obs.template_update_block_reason,
            },
            "camera_dx": camera.dx_px,
            "camera_dy": camera.dy_px,
            "camera_confidence": camera.confidence,
            "camera_motion_source": camera.source,
            "camera_motion_consensus": camera.consensus,
            "camera_compensated": self.camera_compensated,
            "camera": {
                "phase_dx": camera.phase_dx,
                "phase_dy": camera.phase_dy,
                "phase_confidence": camera.phase_confidence,
                "flow_dx": camera.flow_dx,
                "flow_dy": camera.flow_dy,
                "flow_consensus": camera.flow_consensus,
                "phase_flow_disagreement": camera.phase_flow_disagreement,
                "accepted_dx": camera.dx_px,
                "accepted_dy": camera.dy_px,
                "accepted": camera.shift_accepted,
                "rejection_reason": camera.shift_rejection_reason,
                "stationary_mode": camera.stationary_mode,
                "feature_count": camera.feature_count,
            },
            "animated_background_regions": [
                list(key)
                for key, evidence in self.background_evidence.items()
                if evidence.background_class is BackgroundClass.ANIMATED_BACKGROUND
            ],
            "raw_active_pixels": raw_active,
            "noise_gated_active_pixels": gated_active,
            "noise_removed_pixels": raw_active - gated_active,
            "noise_removed_ratio": 0.0 if raw_active == 0 else (raw_active - gated_active) / raw_active,
            "raw_components": len(self.candidates),
            "object_proposal_components": sum(
                candidate.candidate_class is not CandidateClass.UNKNOWN_VISUAL_CHANGE
                for candidate in self.candidates
            ),
            "cell_activity": cell_activity,
            "entity_candidates": candidates,
            "humanoid_candidates": [
                item for item in candidates
                if item["class"] in {
                    CandidateClass.HUMANOID_CANDIDATE.value,
                    CandidateClass.OPPONENT_CANDIDATE.value,
                    CandidateClass.HOSTILITY_PENDING.value,
                    CandidateClass.HOSTILE_CONFIRMED.value,
                }
            ],
            "rejection_reason_counts": dict(rejection_counts),
            "object_tracks": object_tracks,
            "confirmed_body_tracks": sum(track.confirmed for track in self.object_tracks),
            "opponent_candidates": hostility,
            "hostile_confirmed": any(
                track.hostility_state is HostilityState.HOSTILE_CONFIRMED
                for track in self.hostility_tracks
            ),
            "trainer_bbox": None if self.trainer_bbox is None else asdict(self.trainer_bbox),
            "trainer_mask_confidence": trainer.identity_score,
            "trainer_mask_source": trainer.source,
            "trainer_mask_only": self.trainer_mask_only,
            "trainer_rgb_replaced": self.trainer_rgb_replaced,
            "trainer": {
                "state": trainer.state.value,
                "observed_bbox": None if trainer.observed_bbox is None else asdict(trainer.observed_bbox),
                "predicted_bbox": None if trainer.predicted_bbox is None else asdict(trainer.predicted_bbox),
                "identity_score": trainer.identity_score,
                "current_frame_match": trainer.current_frame_match,
                "candidate_vetoes": list(trainer.candidate_vetoes),
                "entity_detection_mask_pixels": trainer.entity_detection_mask_pixels,
            },
            "spawn_delta": None if self.spawn_evidence is None else {
                "available": self.spawn_evidence.available,
                "active_pixels": self.spawn_evidence.active_pixels,
                "candidate_ids": list(self.spawn_evidence.candidate_ids),
                "reason": self.spawn_evidence.reason,
            },
            "planned_action": self.planned_action,
            "action_block_reason": self.action_block_reason,
            "source_reconstructed": self.source_reconstructed,
            "source_has_legacy_overlay": self.source_has_legacy_overlay,
            "timings_ms": dict(self.timings_ms),
        }


__all__ = ["FixedPerceptionResult"]
