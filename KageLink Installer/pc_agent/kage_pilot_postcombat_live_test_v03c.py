from __future__ import annotations

import argparse
import ctypes
import time

from pc_agent.kage_pilot.entity_observer import decode_jpeg
from pc_agent.kage_pilot.observer_runtime_v03 import V03ObserverConfig
from pc_agent.kage_pilot.particle_safe_grid_target_v03 import ParticleSafeGridTargetObserver
from pc_agent.kage_pilot.persistent_water_tracker_v03 import (
    PersistentBackgroundWaterAwareEntityTracker,
)
from pc_agent.kage_pilot.pilot import WindowsGameController
from pc_agent.kage_pilot.post_combat_v03c import (
    PersistentDojoLeaderDetector,
    PostCombatRecoveryEngineV3,
)
from pc_agent.kage_pilot.recorder import WindowsGameFrameSource


DEFAULT_PLAYER_X = 0.5181
DEFAULT_PLAYER_Y = 0.4706
DEFAULT_GRID_SIZE = 32.0
VK_F12 = 0x7B


def _f12_pressed() -> bool:
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(VK_F12) & 0x8000)
    except Exception:
        return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Kage Pilot v0.3c isolated off-screen trainer return/search test / "
            "teste isolado de retorno e busca do treinador fora da tela"
        )
    )
    parser.add_argument("--seconds", type=float, default=60.0)
    parser.add_argument("--fps", type=float, default=8.0)
    parser.add_argument("--telemetry-seconds", type=float, default=0.50)
    parser.add_argument("--startup-delay", type=float, default=3.0)
    parser.add_argument("--move-pulse", type=float, default=0.09)
    parser.add_argument("--v-pulse", type=float, default=0.08)
    parser.add_argument("--leader-threshold", type=float, default=0.88)
    parser.add_argument("--leader-confirm-frames", type=int, default=2)
    parser.add_argument("--recovery-hp", type=float, default=0.90)
    parser.add_argument("--recovery-chakra", type=float, default=0.50)
    parser.add_argument("--recovery-confirm-frames", type=int, default=3)
    parser.add_argument("--search-delay", type=float, default=0.75)
    parser.add_argument("--search-timeout", type=float, default=45.0)
    parser.add_argument("--search-pulses-per-tile", type=int, default=4)
    parser.add_argument("--search-radius", type=int, default=8)
    parser.add_argument("--player-x", type=float, default=DEFAULT_PLAYER_X)
    parser.add_argument("--player-y", type=float, default=DEFAULT_PLAYER_Y)
    parser.add_argument("--player-box-width", type=float, default=18.0)
    parser.add_argument("--player-box-height", type=float, default=38.0)
    parser.add_argument("--grid-size", type=float, default=DEFAULT_GRID_SIZE)
    parser.add_argument("--debug-input", action="store_true")
    return parser


def _line(decision) -> str:
    score = "-" if decision.leader_score is None else f"{decision.leader_score:.3f}"
    distance = "-" if decision.leader_distance is None else str(decision.leader_distance)
    hp = "-" if decision.health is None else f"{decision.health * 100:.0f}%"
    chakra = "-" if decision.chakra is None else f"{decision.chakra * 100:.0f}%"
    move = decision.move_pulse or "-"
    v_text = "V_TAP" if decision.tap_v else "V_WAIT"
    return (
        f"POST {decision.state} leader_score={score} d={distance} "
        f"move_pulse={move} {v_text} HP={hp} Chakra={chakra} reason={decision.reason}"
    )


