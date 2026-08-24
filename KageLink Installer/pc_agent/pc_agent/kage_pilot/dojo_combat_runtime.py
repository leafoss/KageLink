"""Dojo combat-action overlay using the physically validated Alpha 6 V3.2 HF1 core.

The Dojo remains authoritative for request, spawn/target identity, KO acceptance,
return to Trainer and recovery. This module replaces only the action policy after
the existing Dojo observer exposes a current visual opponent.
"""
from __future__ import annotations

from dataclasses import replace
import sys
import time

import kage_pilot_live_v03 as live_runtime
import kage_pilot_live_v03k_round as dojo_round

from .validated_combat_core import CombatV3State, VisualEvidence

_BASE_WATCHER = live_runtime.ChatVictoryWatcher
_BASE_ENGINE = live_runtime.ShadowCombatDecisionEngine
_BASE_PLANNER = live_runtime.LiveCombatControlPlanner
_BASE_BURST_GUARD = live_runtime.MotionBurstGuard
_BASE_CONTROLLER = live_runtime.WindowsGameController
_BASE_REJECT_CURRENT_TARGET = dojo_round._reject_current_target

_ALPHA6 = CombatV3State()
_LOGICAL_TARGET_ID = "DOJO_CURRENT_OPPONENT"
_CURRENT_TRACK_ID: int | None = None
_CURRENT_VISUAL_MODES = {"VISIBLE", "OCCLUDED", "CONTACT_REBIND"}
_DIRECTION_KEYS = {"UP": "up", "DOWN": "down", "LEFT": "left", "RIGHT": "right"}


def _arm_combat() -> None:
    global _CURRENT_TRACK_ID
    now = time.time()
    _ALPHA6.reset(runtime_at=now)
    # The isolated round starts only after the existing Dojo request/spawn flow.
    # Materialization arms acquisition but does not grant R/move/H authority.
    _ALPHA6.on_materialization(now)
    _CURRENT_TRACK_ID = None


def _reject_current_target() -> None:
    _BASE_REJECT_CURRENT_TARGET()
    _arm_combat()


def _current_body_allowed(now_wall: float) -> bool:
    visual = _ALPHA6.last_visual
    return bool(
        visual
        and visual.combatant_verified
        and not visual.noncombatant
        and visual.entity_id == _LOGICAL_TARGET_ID
        and visual.track_id == _CURRENT_TRACK_ID
        and 0.0 <= float(now_wall) - float(visual.timestamp) <= 0.70
    )


def _feed_existing_dojo_target(state, observer) -> None:
    """Convert the current Dojo-selected body into Alpha 6 geometry; never select a target."""
    global _CURRENT_TRACK_ID

    target = getattr(state, "target", None)
    if target is None:
        return
    track_id = getattr(target, "track_id", None)
    if track_id is None:
        return
    target_mode = str(getattr(observer, "target_mode", "NONE") or "NONE").upper()
    if target_mode not in _CURRENT_VISUAL_MODES:
        return
    try:
        metrics = observer.metrics_for(track_id)
        dx = int(metrics.cell[0] - metrics.player_cell[0])
        dy = int(metrics.cell[1] - metrics.player_cell[1])
    except Exception:
        return
    try:
        score = float(getattr(target, "enemy_score", 75.0) or 0.0)
    except Exception:
        score = 75.0
    confidence = max(0.58, min(0.98, score / 100.0))
    now_wall = time.time()
    if _ALPHA6.target_entity_id is None:
        # Dojo already established that this is the current opponent.
        _ALPHA6.on_identity(_LOGICAL_TARGET_ID, now_wall, 1.0, 1.0)
    _CURRENT_TRACK_ID = int(track_id)
    _ALPHA6.on_visual(
        VisualEvidence(
            timestamp=now_wall,
            dx=dx,
            dy=dy,
            track_id=int(track_id),
            confidence=confidence,
            body_valid=True,
            source="DOJO_CURRENT_TARGET",
            combatant_verified=True,
            noncombatant=False,
            binding_reason="EXISTING_DOJO_TARGET_AUTHORITY",
            entity_id=_LOGICAL_TARGET_ID,
            identity_confidence=1.0,
            hostility=1.0,
            network_fused=False,
        )
    )


class Alpha6DojoVictoryWatcher(_BASE_WATCHER):
    """Preserve the existing Dojo KO gate; only notify the combat core after acceptance."""
    def poll(self):
        signal = super().poll()
        if signal is not None:
            _ALPHA6.on_victory(time.time())
        return signal


