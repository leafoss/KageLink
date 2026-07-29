from __future__ import annotations

import time

import kage_pilot_live_v03 as live_v03
import kage_pilot_live_v03e_round as round_v03e
import kage_pilot_live_v03g_round as round_v03g
import kage_pilot_live_v03h_round as round_v03h

from pc_agent.kage_pilot.live_control_v03 import LiveControlCommand, MotionBurstState
from pc_agent.kage_pilot.post_combat_v03h import VisualProgressPostCombatRecoveryEngine


class _MapSaveResyncCoordinator:
    def __init__(self) -> None:
        self.generation = 0
        self.active_until = -1e9
        self.reason = ""

    def trigger(self, reason: str, *, now: float, hold_seconds: float = 1.25) -> None:
        now = float(now)
        if now >= self.active_until:
            self.generation += 1
            print(
                f"MAP_SAVE_RESYNC trigger={reason} generation={self.generation} "
                f"/ RESSINCRONIZAR_APOS_SALVAMENTO"
            )
        self.reason = str(reason)
        self.active_until = max(self.active_until, now + max(0.50, float(hold_seconds)))

    def active(self, *, now: float | None = None) -> bool:
        value = time.monotonic() if now is None else float(now)
        return value < self.active_until


_RESYNC = _MapSaveResyncCoordinator()
_PREVIOUS_OBSERVER = live_v03.ParticleSafeGridTargetObserver
_PREVIOUS_ENGINE = live_v03.ShadowCombatDecisionEngine
_PREVIOUS_GUARD = live_v03.MotionBurstGuard
_PREVIOUS_PLANNER = live_v03.LiveCombatControlPlanner
_PREVIOUS_CONTROLLER = live_v03.WindowsGameController
_PREVIOUS_POST_LINE = live_v03._post_line


