from __future__ import annotations

from dataclasses import dataclass

from pc_agent.kage_pilot.entity_tracker_v03 import appearance_similarity

from .hunting_chat import HuntingChatEvent
from .validated_combat_core import VisualEvidence

LOGICAL_FOREST_TARGET_ID = "FOREST_SPAWN_OPPONENT_001"


@dataclass(slots=True)
class _Episode:
    first: float
    last: float
    gx: int
    gy: int
    hits: int
    appearance: tuple[float, ...]


@dataclass(slots=True)
class _PendingBody:
    track_id: int
    gx: int
    gy: int
    seen_at: float
    hits: int
    appearance: tuple[float, ...]


class ForestSpawnBinder:
    """Alpha 6 forest binder: event opens acquisition, body confirmation binds identity."""

    MAX_INITIAL_DISTANCE = 3
    INITIAL_WINDOW_SECONDS = 8.0
    PRECHAT_EPISODE_TTL = 3.0
    PREEXISTING_MIN_AGE = 1.25
    PREEXISTING_MAX_GAP = 0.95
    PREEXISTING_APPEARANCE_SIM = 0.82
    CROSS_TRACK_CONFIRM_SECONDS = 0.95
    CROSS_TRACK_MAX_STEP = 1
    CROSS_TRACK_APPEARANCE_SIM = 0.55

    def __init__(self) -> None:
        self._episodes: dict[int, _Episode] = {}
        self._frozen: dict[int, _Episode] = {}
        self.pending: _PendingBody | None = None
        self.spawn_at: float | None = None
        self.spawn_line = ""
        self.spawn_name = ""
        self.bound_track_id: int | None = None
        self.bound_appearance: tuple[float, ...] = ()
        self.last_gx = 0
        self.last_gy = 0

    @staticmethod
    def _distance(dx: int, dy: int) -> int:
        return max(abs(int(dx)), abs(int(dy)))

    @staticmethod
    def _track_data(observer, tracker, track):
        track_id = int(getattr(track, "track_id"))
        metrics = observer.metrics_for(track_id)
        if metrics is None:
            return None
        dx = int(metrics.cell[0] - metrics.player_cell[0])
        dy = int(metrics.cell[1] - metrics.player_cell[1])
        context = tracker.context_for(track_id)
        if str(getattr(context, "state", "VISIBLE")).upper() not in {"VISIBLE", "OCCLUDED"}:
            return None
        appearance = tuple(getattr(context, "appearance", ()) or ())
        try:
            score = float(getattr(track, "enemy_score", 70.0) or 0.0)
        except Exception:
            score = 70.0
        confidence = max(0.42, min(0.98, score / 100.0))
        return track_id, dx, dy, confidence, appearance

    def capture_prespawn(self, observer, tracker, state, now: float) -> None:
        for track in list(getattr(state, "tracks", ()) or ())[:48]:
            try:
                data = self._track_data(observer, tracker, track)
            except Exception:
                continue
            if data is None:
                continue
            track_id, gx, gy, _confidence, appearance = data
            old = self._episodes.get(track_id)
            restart = old is None
            if old is not None:
                gap = now - old.last
                jump = max(abs(gx - old.gx), abs(gy - old.gy))
                similarity = appearance_similarity(appearance, old.appearance)
                if gap > 1.25 or jump > 3 or (appearance and old.appearance and similarity < 0.40):
                    restart = True
            if restart:
                self._episodes[track_id] = _Episode(now, now, gx, gy, 1, appearance)
            else:
                old.last = now
                old.gx = gx
                old.gy = gy
                old.hits += 1
                if appearance:
                    old.appearance = appearance
        for key in [key for key, value in self._episodes.items() if now - value.last > self.PRECHAT_EPISODE_TTL]:
            self._episodes.pop(key, None)

    def on_spawn(self, event: HuntingChatEvent, now: float) -> None:
        self.spawn_at = float(now)
        self.spawn_line = event.text
        self.spawn_name = event.name
        self.pending = None
        self.bound_track_id = None
        self.bound_appearance = ()
        self._frozen = {
            key: _Episode(value.first, value.last, value.gx, value.gy, value.hits, value.appearance)
            for key, value in self._episodes.items()
            if now - value.last <= self.PRECHAT_EPISODE_TTL
        }
        print(
            f"HUNTING_ACQUIRE_OPEN clan={event.clan} name={event.name} "
            f"prespawn_episodes={len(self._frozen)}",
            flush=True,
        )

    def acquisition_expired(self, now: float) -> bool:
        return self.spawn_at is not None and now - self.spawn_at > self.INITIAL_WINDOW_SECONDS

    def _definitely_preexisting(
        self,
        track_id: int,
        gx: int,
        gy: int,
        appearance: tuple[float, ...],
    ) -> bool:
        if self.spawn_at is None:
            return False
        episode = self._frozen.get(track_id)
        if episode is None:
            return False
        age = max(0.0, self.spawn_at - episode.first)
        gap = max(0.0, self.spawn_at - episode.last)
        pos_delta = max(abs(gx - episode.gx), abs(gy - episode.gy))
        similarity = appearance_similarity(appearance, episode.appearance)
        return bool(
            age >= self.PREEXISTING_MIN_AGE
            and gap <= self.PREEXISTING_MAX_GAP
            and episode.hits >= 3
            and pos_delta <= 1
            and appearance
            and episode.appearance
            and similarity >= self.PREEXISTING_APPEARANCE_SIM
        )

    def acquire(self, observer, tracker, state, now: float) -> VisualEvidence | None:
        if self.spawn_at is None or self.acquisition_expired(now):
            return None
        candidates = []
        for track in list(getattr(state, "tracks", ()) or ())[:48]:
            try:
                data = self._track_data(observer, tracker, track)
            except Exception:
                continue
            if data is None:
                continue
            track_id, gx, gy, confidence, appearance = data
            distance = self._distance(gx, gy)
            if distance > self.MAX_INITIAL_DISTANCE:
                continue
            if self._definitely_preexisting(track_id, gx, gy, appearance):
                continue
            candidates.append((distance, -confidence, track_id, gx, gy, confidence, appearance))
        candidates.sort(key=lambda value: (value[0], value[1]))
        if not candidates:
            return None

        _d, _neg, track_id, gx, gy, confidence, appearance = candidates[0]
        pending = self.pending
        same_body = False
        if pending is not None:
            delta_t = now - pending.seen_at
            step = max(abs(gx - pending.gx), abs(gy - pending.gy))
            similarity = appearance_similarity(appearance, pending.appearance)
            same_body = bool(
                track_id == pending.track_id
                or (
                    delta_t <= self.CROSS_TRACK_CONFIRM_SECONDS
                    and step <= self.CROSS_TRACK_MAX_STEP
                    and appearance
                    and pending.appearance
                    and similarity >= self.CROSS_TRACK_APPEARANCE_SIM
                )
            )
        if same_body and pending is not None:
            pending.track_id = track_id
            pending.gx = gx
            pending.gy = gy
            pending.seen_at = now
            pending.hits += 1
            if appearance:
                pending.appearance = appearance
        else:
            self.pending = _PendingBody(track_id, gx, gy, now, 1, appearance)
            pending = self.pending

        print(
            f"HUNTING_TARGET_CANDIDATE track={track_id} d={self._distance(gx, gy)} "
            f"dx={gx} dy={gy} hits={pending.hits}",
            flush=True,
        )
        if pending.hits < 2:
            return None

        self.bound_track_id = track_id
        self.bound_appearance = appearance
        self.last_gx, self.last_gy = gx, gy
        print(
            f"HUNTING_TARGET_BOUND track={track_id} d={self._distance(gx, gy)} dx={gx} dy={gy}",
            flush=True,
        )
        return self._evidence(
            track_id,
            gx,
            gy,
            confidence,
            now,
            "FOREST_ALPHA6_BIND",
            "EXACT_AMBUSH_D3_TWO_TEMPORAL_OBSERVATIONS",
        )

    def current(self, observer, tracker, state, now: float) -> VisualEvidence | None:
        if self.bound_track_id is None:
            return None
        preferred = None
        fallback = []
        for track in list(getattr(state, "tracks", ()) or ())[:48]:
            try:
                data = self._track_data(observer, tracker, track)
            except Exception:
                continue
            if data is None:
                continue
            track_id, gx, gy, _confidence, appearance = data
            if track_id == self.bound_track_id:
                preferred = data
                break
            step = max(abs(gx - self.last_gx), abs(gy - self.last_gy))
            similarity = appearance_similarity(appearance, self.bound_appearance)
            if step <= 2 and appearance and self.bound_appearance and similarity >= 0.55:
                fallback.append((step, -similarity, data))
        data = preferred
        if data is None and fallback:
            fallback.sort(key=lambda value: (value[0], value[1]))
            data = fallback[0][2]
            old = self.bound_track_id
            self.bound_track_id = int(data[0])
            print(f"HUNTING_TARGET_REBOUND old={old} new={self.bound_track_id}", flush=True)
        if data is None:
            return None
        track_id, gx, gy, confidence, appearance = data
        self.last_gx, self.last_gy = gx, gy
        if appearance:
            self.bound_appearance = appearance
        return self._evidence(
            track_id,
            gx,
            gy,
            confidence,
            now,
            "FOREST_ALPHA6_BOUND_VISUAL",
            "BOUND_BODY_CONTINUITY",
        )

    @staticmethod
    def _evidence(track_id, gx, gy, confidence, now, source, reason) -> VisualEvidence:
        return VisualEvidence(
            timestamp=now,
            dx=gx,
            dy=gy,
            track_id=track_id,
            confidence=max(0.58, confidence),
            body_valid=True,
            source=source,
            combatant_verified=True,
            noncombatant=False,
            binding_reason=reason,
            entity_id=LOGICAL_FOREST_TARGET_ID,
            identity_confidence=0.96,
            hostility=1.0,
            network_fused=False,
        )

    def reset_fight(self) -> None:
        self.pending = None
        self.spawn_at = None
        self.spawn_line = ""
        self.spawn_name = ""
        self.bound_track_id = None
        self.bound_appearance = ()
        self._frozen = {}


__all__ = ["ForestSpawnBinder", "LOGICAL_FOREST_TARGET_ID"]
