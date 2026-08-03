from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

import numpy as np

from .pr27_entity_validation import CandidateClass, EntityCandidate


class HostilityState(str, Enum):
    UNCLASSIFIED = "UNCLASSIFIED"
    OPPONENT_CANDIDATE = "OPPONENT_CANDIDATE"
    HOSTILITY_PENDING = "HOSTILITY_PENDING"
    HOSTILE_CONFIRMED = "HOSTILE_CONFIRMED"
    NPC = "NPC"
    FROZEN_SELF_UNCERTAIN = "FROZEN_SELF_UNCERTAIN"


@dataclass(slots=True)
class HostilityTrack:
    track_id: int
    candidate: EntityCandidate
    first_seen_frame: int
    last_seen_frame: int
    observations: int = 1
    missing_frames: int = 0
    positions: deque[tuple[float, float]] = field(default_factory=lambda: deque(maxlen=12))
    distances_to_self: deque[float] = field(default_factory=lambda: deque(maxlen=12))
    descriptor: np.ndarray = field(default_factory=lambda: np.zeros(32, dtype=np.float32))
    hostility_state: HostilityState = HostilityState.UNCLASSIFIED
    hostility_score: float = 0.0
    hostility_evidence: tuple[str, ...] = ()
    approach_confirm_frames: int = 0
    known_hostile: bool = False
    hit_associated: bool = False
    object_track_id: int | None = None
    spawned_after_dojo: bool = False
    distance_history_frozen: bool = False

    @property
    def visible(self) -> bool:
        return self.missing_frames == 0


