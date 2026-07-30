from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
import time

from pc_agent.kage_pilot import DojoTrainingConfig, DojoTrainingPhase, DojoTrainingService
from pc_agent.kage_pilot.cli import main as tools_main

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config" / "kage_pilot_dojo.json"
TOOLS_COMMANDS = {
    "record", "mark", "train", "train-v2", "pilot", "pilot-v2",
    "capture-template", "init-config", "dojo-v2",
}


def build_dojo_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kage_pilot.py dojo",
        description=(
            "Kage Pilot Dojo training through the canonical KageLink 3.5 surface / "
            "treinamento no Dojo pela superficie canonica do KageLink 3.5"
        ),
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--show-config", action="store_true")
    parser.add_argument("--rounds", type=int, default=None, help="0 = continuous until stop/F12")
    parser.add_argument("--combat-seconds", type=float, default=None)
    parser.add_argument("--post-combat-timeout", type=float, default=None)
    parser.add_argument("--dialog-delay", type=float, default=None)
    parser.add_argument("--dialog-timeout", type=float, default=None)
    parser.add_argument("--spawn-delay", type=float, default=None)
    parser.add_argument("--trainer-search-timeout", type=float, default=None)
    parser.add_argument("--recovery-hp-percent", type=float, default=None)
    parser.add_argument("--recovery-chakra-percent", type=float, default=None)
    parser.add_argument("--leader-threshold", type=float, default=None)
    parser.add_argument("--round-startup-delay", type=float, default=None)
    parser.add_argument("--chat-poll-seconds", type=float, default=None)
    parser.add_argument("--log-dir", type=Path, default=None)
    h_group = parser.add_mutually_exclusive_group()
    h_group.add_argument("--enable-h", dest="h_enabled", action="store_true")
    h_group.add_argument("--disable-h", dest="h_enabled", action="store_false")
    parser.set_defaults(h_enabled=None)
    return parser


def resolve_dojo_config(args: argparse.Namespace) -> DojoTrainingConfig:
    value = DojoTrainingConfig.load_json(args.config)
    overrides = {}
    for argument, field in (
        ("rounds", "rounds"),
        ("combat_seconds", "combat_seconds"),
        ("post_combat_timeout", "post_combat_timeout"),
        ("dialog_delay", "dialog_delay"),
        ("dialog_timeout", "dialog_timeout"),
        ("spawn_delay", "spawn_delay"),
        ("trainer_search_timeout", "trainer_search_timeout"),
        ("recovery_hp_percent", "recovery_hp_percent"),
        ("recovery_chakra_percent", "recovery_chakra_percent"),
        ("leader_threshold", "leader_threshold"),
        ("round_startup_delay", "round_startup_delay"),
        ("chat_poll_seconds", "chat_poll_seconds"),
        ("log_dir", "log_dir"),
    ):
        raw = getattr(args, argument, None)
        if raw is not None:
            overrides[field] = raw
    if getattr(args, "h_enabled", None) is not None:
        overrides["disable_h"] = not bool(args.h_enabled)
    return replace(value, **overrides).normalized()


# Compatibility aliases for integrations that previously imported kage_pilot_dojo.
build_parser = build_dojo_parser
resolve_config = resolve_dojo_config


def run_dojo(argv: list[str]) -> int:
    args = build_dojo_parser().parse_args(argv)
    try:
        config = resolve_dojo_config(args)
    except (TypeError, ValueError) as exc:
        print(f"DOJO_CONFIG_ERROR / ERRO_CONFIG_DOJO: {exc}")
        return 2

    if args.show_config:
        print(json.dumps(config.to_public_dict(), ensure_ascii=False, indent=2))
        return 0

    service = DojoTrainingService()
    print("Kage Pilot Dojo - CANONICAL ENTRY POINT / ENTRADA CANONICA")
    print(f"Config / Configuracao: {Path(args.config).resolve()}")
    print(
        f"Recovery / Recuperacao: HP>={config.recovery_hp_percent:.0f}% "
        f"Chakra>={config.recovery_chakra_percent:.0f}%"
    )
    print("F12 or Ctrl+C = stop / parar")

    if not service.start(config, on_output=print):
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


def main(argv: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if not values:
        build_dojo_parser().print_help()
        print("\nMain command / Comando principal: python kage_pilot.py dojo")
        return 0

    command = values[0].strip().lower()
    if command == "dojo":
        return run_dojo(values[1:])
    if command in TOOLS_COMMANDS:
        return int(tools_main(values))

    print(f"UNKNOWN_KAGE_PILOT_COMMAND: {values[0]}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
