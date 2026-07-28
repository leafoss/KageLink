from __future__ import annotations

import argparse
from pathlib import Path
import time

from pc_agent.kage_pilot.dojo_training import (
    DojoTrainingConfig,
    DojoTrainingPhase,
    DojoTrainingService,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Kage Pilot Dojo training: stable public entry point over the validated v0.3i loop / "
            "treinamento no Dojo: entrada publica estavel sobre o loop v0.3i validado"
        )
    )
    parser.add_argument("--rounds", type=int, default=1, help="0 = continuous until stop/F12")
    parser.add_argument("--combat-seconds", type=float, default=120.0)
    parser.add_argument("--post-combat-timeout", type=float, default=240.0)
    parser.add_argument("--dialog-delay", type=float, default=5.0)
    parser.add_argument("--dialog-timeout", type=float, default=6.0)
    parser.add_argument("--spawn-delay", type=float, default=5.0)
    parser.add_argument("--trainer-search-timeout", type=float, default=90.0)
    parser.add_argument("--leader-threshold", type=float, default=0.88)
    parser.add_argument("--round-startup-delay", type=float, default=1.0)
    parser.add_argument("--chat-poll-seconds", type=float, default=0.15)
    parser.add_argument("--log-dir", type=Path, default=Path("kage_pilot_loop_logs"))
    parser.add_argument("--disable-h", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = DojoTrainingConfig(
        rounds=args.rounds,
        combat_seconds=args.combat_seconds,
        post_combat_timeout=args.post_combat_timeout,
        dialog_delay=args.dialog_delay,
        dialog_timeout=args.dialog_timeout,
        spawn_delay=args.spawn_delay,
        trainer_search_timeout=args.trainer_search_timeout,
        leader_threshold=args.leader_threshold,
        round_startup_delay=args.round_startup_delay,
        chat_poll_seconds=args.chat_poll_seconds,
        log_dir=args.log_dir,
        disable_h=args.disable_h,
    )
    service = DojoTrainingService()

    print("Kage Pilot Dojo - STABLE ENTRY POINT / ENTRADA ESTAVEL")
    print("Validated engine: v0.3i / motor validado: v0.3i")
    print("F12 or Ctrl+C = stop / parar")

    started = service.start(config, on_output=print)
    if not started:
        snapshot = service.snapshot()
        print(f"DOJO_START_FAILED: {snapshot.last_error or 'ALREADY_RUNNING'}")
        return 1

    try:
        while service.is_running:
            time.sleep(0.20)
    except KeyboardInterrupt:
        print("DOJO_STOP_REQUESTED / PARADA_SOLICITADA")
        service.stop()

    snapshot = service.wait(timeout=1.0)
    print(
        f"DOJO_FINAL phase={snapshot.phase.value} completed={snapshot.completed_rounds} "
        f"return_code={snapshot.return_code}"
    )
    return 1 if snapshot.phase == DojoTrainingPhase.ERROR else 0


if __name__ == "__main__":
    raise SystemExit(main())
