from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pc_agent.kage_pilot.dataset import DatasetStore, default_data_dir
from pc_agent.kage_pilot.learning_spatial_v2 import FEATURE_MODE, SpatialCombatModel
from pc_agent.kage_pilot.pilot import WindowsGameController
from pc_agent.kage_pilot.pilot_v2 import TemporalCombatPilot
from pc_agent.kage_pilot.recorder import WindowsGameFrameSource


def _data_dir(value: str | None) -> Path:
    return Path(value).expanduser() if value else default_data_dir()


def command_train(args: argparse.Namespace) -> int:
    store = DatasetStore(_data_dir(args.data_dir))
    results = ("victory", "defeat") if args.include_defeats else ("victory",)
    model = SpatialCombatModel.train(
        store,
        results=results,
        base_keys=("r",),
        skill_keys=("h",),
        post_combat_keys=("v",),
        stride=args.stride,
        history_frames=args.history_frames,
    )
    path = model.save(Path(args.model))
    print(
        f"model={path} mode={FEATURE_MODE} base=r skills=h post=v "
        f"nav_runs={sum(model.navigation.counts.values())} "
        f"skill_runs={sum(model.skill.counts.values())}"
    )
    print("navigation=" + repr(sorted(model.navigation.counts.items(), key=lambda item: -item[1])))
    print("skills=" + repr(sorted(model.skill.counts.items(), key=lambda item: -item[1])))
    return 0


def command_pilot(args: argparse.Namespace) -> int:
    model = SpatialCombatModel.load(Path(args.model))
    frame_source = WindowsGameFrameSource()
    controller = WindowsGameController(recover_foreground=True, debug=args.debug)
    pilot = TemporalCombatPilot(
        model,  # type: ignore[arg-type]
        frame_source,
        controller,
        nav_confidence=args.nav_confidence,
        skill_confidence=args.skill_confidence,
        decision_hz=args.hz,
        skill_cooldown_seconds=args.skill_cooldown,
        startup_delay_seconds=args.startup_delay,
        debug=args.debug,
    )
    try:
        pilot.run(seconds=args.seconds)
    except KeyboardInterrupt:
        controller.release_all()
    finally:
        frame_source.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Kage Pilot v0.2 spatial experiment / experimento espacial"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    train = sub.add_parser("train", help="Train spatial model / Treinar modelo espacial")
    train.add_argument("--data-dir")
    train.add_argument("--model", default="kage_pilot_v02_spatial.json")
    train.add_argument("--stride", type=int, default=1)
    train.add_argument("--history-frames", type=int, default=2)
    train.add_argument("--include-defeats", action="store_true")
    train.set_defaults(func=command_train)

    pilot = sub.add_parser("pilot", help="Run spatial model / Executar modelo espacial")
    pilot.add_argument("--model", default="kage_pilot_v02_spatial.json")
    pilot.add_argument("--seconds", type=float, default=20.0)
    pilot.add_argument("--nav-confidence", type=float, default=0.01)
    pilot.add_argument("--skill-confidence", type=float, default=0.02)
    pilot.add_argument("--skill-cooldown", type=float, default=1.2)
    pilot.add_argument("--hz", type=float, default=10.0)
    pilot.add_argument("--startup-delay", type=float, default=3.0)
    pilot.add_argument("--debug", action="store_true")
    pilot.set_defaults(func=command_pilot)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