class Alpha6DojoCombatEngine(_BASE_ENGINE):
    """Existing Dojo target authority in; exact Alpha 6 combat decision out."""
    def decide(self, state, observer, tracker, *, now: float, skills_allowed: bool = True):
        # The existing engine still performs target/KO-evidence side effects. Disallowing skills
        # here prevents it from consuming an H opportunity that Alpha 6 now owns.
        base = super().decide(state, observer, tracker, now=now, skills_allowed=False)
        _feed_existing_dojo_target(state, observer)
        wall = time.time()
        alpha = _ALPHA6.decide(wall, float(now))
        if _ALPHA6.engaged and not _ALPHA6.victory and not _ALPHA6.target_entity_id:
            alpha = replace(
                alpha,
                state="ACQUIRE",
                hold_r=False,
                navigation="HOLD",
                face="-",
                h_request=False,
                geometry=None,
                reason="Dojo round armed; waiting existing Dojo target authority; physical inputs OFF",
            )
        geometry = alpha.geometry
        return replace(
            base,
            mode=f"COMBAT_V3_{alpha.state}",
            target_id=(geometry.track_id if geometry is not None else None),
            navigation=alpha.navigation,
            face=alpha.face,
            grid_distance=(geometry.distance() if geometry is not None else None),
            base_r=alpha.hold_r,
            engagement_active=alpha.hold_r,
            h_opportunity=bool(alpha.h_request and skills_allowed),
            reason=alpha.reason,
        )


class Alpha6DojoPlanner(_BASE_PLANNER):
    """Map Alpha 6 decisions to the existing runtime command shape without old action policy."""
    def plan(self, decision, *, now: float, movement_allowed: bool = True, block_reason: str = ""):
        # Keep the inherited command type/configuration, but veto its old movement/H policy.
        command = super().plan(
            decision,
            now=now,
            movement_allowed=False,
            block_reason="alpha6_combat_action_owner",
        )
        wall = time.time()
        mono = float(now)
        alpha = _ALPHA6.decide(wall, mono)
        target_bound = bool(_ALPHA6.target_entity_id and not _ALPHA6.victory)
        held = {"r"} if target_bound and alpha.hold_r else set()

        if not target_bound:
            return replace(
                command,
                held_keys=(), face_pulse=None, move_pulse=None,
                h_fire=False, h_shadow_ready=False,
                safety_state="COMBAT_V3_ACQUIRE",
                reason="Dojo round armed; waiting existing Dojo target authority; physical inputs OFF",
            )

        geometry = alpha.geometry
        direction = alpha.face if alpha.face in _DIRECTION_KEYS else (
            geometry.direction() if geometry is not None else "-"
        )

        if alpha.navigation.startswith("MOVE_") and movement_allowed:
            key = _DIRECTION_KEYS.get(alpha.navigation[5:].upper())
            if key:
                _ALPHA6.authorize_input("MOVE", key, mono, 0.30)
                _ALPHA6.mark_move(wall, mono, None)
                return replace(
                    command,
                    held_keys=tuple(sorted(held)), face_pulse=None, move_pulse=key,
                    h_fire=False, h_shadow_ready=False,
                    safety_state="COMBAT_V3_ONE_TILE", reason=alpha.reason,
                )

        if alpha.state == "MELEE":
            key = _DIRECTION_KEYS.get(direction)
            if key and (_ALPHA6.facing != direction or mono - _ALPHA6.facing_at > 1.4):
                _ALPHA6.face_pending = key
                _ALPHA6.authorize_input("FACE", key, mono, 0.35)
                return replace(
                    command,
                    held_keys=tuple(sorted(held)), face_pulse=key, move_pulse=None,
                    h_fire=False, h_shadow_ready=False,
                    safety_state="COMBAT_V3_FACE",
                    reason="explicit CTRL+direction face before current Dojo-target H",
                )
            if alpha.h_request and bool(getattr(self, "h_enabled", True)):
                if not _current_body_allowed(wall):
                    return replace(
                        command,
                        held_keys=tuple(sorted(held)), face_pulse=None, move_pulse=None,
                        h_fire=False, h_shadow_ready=False,
                        safety_state="COMBAT_V3_H_TARGET_VETO",
                        reason="current Dojo-authorized visual body required for H",
                    )
                _ALPHA6.authorize_input("H", "h", mono, 0.40)
                _ALPHA6.register_h(wall, mono)
                return replace(
                    command,
                    held_keys=tuple(sorted(held)), face_pulse=None, move_pulse=None,
                    h_fire=True, h_shadow_ready=True,
                    safety_state="COMBAT_V3_H_FIRE",
                    reason="current Dojo target in cardinal line; Alpha 6 frequent H cadence",
                )

        return replace(
            command,
            held_keys=tuple(sorted(held)), face_pulse=None, move_pulse=None,
            h_fire=False, h_shadow_ready=False,
            safety_state=f"COMBAT_V3_{alpha.state}", reason=alpha.reason,
        )


