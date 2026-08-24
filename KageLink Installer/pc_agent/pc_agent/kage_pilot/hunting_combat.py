from __future__ import annotations

import time

from pc_agent.kage_pilot.observer_runtime_v03 import V03ObserverConfig
from pc_agent.kage_pilot.particle_safe_grid_target_v03 import ParticleSafeGridTargetObserver
from pc_agent.kage_pilot.persistent_water_tracker_v03 import PersistentBackgroundWaterAwareEntityTracker

from .validated_combat_core import CombatV3State

DIRECTION_KEYS = {"UP": "up", "DOWN": "down", "LEFT": "left", "RIGHT": "right"}


def build_hunting_observer():
    config = V03ObserverConfig(
        player_x=0.5181,
        player_y=0.4706,
        player_exclusion_radius=19.0,
        player_box_width=18.0,
        player_box_height=38.0,
        enemy_threshold=55.0,
        target_acquire_threshold=55.0,
        target_keep_threshold=38.0,
        track_ttl_seconds=2.0,
        track_match_distance=105.0,
        dynamic_background_enabled=True,
        background_similarity=0.88,
        background_min_dense_hits=8.0,
        background_min_age=0.8,
        reacquire_ttl=5.0,
        reacquire_distance=180.0,
        reacquire_similarity=0.82,
    ).normalized()
    observer = ParticleSafeGridTargetObserver(
        config,
        tile_size=32.0,
        contact_lock_seconds=2.8,
        show_grid=False,
        contact_confirm_frames=2,
    )
    tracker = PersistentBackgroundWaterAwareEntityTracker(config)
    observer.tracker = tracker
    return observer, tracker


def tap(controller, key: str, seconds: float) -> None:
    controller.apply_keys((key,))
    time.sleep(seconds)
    controller.apply_keys(())


def execute_alpha6_combat(controller, core: CombatV3State, decision, now_wall: float, now_mono: float) -> None:
    """Physical cadence frozen from the field-validated Alpha 6 fight."""
    if not core.target_entity_id or core.victory:
        controller.release_all()
        return
    if not decision.hold_r:
        controller.release_all()
        return

    core.mark_r_physical(now_wall)
    controller.apply_keys(("r",))

    if decision.navigation.startswith("MOVE_"):
        key = DIRECTION_KEYS.get(decision.navigation[5:].upper())
        if key:
            core.authorize_input("MOVE", key, now_mono, 0.30)
            core.mark_move(now_wall, now_mono, None)
            controller.apply_keys(("r", key))
            time.sleep(0.040)
            controller.apply_keys(("r",))
        return

    if decision.state != "MELEE":
        return
    direction = decision.face
    key = DIRECTION_KEYS.get(direction)
    if key and (core.facing != direction or now_mono - core.facing_at > 1.4):
        core.authorize_input("FACE", key, now_mono, 0.35)
        controller.apply_keys(("r", "ctrl"))
        time.sleep(0.022)
        controller.apply_keys(("r", "ctrl", key))
        time.sleep(0.055)
        controller.apply_keys(("r",))
        core.facing = direction
        core.facing_at = now_mono
        return

    if decision.h_request and core.last_visual is not None and now_wall - core.last_visual.timestamp <= 0.70:
        core.authorize_input("H", "h", now_mono, 0.40)
        core.register_h(now_wall, now_mono)
        controller.apply_keys(("r", "h"))
        time.sleep(0.065)
        controller.apply_keys(("r",))


__all__ = ["DIRECTION_KEYS", "build_hunting_observer", "execute_alpha6_combat", "tap"]
