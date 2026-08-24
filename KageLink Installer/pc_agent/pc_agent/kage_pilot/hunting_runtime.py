"""Autonomous forest Hunting using the field-validated Alpha 6 contracts."""
from __future__ import annotations

import argparse
from pathlib import Path
import time

from pc_agent.config import load_config
from pc_agent.kage_pilot.dojo_fight_v03e import f12_pressed
from pc_agent.kage_pilot.entity_observer import decode_jpeg
from pc_agent.kage_pilot.pilot import WindowsGameController
from pc_agent.kage_pilot.post_combat_v03 import HudResourceReader
from pc_agent.kage_pilot.recorder import WindowsGameFrameSource

from .hunting_binder import ForestSpawnBinder, LOGICAL_FOREST_TARGET_ID
from .hunting_chat import HuntingChatEvent, HuntingChatWatcher
from .hunting_combat import build_hunting_observer, execute_alpha6_combat, tap
from .hunting_navigation import SceneMotionProbe
from .hunting_recovery import StaminaHudReader
from .validated_combat_core import CombatV3State


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kage_pilot_round.py --hunting")
    parser.add_argument("--walk-seconds", type=float, default=1.40)
    parser.add_argument("--combat-timeout", type=float, default=300.0)
    parser.add_argument("--recovery-timeout", type=float, default=600.0)
    parser.add_argument("--recovery-hp", type=float, default=0.90)
    parser.add_argument("--recovery-stamina", type=float, default=0.90)
    parser.add_argument("--chat-poll-seconds", type=float, default=0.10)
    parser.add_argument("--fps", type=float, default=12.0)
    parser.add_argument("--stop-file", type=Path, required=True)
    return parser