class HostilityEvaluator:
    """Promote only stable body/object tracks with explicit hostility evidence."""

    def __init__(
        self,
        *,
        opponent_confirm_frames: int = 3,
        approach_confirm_frames: int = 3,
        maximum_missing_frames: int = 8,
    ) -> None:
        self.opponent_confirm_frames = max(2, int(opponent_confirm_frames))
        self.approach_confirm_frames = max(2, int(approach_confirm_frames))
        self.maximum_missing_frames = max(1, int(maximum_missing_frames))
        self.tracks: dict[int, HostilityTrack] = {}
        self._next_track_id = 1

    @staticmethod
    def _descriptor_similarity(left: np.ndarray, right: np.ndarray) -> float:
        if left.size == 0 or right.size == 0 or left.shape != right.shape:
            return 0.0
        denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
        if denominator <= 1e-9:
            return 0.0
        return float(max(0.0, min(1.0, np.dot(left, right) / denominator)))

    @staticmethod
    def _distance(left: tuple[float, float], right: tuple[float, float]) -> float:
        return float(np.hypot(left[0] - right[0], left[1] - right[1]))

    @staticmethod
    def _unwrap(item) -> tuple[EntityCandidate, int | None, bool]:
        candidate = getattr(item, "candidate", item)
        object_track_id = getattr(item, "track_id", None) if candidate is not item else None
        spawned = bool(getattr(item, "spawned_after_dojo", False))
        return candidate, object_track_id, spawned

    def _association_score(self, track: HostilityTrack, candidate: EntityCandidate) -> float:
        distance = self._distance(track.candidate.feet_anchor, candidate.feet_anchor)
        if distance > 96.0 + track.missing_frames * 32.0:
            return 0.0
        proximity = max(0.0, 1.0 - distance / (128.0 + track.missing_frames * 32.0))
        appearance = self._descriptor_similarity(track.descriptor, candidate.descriptor)
        old_area = max(1, track.candidate.area)
        new_area = max(1, candidate.area)
        size = min(old_area, new_area) / max(old_area, new_area)
        return 0.48 * proximity + 0.32 * appearance + 0.20 * size

    def _new_track(
        self,
        candidate: EntityCandidate,
        *,
        frame_index: int,
        self_anchor: tuple[float, float] | None,
        object_track_id: int | None,
        spawned_after_dojo: bool,
    ) -> HostilityTrack:
        track = HostilityTrack(
            track_id=self._next_track_id,
            candidate=candidate,
            first_seen_frame=frame_index,
            last_seen_frame=frame_index,
            descriptor=candidate.descriptor.copy(),
            object_track_id=object_track_id,
            spawned_after_dojo=spawned_after_dojo,
        )
        track.positions.append(candidate.feet_anchor)
        if self_anchor is not None:
            track.distances_to_self.append(self._distance(candidate.feet_anchor, self_anchor))
        self.tracks[track.track_id] = track
        self._next_track_id += 1
        return track

    def _update_track(
        self,
        track: HostilityTrack,
        candidate: EntityCandidate,
        *,
        frame_index: int,
        self_anchor: tuple[float, float] | None,
        object_track_id: int | None,
        spawned_after_dojo: bool,
    ) -> None:
        track.candidate = candidate
        track.last_seen_frame = frame_index
        track.observations += 1
        track.missing_frames = 0
        track.positions.append(candidate.feet_anchor)
        if self_anchor is not None:
            track.distances_to_self.append(self._distance(candidate.feet_anchor, self_anchor))
            track.distance_history_frozen = False
        else:
            track.distance_history_frozen = True
        track.descriptor = (0.78 * track.descriptor + 0.22 * candidate.descriptor).astype(np.float32)
        if object_track_id is not None:
            track.object_track_id = object_track_id
        track.spawned_after_dojo = track.spawned_after_dojo or spawned_after_dojo

    def _approach_evidence(self, track: HostilityTrack, *, player_stationary: bool) -> tuple[bool, float]:
        if (
            not player_stationary
            or track.distance_history_frozen
            or len(track.distances_to_self) < self.approach_confirm_frames + 1
        ):
            track.approach_confirm_frames = 0
            return False, 0.0
        values = list(track.distances_to_self)[-(self.approach_confirm_frames + 1) :]
        deltas = [values[index] - values[index + 1] for index in range(len(values) - 1)]
        coherent = all(delta >= 1.5 for delta in deltas)
        total_reduction = values[0] - values[-1]
        if coherent and total_reduction >= 5.0:
            track.approach_confirm_frames += 1
            strength = min(1.0, total_reduction / 24.0)
            return True, strength
        track.approach_confirm_frames = 0
        return False, 0.0

    def _classify(
        self,
        track: HostilityTrack,
        *,
        player_stationary: bool,
        known_hostile: bool,
        hit_associated: bool,
        self_confirmed: bool,
        attack_directed: bool,
        repeated_contact: bool,
    ) -> None:
        if not self_confirmed:
            track.distance_history_frozen = True
            track.hostility_state = HostilityState.FROZEN_SELF_UNCERTAIN
            track.hostility_evidence = tuple((*track.hostility_evidence, "SELF_UNCERTAIN_EVIDENCE_FROZEN"))[-4:]
            return
        evidence: list[str] = []
        score = 0.0
        humanoid = (
            track.candidate.candidate_class in {
                CandidateClass.HUMANOID_CANDIDATE,
                CandidateClass.OPPONENT_CANDIDATE,
                CandidateClass.HOSTILITY_PENDING,
                CandidateClass.HOSTILE_CONFIRMED,
            }
            and track.candidate.humanoid_confidence >= 0.45
        )
        if not humanoid:
            track.hostility_state = HostilityState.UNCLASSIFIED
            track.hostility_score = 0.0
            track.hostility_evidence = ("HUMANOID_BODY_NOT_CONFIRMED",)
            return
        if track.observations < self.opponent_confirm_frames:
            track.hostility_state = HostilityState.OPPONENT_CANDIDATE
            track.hostility_score = min(0.30, track.observations / self.opponent_confirm_frames * 0.30)
            track.hostility_evidence = ("WAITING_STABLE_BODY_TRACK",)
            return

        track.hostility_state = HostilityState.HOSTILITY_PENDING
        if known_hostile:
            score += 0.85
            evidence.append("KNOWN_HOSTILE_TEMPLATE")
            track.known_hostile = True
        if track.spawned_after_dojo:
            score += 0.45
            evidence.append("NEW_HUMANOID_AFTER_DOJO_SPAWN")
        approached, strength = self._approach_evidence(track, player_stationary=player_stationary)
        if approached:
            score += 0.40 * max(0.75, strength)
            evidence.append("CONSISTENT_APPROACH_TO_FIXED_SELF")
        if hit_associated:
            score += 0.75
            evidence.append("HIT_EVENT_TEMPORALLY_ASSOCIATED")
            track.hit_associated = True
        if attack_directed:
            score += 0.55
            evidence.append("ATTACK_ANIMATION_DIRECTED_AT_SELF")
        if repeated_contact:
            score += 0.30
            evidence.append("REPEATED_CONTACT_WITH_SELF")

        if not evidence:
            evidence.append("NO_EXPLICIT_HOSTILITY_EVIDENCE")
        track.hostility_score = min(1.0, score)
        track.hostility_evidence = tuple(evidence)
        non_generic = any(
            item in evidence
            for item in {
                "KNOWN_HOSTILE_TEMPLATE",
                "NEW_HUMANOID_AFTER_DOJO_SPAWN",
                "CONSISTENT_APPROACH_TO_FIXED_SELF",
                "HIT_EVENT_TEMPORALLY_ASSOCIATED",
                "ATTACK_ANIMATION_DIRECTED_AT_SELF",
                "REPEATED_CONTACT_WITH_SELF",
            }
        )
        if score >= 0.65 and non_generic:
            track.hostility_state = HostilityState.HOSTILE_CONFIRMED
            track.candidate.candidate_class = CandidateClass.HOSTILE_CONFIRMED
        else:
            track.candidate.candidate_class = CandidateClass.HOSTILITY_PENDING

    def update(
        self,
        candidates: Iterable,
        *,
        frame_index: int,
        self_anchor: tuple[float, float] | None,
        player_stationary: bool = True,
        known_hostile_candidate_ids: Iterable[int] = (),
        hit_candidate_id: int | None = None,
        self_confirmed: bool = True,
        spawn_object_track_ids: Iterable[int] = (),
        trainer_veto_object_track_ids: Iterable[int] = (),
        attack_directed_object_track_ids: Iterable[int] = (),
        repeated_contact_object_track_ids: Iterable[int] = (),
    ) -> tuple[HostilityTrack, ...]:
        entries = []
        for item in candidates:
            candidate, object_track_id, spawned = self._unwrap(item)
            if candidate.candidate_class in {
                CandidateClass.HUMANOID_CANDIDATE,
                CandidateClass.OPPONENT_CANDIDATE,
                CandidateClass.HOSTILITY_PENDING,
                CandidateClass.HOSTILE_CONFIRMED,
            }:
                entries.append((candidate, object_track_id, spawned))
        known_ids = frozenset(int(value) for value in known_hostile_candidate_ids)
        spawn_ids = frozenset(int(value) for value in spawn_object_track_ids)
        trainer_veto_ids = frozenset(int(value) for value in trainer_veto_object_track_ids)
        attack_ids = frozenset(int(value) for value in attack_directed_object_track_ids)
        contact_ids = frozenset(int(value) for value in repeated_contact_object_track_ids)

        used_tracks: set[int] = set()
        used_entries: set[int] = set()
        by_object_id = {
            track.object_track_id: track
            for track in self.tracks.values()
            if track.object_track_id is not None
        }
        for index, (candidate, object_track_id, spawned) in enumerate(entries):
            if object_track_id is None or object_track_id in trainer_veto_ids:
                continue
            track = by_object_id.get(object_track_id)
            if track is not None:
                self._update_track(
                    track,
                    candidate,
                    frame_index=frame_index,
                    self_anchor=self_anchor if self_confirmed else None,
                    object_track_id=object_track_id,
                    spawned_after_dojo=spawned or object_track_id in spawn_ids,
                )
                used_tracks.add(track.track_id)
                used_entries.add(index)

        scored: list[tuple[float, int, int]] = []
        for track_id, track in self.tracks.items():
            if track_id in used_tracks:
                continue
            for index, (candidate, object_track_id, _spawned) in enumerate(entries):
                if index in used_entries or object_track_id in trainer_veto_ids:
                    continue
                score = self._association_score(track, candidate)
                if score >= 0.45:
                    scored.append((score, track_id, index))
        for _score, track_id, index in sorted(scored, reverse=True):
            if track_id in used_tracks or index in used_entries:
                continue
            candidate, object_track_id, spawned = entries[index]
            self._update_track(
                self.tracks[track_id],
                candidate,
                frame_index=frame_index,
                self_anchor=self_anchor if self_confirmed else None,
                object_track_id=object_track_id,
                spawned_after_dojo=spawned or (object_track_id in spawn_ids if object_track_id is not None else False),
            )
            used_tracks.add(track_id)
            used_entries.add(index)

        for index, (candidate, object_track_id, spawned) in enumerate(entries):
            if index in used_entries or object_track_id in trainer_veto_ids:
                continue
            track = self._new_track(
                candidate,
                frame_index=frame_index,
                self_anchor=self_anchor if self_confirmed else None,
                object_track_id=object_track_id,
                spawned_after_dojo=spawned or (object_track_id in spawn_ids if object_track_id is not None else False),
            )
            used_tracks.add(track.track_id)

        for track_id, track in list(self.tracks.items()):
            if track_id not in used_tracks and track.last_seen_frame != frame_index:
                track.missing_frames += 1
                if track.missing_frames > self.maximum_missing_frames:
                    del self.tracks[track_id]
                    continue
            object_id = track.object_track_id
            candidate_id = track.candidate.candidate_id
            self._classify(
                track,
                player_stationary=player_stationary,
                known_hostile=candidate_id in known_ids,
                hit_associated=(hit_candidate_id == candidate_id),
                self_confirmed=self_confirmed,
                attack_directed=object_id in attack_ids if object_id is not None else False,
                repeated_contact=object_id in contact_ids if object_id is not None else False,
            )
        return tuple(sorted(self.tracks.values(), key=lambda item: item.track_id))

    def hostile_tracks(self) -> tuple[HostilityTrack, ...]:
        return tuple(
            track
            for track in self.tracks.values()
            if track.visible and track.hostility_state is HostilityState.HOSTILE_CONFIRMED
        )


__all__ = ["HostilityEvaluator", "HostilityState", "HostilityTrack"]