def main() -> int:
    args = build_parser().parse_args()
    observer_config = V03ObserverConfig(
        player_x=args.player_x,
        player_y=args.player_y,
        player_exclusion_radius=max(args.player_box_width, args.player_box_height) / 2.0,
        player_box_width=args.player_box_width,
        player_box_height=args.player_box_height,
        dynamic_background_enabled=True,
    ).normalized()
    observer = ParticleSafeGridTargetObserver(
        observer_config,
        tile_size=args.grid_size,
        contact_lock_seconds=2.8,
        show_grid=False,
        contact_confirm_frames=2,
    )
    observer.tracker = PersistentBackgroundWaterAwareEntityTracker(observer_config)

    leader = PersistentDojoLeaderDetector(threshold=args.leader_threshold)
    engine = PostCombatRecoveryEngineV3(
        leader_detector=leader,
        leader_confirm_frames=args.leader_confirm_frames,
        health_target=args.recovery_hp,
        chakra_target=args.recovery_chakra,
        recovery_confirm_frames=args.recovery_confirm_frames,
        search_delay_seconds=args.search_delay,
        search_timeout_seconds=args.search_timeout,
        search_pulses_per_tile=args.search_pulses_per_tile,
        search_max_radius_tiles=args.search_radius,
    )
    source = WindowsGameFrameSource()
    controller = WindowsGameController(recover_foreground=False, debug=bool(args.debug_input))
    controller.repeat_keys = set()

    interval = 1.0 / max(1.0, min(20.0, float(args.fps)))
    telemetry_interval = max(0.10, float(args.telemetry_seconds))
    startup_delay = max(0.0, float(args.startup_delay))
    move_pulse_seconds = max(0.03, min(0.14, float(args.move_pulse)))
    v_pulse_seconds = max(0.03, min(0.20, float(args.v_pulse)))
    timeout = max(5.0, float(args.seconds))

    print("Kage Pilot v0.3c OFF-SCREEN TRAINER SEARCH TEST")
    print("NO R / NO H - DEAD-MAN ARROWS + V TOGGLE ONLY")
    print("ANCHOR IF AVAILABLE; OTHERWISE BOUNDED EXPANDING-SQUARE SEARCH")
    print(f"LEADER TEMPLATE: {leader.template_source} -> {leader.template_path}")
    print("Start NOT meditating / Inicie FORA da meditacao")
    print("F12 = EMERGENCY STOP / PARADA IMEDIATA")

    started = 0.0
    next_telemetry = 0.0
    ready = False
    try:
        controller.activate()
        controller.release_all()
        if startup_delay > 0:
            print(f"Control starts in / Controle inicia em {startup_delay:.1f}s")
            time.sleep(startup_delay)

        started = time.monotonic()
        next_telemetry = started
        while time.monotonic() - started < timeout:
            loop_started = time.monotonic()
            if _f12_pressed():
                print("F12 STOP / PARADA F12")
                break

            frame = decode_jpeg(bytes(source.capture().jpeg))
            state = observer.process(frame)
            now = time.monotonic()
            decision = engine.step(frame, state, observer, now=now)

            # Absolute safety invariant: no persistent post-combat key state.
            controller.apply_keys(())
            if decision.move_pulse is not None:
                controller.apply_keys((decision.move_pulse,))
                time.sleep(move_pulse_seconds)
                controller.apply_keys(())
            if decision.tap_v:
                controller.tap("v", v_pulse_seconds)

            if now >= next_telemetry or decision.tap_v:
                print(_line(decision))
                next_telemetry = now + telemetry_interval

            if decision.state == "READY":
                ready = True
                print("OFFSCREEN_SEARCH_TEST_OK / TESTE_BUSCA_FORA_DA_TELA_OK")
                break

            elapsed = time.monotonic() - loop_started
            if elapsed < interval:
                time.sleep(interval - elapsed)
    except KeyboardInterrupt:
        print("Keyboard interrupt / Interrupcao de teclado")
    except Exception as exc:
        print(f"SEARCH TEST STOPPED / TESTE INTERROMPIDO: {type(exc).__name__}: {exc}")
    finally:
        controller.release_all()
        source.close()

    if not ready:
        print(f"OFFSCREEN_SEARCH_TEST_INCOMPLETE state={engine.state}")
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
