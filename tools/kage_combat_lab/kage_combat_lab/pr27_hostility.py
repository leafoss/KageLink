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
    def __init__(self, *, opponent_confirm_frames: int = 3, approach_confirm_frames: int = 3, maximum_missing_frames: int = 8) -> None:
        self.opponent_confirm_frames = max(2, int(opponent_confirm_frames))
        self.approach_confirm_frames = max(2, int(approach_confirm_frames))
        self.maximum_missing_frames = max(1, int(maximum_missing_frames))
        self.tracks: dict[int, HostilityTrack] = {}
        self._next_track_id = 1

    @staticmethod
    def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
        return float(np.hypot(a[0] - b[0], a[1] - b[1]))

    @staticmethod
    def _similarity(a: np.ndarray, b: np.ndarray) -> float:
        if a.shape != b.shape or a.size == 0:
            return 0.0
        denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
        return 0.0 if denominator <= 1e-9 else float(max(0.0, min(1.0, np.dot(a, b) / denominator)))

    @staticmethod
    def _unwrap(item) -> tuple[EntityCandidate, int | None, bool]:
        candidate = getattr(item, "candidate", item)
        object_id = getattr(item, "track_id", None) if candidate is not item else None
        return candidate, object_id, bool(getattr(item, "spawned_after_dojo", False))

    def _new(self, candidate: EntityCandidate, frame: int, self_anchor, object_id, spawned) -> HostilityTrack:
        track = HostilityTrack(self._next_track_id, candidate, frame, frame, descriptor=candidate.descriptor.copy(), object_track_id=object_id, spawned_after_dojo=spawned)
        self._next_track_id += 1
        track.positions.append(candidate.feet_anchor)
        if self_anchor is not None:
            track.distances_to_self.append(self._distance(candidate.feet_anchor, self_anchor))
        self.tracks[track.track_id] = track
        return track

    def _update(self, track: HostilityTrack, candidate: EntityCandidate, frame: int, self_anchor, object_id, spawned) -> None:
        track.candidate = candidate
        track.last_seen_frame = frame
        track.observations += 1
        track.missing_frames = 0
        track.positions.append(candidate.feet_anchor)
        if self_anchor is not None:
            track.distances_to_self.append(self._distance(candidate.feet_anchor, self_anchor))
            track.distance_history_frozen = False
        else:
            track.distance_history_frozen = True
        track.descriptor = (0.78 * track.descriptor + 0.22 * candidate.descriptor).astype(np.float32)
        track.object_track_id = object_id if object_id is not None else track.object_track_id
        track.spawned_after_dojo = track.spawned_after_dojo or spawned

    def _association_score(self, track: HostilityTrack, candidate: EntityCandidate) -> float:
        distance = self._distance(track.candidate.feet_anchor, candidate.feet_anchor)
        limit = 96.0 + track.missing_frames * 32.0
        if distance > limit:
            return 0.0
        proximity = max(0.0, 1.0 - distance / max(1.0, limit))
        appearance = self._similarity(track.descriptor, candidate.descriptor)
        size = min(track.candidate.area, candidate.area) / max(1, max(track.candidate.area, candidate.area))
        return 0.48 * proximity + 0.32 * appearance + 0.20 * size

    def _approach(self, track: HostilityTrack, stationary: bool) -> tuple[bool, float]:
        if not stationary or track.distance_history_frozen or len(track.distances_to_self) < self.approach_confirm_frames + 1:
            track.approach_confirm_frames = 0
            return False, 0.0
        values = list(track.distances_to_self)[-(self.approach_confirm_frames + 1):]
        deltas = [values[i] - values[i + 1] for i in range(len(values) - 1)]
        reduction = values[0] - values[-1]
        if all(delta >= 1.5 for delta in deltas) and reduction >= 5.0:
            track.approach_confirm_frames += 1
            return True, min(1.0, reduction / 24.0)
        track.approach_confirm_frames = 0
        return False, 0.0

    def _classify(self, track: HostilityTrack, *, stationary: bool, self_confirmed: bool, known: bool, hit: bool, attack: bool, contact: bool) -> None:
        if not self_confirmed:
            track.distance_history_frozen = True
            track.hostility_state = HostilityState.FROZEN_SELF_UNCERTAIN
            track.hostility_evidence = tuple((*track.hostility_evidence, "SELF_UNCERTAIN_EVIDENCE_FROZEN"))[-4:]
            return
        if track.observations < self.opponent_confirm_frames:
            track.hostility_state = HostilityState.OPPONENT_CANDIDATE
            track.hostility_score = min(0.30, track.observations / self.opponent_confirm_frames * 0.30)
            track.hostility_evidence = ("WAITING_STABLE_BODY_TRACK",)
            return
        score = 0.0
        evidence: list[str] = []
        if known:
            score += 0.85; evidence.append("KNOWN_HOSTILE_TEMPLATE")
        if track.spawned_after_dojo:
            score += 0.45; evidence.append("NEW_HUMANOID_AFTER_DOJO_SPAWN")
        approached, strength = self._approach(track, stationary)
        if approached:
            score += 0.68 + 0.12 * strength
            evidence.append("CONSISTENT_APPROACH_TO_FIXED_SELF")
        if hit:
            score += 0.75; evidence.append("HIT_EVENT_TEMPORALLY_ASSOCIATED")
        if attack:
            score += 0.55; evidence.append("ATTACK_ANIMATION_DIRECTED_AT_SELF")
        if contact:
            score += 0.30; evidence.append("REPEATED_CONTACT_WITH_SELF")
        if not evidence:
            evidence.append("NO_EXPLICIT_HOSTILITY_EVIDENCE")
        track.hostility_score = min(1.0, score)
        track.hostility_evidence = tuple(evidence)
        if score >= 0.65 and evidence != ["NO_EXPLICIT_HOSTILITY_EVIDENCE"]:
            track.hostility_state = HostilityState.HOSTILE_CONFIRMED
            track.candidate.candidate_class = CandidateClass.HOSTILE_CONFIRMED
        else:
            track.hostility_state = HostilityState.HOSTILITY_PENDING
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
        valid_classes = {CandidateClass.HUMANOID_CANDIDATE, CandidateClass.OPPONENT_CANDIDATE, CandidateClass.HOSTILITY_PENDING, CandidateClass.HOSTILE_CONFIRMED}
        for item in candidates:
            candidate, object_id, spawned = self._unwrap(item)
            if candidate.candidate_class in valid_classes:
                entries.append((candidate, object_id, spawned))
        known_ids = set(map(int, known_hostile_candidate_ids)); spawn_ids = set(map(int, spawn_object_track_ids)); veto_ids = set(map(int, trainer_veto_object_track_ids))
        attack_ids = set(map(int, attack_directed_object_track_ids)); contact_ids = set(map(int, repeated_contact_object_track_ids))
        used_tracks: set[int] = set(); used_entries: set[int] = set()
        by_object = {t.object_track_id: t for t in self.tracks.values() if t.object_track_id is not None}
        for i, (candidate, object_id, spawned) in enumerate(entries):
            if object_id is None or object_id in veto_ids or object_id not in by_object:
                continue
            track = by_object[object_id]
            self._update(track, candidate, frame_index, self_anchor if self_confirmed else None, object_id, spawned or object_id in spawn_ids)
            used_tracks.add(track.track_id); used_entries.add(i)
        scored = []
        for track_id, track in self.tracks.items():
            if track_id in used_tracks:
                continue
            for i, (candidate, object_id, _spawned) in enumerate(entries):
                if i in used_entries or object_id in veto_ids:
                    continue
                score = self._association_score(track, candidate)
                if score >= 0.45:
                    scored.append((score, track_id, i))
        for _score, track_id, i in sorted(scored, reverse=True):
            if track_id in used_tracks or i in used_entries:
                continue
            candidate, object_id, spawned = entries[i]
            self._update(self.tracks[track_id], candidate, frame_index, self_anchor if self_confirmed else None, object_id, spawned or (object_id in spawn_ids if object_id is not None else False))
            used_tracks.add(track_id); used_entries.add(i)
        for i, (candidate, object_id, spawned) in enumerate(entries):
            if i in used_entries or object_id in veto_ids:
                continue
            track = self._new(candidate, frame_index, self_anchor if self_confirmed else None, object_id, spawned or (object_id in spawn_ids if object_id is not None else False))
            used_tracks.add(track.track_id)
        for track_id, track in list(self.tracks.items()):
            if track_id not in used_tracks and track.last_seen_frame != frame_index:
                track.missing_frames += 1
                if track.missing_frames > self.maximum_missing_frames:
                    del self.tracks[track_id]
                    continue
            object_id = track.object_track_id
            self._classify(
                track, stationary=player_stationary, self_confirmed=self_confirmed,
                known=track.candidate.candidate_id in known_ids, hit=hit_candidate_id == track.candidate.candidate_id,
                attack=object_id in attack_ids if object_id is not None else False,
                contact=object_id in contact_ids if object_id is not None else False,
            )
        return tuple(sorted(self.tracks.values(), key=lambda item: item.track_id))

    def hostile_tracks(self) -> tuple[HostilityTrack, ...]:
        return tuple(t for t in self.tracks.values() if t.visible and t.hostility_state is HostilityState.HOSTILE_CONFIRMED)


__all__ = ["HostilityEvaluator", "HostilityState", "HostilityTrack"]