class Alpha6DojoBurstGuard(_BASE_BURST_GUARD):
    """Match Alpha 6: particles are telemetry and cannot own target/action authority."""
    def update(self, *args, **kwargs):
        raw = super().update(*args, **kwargs)
        return replace(raw, blocked=False, reason="alpha6_bound_target_identity_not_owned_by_particles")


class Alpha6DojoController(_BASE_CONTROLLER):
    """Exact Alpha 6 movement/facing ownership while combat is active; old controller after KO."""
    def apply_keys(self, keys):
        raw = {str(key).lower() for key in keys if str(key).strip()}
        desired = set(raw)
        mono = time.monotonic()
        combat = bool(_ALPHA6.engaged and not _ALPHA6.victory and _ALPHA6.target_entity_id)
        if combat:
            desired.add("r")
            if _ALPHA6.r_physical_at is None:
                _ALPHA6.mark_r_physical(time.time())
                print("ALPHA6_DOJO_R_PHYSICAL_ASSERT")
        pending = _ALPHA6.face_pending
        cardinals = desired & {"up", "down", "left", "right"}
        if combat and cardinals:
            if len(cardinals) != 1:
                desired -= cardinals
                desired.discard("ctrl")
                return super().apply_keys(tuple(sorted(desired)))
            card = next(iter(cardinals))
            face_ok = bool(pending == card and _ALPHA6.input_allowed("FACE", card, mono, consume=True))
            move_ok = bool(not face_ok and _ALPHA6.input_allowed("MOVE", card, mono, consume=True))
            if face_ok:
                base = tuple(sorted(desired - {card, "ctrl"}))
                super().apply_keys(tuple(sorted(set(base) | {"ctrl"})))
                time.sleep(0.022)
                result = super().apply_keys(tuple(sorted(set(base) | {"ctrl", card})))
                _ALPHA6.face_pending = None
                _ALPHA6.facing = {"up": "UP", "down": "DOWN", "left": "LEFT", "right": "RIGHT"}[card]
                _ALPHA6.facing_at = mono
                return result
            if move_ok:
                without = tuple(sorted(desired - cardinals - {"ctrl"}))
                super().apply_keys(tuple(sorted(desired - {"ctrl"})))
                time.sleep(0.040)
                result = super().apply_keys(without)
                _ALPHA6.facing = {"up": "UP", "down": "DOWN", "left": "LEFT", "right": "RIGHT"}[card]
                _ALPHA6.facing_at = mono
                return result
            desired -= cardinals
            desired.discard("ctrl")
            return super().apply_keys(tuple(sorted(desired)))
        if combat and "ctrl" in desired:
            desired.discard("ctrl")
        return super().apply_keys(tuple(sorted(desired)))


# Patch only the isolated round process. No long-lived PC Agent module imports this overlay.
dojo_round._reject_current_target = _reject_current_target
live_runtime.ChatVictoryWatcher = Alpha6DojoVictoryWatcher
live_runtime.ShadowCombatDecisionEngine = Alpha6DojoCombatEngine
live_runtime.LiveCombatControlPlanner = Alpha6DojoPlanner
live_runtime.MotionBurstGuard = Alpha6DojoBurstGuard
live_runtime.WindowsGameController = Alpha6DojoController


def _set_runtime_arg(values: list[str], name: str, value: str) -> None:
    if name in values:
        index = values.index(name)
        if index + 1 < len(values):
            values[index + 1] = str(value)
        return
    values.extend([name, str(value)])


def _apply_alpha6_combat_timing(argv: list[str]) -> list[str]:
    """Freeze only combat timings that materially shaped the validated Alpha 6 fight."""
    values = list(argv)
    _set_runtime_arg(values, "--fps", "12")
    _set_runtime_arg(values, "--telemetry-seconds", "0.20")
    _set_runtime_arg(values, "--move-pulse", "0.040")
    return values


def main() -> int:
    sys.argv = [sys.argv[0], *_apply_alpha6_combat_timing(sys.argv[1:])]
    _arm_combat()
    print("Kage Pilot ROUND: EXISTING DOJO FLOW + VALIDATED ALPHA 6 COMBAT CORE")
    print("DOJO FLOW PRESERVED: request/spawn identity before combat; KO/return/recovery after combat")
    print("COMBAT: V3.2 HF1 Alpha 6 cadence; R + 40ms pursuit + CTRL facing + frequent H")
    print("COMBAT TARGET: existing Dojo observer remains the sole target/birth authority")
    return dojo_round.main()


__all__ = ["main"]