def _phase(name: str, *, direction: str = "-", kills: int = 0, detail: str = "") -> None:
    suffix = f" detail={detail}" if detail else ""
    print(f"HUNTING_PHASE phase={name} direction={direction} kills={kills}{suffix}", flush=True)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    app_config = load_config()
    source = WindowsGameFrameSource()
    controller = WindowsGameController(recover_foreground=False, debug=False)
    controller.repeat_keys = {"r"}
    observer, tracker = build_hunting_observer()
    chat = HuntingChatWatcher(app_config.game_title, app_config.chat_class)
    binder = ForestSpawnBinder()
    core = CombatV3State(runtime_at=time.time())
    health_reader = HudResourceReader()
    stamina_reader = StaminaHudReader()
    motion_probe = SceneMotionProbe()

    interval = 1.0 / max(4.0, min(20.0, float(args.fps)))
    chat_interval = max(0.08, min(1.0, float(args.chat_poll_seconds)))
    walk_seconds = max(0.50, min(10.0, float(args.walk_seconds)))
    combat_timeout = max(30.0, min(900.0, float(args.combat_timeout)))
    recovery_timeout = max(30.0, min(1800.0, float(args.recovery_timeout)))
    hp_target = max(0.90, min(1.0, float(args.recovery_hp)))
    stamina_target = max(0.90, min(1.0, float(args.recovery_stamina)))
    stop_file = Path(args.stop_file)

    phase = "searching"
    direction = "up"
    direction_since = time.monotonic()
    next_chat = time.monotonic()
    combat_started = -1e9
    recovery_started = -1e9
    recovery_hits = 0
    kills = 0
    meditation_active = False
    last_resource_emit = -1e9

    print("KAGE_HUNTING_RUNTIME_START version=FOREST_ALPHA6_HUNTING_2_STAMINA", flush=True)
    print(
        "HUNTING_RULE exact_ambush_chat_only; D<=3; two temporal body observations; "
        "preexisting bodies/players have no attack authority; V3.2 HF1 combat",
        flush=True,
    )
    print(
        "HUNTING_RECOVERY HP>=90% AND Stamina>=90%; "
        "Stamina visual reader calibrated from the fixed bar below HEALTH",
        flush=True,
    )

    try:
        controller.activate()
        controller.release_all()
        chat.prime()
        _phase("searching", direction=direction, kills=kills)

        while True:
            loop_started = time.monotonic()
            now_mono = loop_started
            now_wall = time.time()
            if stop_file.exists() or f12_pressed():
                _phase("stopping", direction=direction, kills=kills, detail="stop_requested")
                break

            events: list[HuntingChatEvent] = []
            if now_mono >= next_chat:
                events = chat.poll()
                next_chat = now_mono + chat_interval

            for event in events:
                if event.kind == "spawn":
                    if phase == "searching":
                        controller.release_all()
                        binder.on_spawn(event, now_wall)
                        core.on_materialization(now_wall)
                        phase = "acquiring"
                        print(f"HUNTING_ENEMY clan={event.clan} name={event.name}", flush=True)
                        _phase("acquiring", direction="-", kills=kills)
                    else:
                        print(f"HUNTING_SPAWN_IGNORED phase={phase} text={event.text}", flush=True)
                elif event.kind == "ko" and phase == "combat" and core.target_entity_id:
                    core.on_victory(now_wall)
                    controller.release_all()
                    kills += 1
                    print(f"HUNTING_VICTORY kills={kills} text={event.text}", flush=True)
                    phase = "recovery"
                    recovery_started = now_mono
                    recovery_hits = 0
                    tap(controller, "v", 0.080)
                    meditation_active = True
                    _phase("recovery", direction="-", kills=kills)

            captured = source.capture()
            frame = decode_jpeg(bytes(captured.jpeg))
            state = observer.process(frame)
            now_wall = time.time()
            now_mono = time.monotonic()

            if phase == "searching":
                binder.capture_prespawn(observer, tracker, state, now_wall)
                controller.apply_keys((direction,))
                moved = motion_probe.moved(frame, now_mono)
                timed_flip = now_mono - direction_since >= walk_seconds
                obstacle_flip = moved is False and now_mono - direction_since >= 0.65
                if timed_flip or obstacle_flip:
                    direction = "down" if direction == "up" else "up"
                    direction_since = now_mono
                    controller.apply_keys((direction,))
                    _phase(
                        "searching",
                        direction=direction,
                        kills=kills,
                        detail="obstacle_flip" if obstacle_flip else "timed_flip",
                    )

            elif phase == "acquiring":
                controller.release_all()
                evidence = binder.acquire(observer, tracker, state, now_wall)
                if evidence is not None:
                    core.on_identity(LOGICAL_FOREST_TARGET_ID, now_wall, 0.96, 1.0)
                    core.on_visual(evidence)
                    combat_started = now_mono
                    phase = "combat"
                    _phase("combat", direction="-", kills=kills)
                elif binder.acquisition_expired(now_wall):
                    print("HUNTING_ACQUIRE_TIMEOUT no body bound; return to passive search", flush=True)
                    binder.reset_fight()
                    core.reset(runtime_at=now_wall)
                    phase = "searching"
                    direction_since = now_mono
                    _phase("searching", direction=direction, kills=kills, detail="acquire_timeout")

            elif phase == "combat":
                evidence = binder.current(observer, tracker, state, now_wall)
                if evidence is not None:
                    core.on_visual(evidence)
                decision = core.decide(now_wall, now_mono)
                execute_alpha6_combat(controller, core, decision, now_wall, now_mono)
                if now_mono - combat_started > combat_timeout:
                    controller.release_all()
                    print("HUNTING_RUNTIME_ERROR combat_timeout", flush=True)
                    return 1

            elif phase == "recovery":
                controller.release_all()
                levels = health_reader.read(frame)
                stamina = stamina_reader.read(frame)
                hp = levels.health
                calibrated = bool(stamina_reader.calibrated)
                if now_mono - last_resource_emit >= 1.0:
                    hp_text = "-" if hp is None else f"{float(hp):.4f}"
                    stamina_text = "-" if stamina is None else f"{float(stamina):.4f}"
                    print(
                        f"HUNTING_RESOURCES hp={hp_text} stamina={stamina_text} "
                        f"stamina_calibrated={'true' if calibrated else 'false'}",
                        flush=True,
                    )
                    last_resource_emit = now_mono
                ready = bool(
                    calibrated
                    and hp is not None
                    and stamina is not None
                    and float(hp) >= hp_target
                    and float(stamina) >= stamina_target
                )
                recovery_hits = recovery_hits + 1 if ready else 0
                if recovery_hits >= 3:
                    if meditation_active:
                        tap(controller, "v", 0.080)
                        meditation_active = False
                    binder.reset_fight()
                    core.reset(runtime_at=now_wall)
                    phase = "searching"
                    direction_since = now_mono
                    _phase("searching", direction=direction, kills=kills, detail="recovered")
                elif now_mono - recovery_started > recovery_timeout:
                    print(
                        "HUNTING_RECOVERY_HOLD timeout_reached; "
                        "V remains active because HP/Stamina authority is not yet satisfied",
                        flush=True,
                    )
                    recovery_started = now_mono

            elapsed = time.monotonic() - loop_started
            if elapsed < interval:
                time.sleep(interval - elapsed)

        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(f"HUNTING_RUNTIME_ERROR {type(exc).__name__}:{exc}", flush=True)
        return 1
    finally:
        if meditation_active:
            try:
                tap(controller, "v", 0.080)
            except Exception:
                pass
        try:
            controller.release_all()
        except Exception:
            pass
        try:
            controller.close()
        except Exception:
            pass
        _phase("stopped", direction="-", kills=kills)


__all__ = ["main"]