class MapSaveResyncObserver(_PREVIOUS_OBSERVER):
    """Discard stale identities after a real capture stall or a sustained scene reset."""

    def __init__(self, *args, frame_gap_seconds: float = 1.25, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.frame_gap_seconds = max(0.75, min(5.0, float(frame_gap_seconds)))
        self._last_process_wall: float | None = None
        self._resync_generation = _RESYNC.generation

    def _apply_resync_if_needed(self) -> None:
        if self._resync_generation == _RESYNC.generation:
            return
        self._resync_generation = _RESYNC.generation
        tracker = getattr(self, "tracker", None)
        if tracker is not None and hasattr(tracker, "full_reset"):
            tracker.full_reset()
        super().reset()
        request_realign = getattr(self, "request_grid_realign", None)
        if callable(request_realign):
            request_realign()

    def process(self, frame_bgr, *, timestamp=None):
        now = time.monotonic()
        if self._last_process_wall is not None:
            gap = now - self._last_process_wall
            if gap >= self.frame_gap_seconds:
                _RESYNC.trigger(f"frame_gap={gap:.2f}s", now=now)
        self._last_process_wall = now
        self._apply_resync_if_needed()
        return super().process(frame_bgr, timestamp=timestamp)


class MapSaveResyncDecisionEngine(_PREVIOUS_ENGINE):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._resync_generation = _RESYNC.generation

    def decide(self, *args, **kwargs):
        if self._resync_generation != _RESYNC.generation:
            self._resync_generation = _RESYNC.generation
            self.reset()
        return super().decide(*args, **kwargs)


class MapSaveResyncMotionBurstGuard(_PREVIOUS_GUARD):
    """Turn an implausibly long whole-scene burst into a clean perception resync."""

    def __init__(
        self,
        *args,
        sustained_spike_seconds: float = 4.0,
        sustained_active_cells: int = 40,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.sustained_spike_seconds = max(2.0, min(12.0, float(sustained_spike_seconds)))
        self.sustained_active_cells = max(24, int(sustained_active_cells))
        self._spike_since: float | None = None
        self._resync_generation = _RESYNC.generation

    def update(self, *, active_cells: int, entities: int, now: float):
        now = float(now)
        if self._resync_generation != _RESYNC.generation:
            self._resync_generation = _RESYNC.generation
            self.reset()
            self._spike_since = None

        if _RESYNC.active(now=now):
            return MotionBurstState(
                blocked=True,
                reason=f"map_save_resync:{_RESYNC.reason}",
                active_cells=max(0, int(active_cells)),
                entities=max(0, int(entities)),
                baseline_active_cells=float(self._baseline_active or 1.0),
                baseline_entities=float(self._baseline_entities or 1.0),
            )

        state = super().update(active_cells=active_cells, entities=entities, now=now)
        sustained_candidate = (
            state.blocked
            and int(active_cells) >= self.sustained_active_cells
            and "active_cells_spike" in state.reason
        )
        if sustained_candidate:
            if self._spike_since is None:
                self._spike_since = now
            elif now - self._spike_since >= self.sustained_spike_seconds:
                _RESYNC.trigger(
                    f"sustained_active_cells={int(active_cells)}",
                    now=now,
                    hold_seconds=1.25,
                )
                self._resync_generation = _RESYNC.generation
                self.reset()
                self._spike_since = None
                return MotionBurstState(
                    blocked=True,
                    reason="map_save_resync:sustained_scene_spike",
                    active_cells=max(0, int(active_cells)),
                    entities=max(0, int(entities)),
                    baseline_active_cells=1.0,
                    baseline_entities=1.0,
                )
        else:
            self._spike_since = None
        return state


class MapSaveResyncPlanner(_PREVIOUS_PLANNER):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._resync_generation = _RESYNC.generation

    def plan(self, decision, *, now: float, movement_allowed: bool = True, block_reason: str = ""):
        if self._resync_generation != _RESYNC.generation:
            self._resync_generation = _RESYNC.generation
            self.reset()
        if _RESYNC.active(now=now):
            return LiveControlCommand(
                held_keys=(),
                face_pulse=None,
                h_shadow_ready=False,
                reason=(
                    f"map-save resync; release all and reacquire / "
                    f"ressincronizacao; soltar tudo e readquirir: {_RESYNC.reason}"
                ),
                move_pulse=None,
                h_fire=False,
                safety_state="MAP_SAVE_RESYNC",
            )
        return super().plan(
            decision,
            now=now,
            movement_allowed=movement_allowed,
            block_reason=block_reason,
        )


class FastChakraVisualRecoveryEngine(round_v03h.ActiveVisualProgressRecoveryEngine):
    """Toggle Y once when only Chakra remains, then toggle it off at the Chakra threshold."""

    def __init__(self, *args, y_confirm_frames: int = 2, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.y_confirm_frames = max(1, min(5, int(y_confirm_frames)))
        self.y_fast_active = False
        self.pending_y_action: str | None = None
        self._y_on_hits = 0
        self._y_off_hits = 0
        self.last_y_action = "-"

    def _update_fast_chakra(self, decision) -> None:
        if self.pending_y_action is not None:
            return
        health = decision.health
        chakra = decision.chakra
        if health is None or chakra is None:
            return

        hp = float(health)
        ch = float(chakra)
        if self.y_fast_active:
            if ch >= self.chakra_target:
                self._y_off_hits += 1
            else:
                self._y_off_hits = 0
            if decision.state == "READY" or self._y_off_hits >= self.y_confirm_frames:
                self.pending_y_action = "off"
                self._y_off_hits = 0
            return

        # Strictly greater than 90% HP, as requested. Y is never used while HP still needs recovery.
        if decision.state == "MEDITATING" and hp > self.health_target and ch < self.chakra_target:
            self._y_on_hits += 1
        else:
            self._y_on_hits = 0
        if self._y_on_hits >= self.y_confirm_frames:
            self.pending_y_action = "on"
            self._y_on_hits = 0

    def step(self, *args, **kwargs):
        decision = super().step(*args, **kwargs)
        self._update_fast_chakra(decision)
        return decision

    def consume_y_action(self) -> str | None:
        action = self.pending_y_action
        self.pending_y_action = None
        if action == "on":
            self.y_fast_active = True
            self.last_y_action = "ON"
        elif action == "off":
            self.y_fast_active = False
            self.last_y_action = "OFF"
        return action

    def mark_y_forced_off(self) -> None:
        self.pending_y_action = None
        self.y_fast_active = False
        self._y_on_hits = 0
        self._y_off_hits = 0
        self.last_y_action = "OFF_CLEANUP"


class ResyncAndFastChakraController(_PREVIOUS_CONTROLLER):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._consuming_y = False

    def _tap_y_direct(self) -> None:
        self._consuming_y = True
        try:
            super().apply_keys(("y",))
            time.sleep(0.08)
            super().apply_keys(())
        finally:
            self._consuming_y = False

    def apply_keys(self, keys: tuple[str, ...]) -> None:
        super().apply_keys(keys)
        if self._consuming_y or keys:
            return
        engine = round_v03e._ACTIVE_RECOVERY_ENGINE
        if not isinstance(engine, FastChakraVisualRecoveryEngine) or not engine.post_started:
            return
        action = engine.consume_y_action()
        if action is None:
            return
        self._tap_y_direct()
        print(
            "POST Y_FAST_ON / Y_RAPIDO_LIGADO"
            if action == "on"
            else "POST Y_FAST_OFF / Y_RAPIDO_DESLIGADO"
        )

    def close(self) -> None:
        engine = round_v03e._ACTIVE_RECOVERY_ENGINE
        if isinstance(engine, FastChakraVisualRecoveryEngine) and engine.y_fast_active:
            try:
                self._tap_y_direct()
                print("POST Y_FAST_OFF_CLEANUP / Y_RAPIDO_DESLIGADO_NA_LIMPEZA")
            except Exception:
                pass
            engine.mark_y_forced_off()
        super().close()


def _post_line_with_y(decision) -> str:
    text = _PREVIOUS_POST_LINE(decision)
    engine = round_v03e._ACTIVE_RECOVERY_ENGINE
    if not isinstance(engine, FastChakraVisualRecoveryEngine):
        return text
    status = "ON" if engine.y_fast_active else "OFF"
    pending = engine.pending_y_action or "-"
    return text + f" Y_FAST={status} Y_PENDING={pending}"


# v0.3h combat inference is preserved. These patches add only map-save recovery, strict
# post-combat Y toggling and their telemetry.
live_v03.ParticleSafeGridTargetObserver = MapSaveResyncObserver
live_v03.ShadowCombatDecisionEngine = MapSaveResyncDecisionEngine
live_v03.MotionBurstGuard = MapSaveResyncMotionBurstGuard
live_v03.LiveCombatControlPlanner = MapSaveResyncPlanner
live_v03.PostCombatRecoveryEngine = FastChakraVisualRecoveryEngine
live_v03.WindowsGameController = ResyncAndFastChakraController
live_v03._post_line = _post_line_with_y


def main() -> int:
    print("Kage Pilot v0.3i ROUND: MAP-SAVE RESYNC + FAST CHAKRA Y TOGGLE")
    print("STALL/SUSTAINED SCENE SPIKE -> RELEASE ALL -> RESET TARGET/FACING -> REACQUIRE")
    print("POST: HP>90% and Chakra<50% -> Y ON once; Chakra>=50% -> Y OFF once")
    return round_v03g.main()


if __name__ == "__main__":
    raise SystemExit(main())
