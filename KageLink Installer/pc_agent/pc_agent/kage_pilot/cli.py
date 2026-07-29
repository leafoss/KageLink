from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .dataset import DatasetStore, SessionWriter, default_data_dir
from .dojo import DojoConfig, DojoManager, default_config_text, save_template
from .learning import BehaviorCloner
from .learning_v2 import TemporalCombatModel
from .pilot import Pilot, WindowsGameController
from .pilot_v2 import TemporalCombatPilot
from .recorder import WindowsAsyncInputSource, WindowsGameFrameSource

CONTROL_KEYS = ("f10", "f11", "f12")


def _data_dir(value: str | None) -> Path:
    return Path(value).expanduser() if value else default_data_dir()


def command_record(args: argparse.Namespace) -> int:
    root = _data_dir(args.data_dir)
    frame_source = WindowsGameFrameSource()
    input_source = WindowsAsyncInputSource(excluded_keys=CONTROL_KEYS)
    print("Kage Pilot Recorder v0.2")
    print("F11 = victory / vitória | F12 = defeat / derrota | F10 = stop / parar")
    active: SessionWriter | None = None
    previous_controls: set[str] = set()
    interval = 1.0 / max(1.0, float(args.fps))
    try:
        while True:
            if active is None:
                active = SessionWriter(root, metadata={"source": "kage-pilot-recorder-v0.2"})
                print(f"REC {active.session_id}")
            now = time.time()
            frame = frame_source.capture()
            snapshot = input_source.snapshot(getattr(frame, "target", None))
            active.append(
                bytes(frame.jpeg),
                timestamp=now,
                keys=snapshot.keys,
                mouse_buttons=snapshot.mouse_buttons,
                mouse_x=snapshot.mouse_x,
                mouse_y=snapshot.mouse_y,
            )
            controls = {key for key in CONTROL_KEYS if input_source.key_down(key)}
            pressed = controls - previous_controls
            previous_controls = controls
            if "f10" in pressed:
                active.finalize("unknown")
                print("STOP")
                break
            if "f11" in pressed or "f12" in pressed:
                result = "victory" if "f11" in pressed else "defeat"
                manifest = active.finalize(result)
                print(f"{result.upper()} {manifest['session_id']} samples={manifest['samples']}")
                active = None
                time.sleep(0.35)
            time.sleep(interval)
    except KeyboardInterrupt:
        if active is not None:
            active.finalize("unknown")
    finally:
        frame_source.close()
    return 0


def command_mark(args: argparse.Namespace) -> int:
    store = DatasetStore(_data_dir(args.data_dir))
    manifest = store.mark_result(args.session, args.result)
    print(f"{manifest['session_id']}: {manifest['result']}")
    return 0


def command_train(args: argparse.Namespace) -> int:
    store = DatasetStore(_data_dir(args.data_dir))
    results = ("victory", "defeat") if args.include_defeats else ("victory",)
    model = BehaviorCloner.train(
        store,
        results=results,
        stride=args.stride,
        include_idle=not args.no_idle,
        exclude_keys=args.exclude_key or (),
        use_action_runs=not args.frame_samples,
    )
    path = model.save(Path(args.model))
    mode = "frames" if args.frame_samples else "action-runs"
    excluded = ",".join(args.exclude_key or ()) or "-"
    print(
        f"model={path} mode={mode} exclude={excluded} "
        f"actions={len(model.prototypes)} samples={sum(model.counts.values())}"
    )
    return 0


def command_train_v2(args: argparse.Namespace) -> int:
    store = DatasetStore(_data_dir(args.data_dir))
    results = ("victory", "defeat") if args.include_defeats else ("victory",)
    base_keys = tuple(args.base_key or ("r",))
    skill_keys = tuple(args.skill_key or ("h",))
    post_combat_keys = tuple(args.post_combat_key or ("v",))
    model = TemporalCombatModel.train(
        store,
        results=results,
        base_keys=base_keys,
        skill_keys=skill_keys,
        post_combat_keys=post_combat_keys,
        stride=args.stride,
        history_frames=args.history_frames,
    )
    path = model.save(Path(args.model))
    print(
        f"model={path} version=0.2 base={','.join(model.base_keys) or '-'} "
        f"skills={','.join(model.skill_keys) or '-'} "
        f"post={','.join(model.post_combat_keys) or '-'} "
        f"nav_runs={sum(model.navigation.counts.values())} "
        f"skill_runs={sum(model.skill.counts.values())}"
    )
    print("navigation=" + repr(sorted(model.navigation.counts.items(), key=lambda item: -item[1])))
    print("skills=" + repr(sorted(model.skill.counts.items(), key=lambda item: -item[1])))
    return 0


def command_pilot(args: argparse.Namespace) -> int:
    model = BehaviorCloner.load(Path(args.model))
    frame_source = WindowsGameFrameSource()
    controller = WindowsGameController()
    pilot = Pilot(
        model,
        frame_source,
        controller,
        min_confidence=args.confidence,
        decision_hz=args.hz,
        base_keys=tuple(args.hold_key or ()),
    )
    try:
        pilot.run(seconds=args.seconds)
    except KeyboardInterrupt:
        controller.release_all()
    finally:
        frame_source.close()
    return 0


def _build_v2_pilot(args: argparse.Namespace, frame_source, controller) -> TemporalCombatPilot:
    model = TemporalCombatModel.load(Path(args.model))
    return TemporalCombatPilot(
        model,
        frame_source,
        controller,
        nav_confidence=args.nav_confidence,
        skill_confidence=args.skill_confidence,
        decision_hz=args.hz,
        skill_cooldown_seconds=args.skill_cooldown,
        startup_delay_seconds=getattr(args, "startup_delay", 0.0),
        debug=args.debug,
    )


def command_pilot_v2(args: argparse.Namespace) -> int:
    frame_source = WindowsGameFrameSource()
    controller = WindowsGameController()
    pilot = _build_v2_pilot(args, frame_source, controller)
    try:
        pilot.run(seconds=args.seconds)
    except KeyboardInterrupt:
        controller.release_all()
    finally:
        frame_source.close()
    return 0


def _region(values: list[str]) -> tuple[float, float, float, float]:
    region = tuple(float(value) for value in values)
    if len(region) != 4:
        raise ValueError("REGION_REQUIRES_X_Y_W_H")
    return region  # type: ignore[return-value]


def command_template(args: argparse.Namespace) -> int:
    frame_source = WindowsGameFrameSource()
    try:
        frame = frame_source.capture()
        output = save_template(bytes(frame.jpeg), _region(args.region), Path(args.output))
        print(output)
    finally:
        frame_source.close()
    return 0


def command_init_config(args: argparse.Namespace) -> int:
    path = Path(args.output)
    if path.exists() and not args.force:
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(default_config_text(), encoding="utf-8")
    print(path)
    return 0


def command_dojo(args: argparse.Namespace) -> int:
    model = BehaviorCloner.load(Path(args.model))
    config = DojoConfig.load(Path(args.config))
    frame_source = WindowsGameFrameSource()
    controller = WindowsGameController()
    pilot = Pilot(
        model,
        frame_source,
        controller,
        min_confidence=args.confidence,
        decision_hz=args.hz,
        base_keys=tuple(args.hold_key or ()),
    )
    manager = DojoManager(config, frame_source, controller, pilot)
    try:
        results = manager.run(args.cycles)
        print("cycles=" + ",".join(results))
    except KeyboardInterrupt:
        controller.release_all()
    finally:
        frame_source.close()
    return 0


def command_dojo_v2(args: argparse.Namespace) -> int:
    config = DojoConfig.load(Path(args.config))
    frame_source = WindowsGameFrameSource()
    controller = WindowsGameController()
    pilot = _build_v2_pilot(args, frame_source, controller)
    pilot.startup_delay_seconds = 0.0
    manager = DojoManager(config, frame_source, controller, pilot)
    try:
        results = manager.run(args.cycles)
        print("cycles=" + ",".join(results))
    except KeyboardInterrupt:
        controller.release_all()
    finally:
        frame_source.close()
    return 0


def _add_v2_runtime_args(parser: argparse.ArgumentParser, *, include_startup_delay: bool) -> None:
    parser.add_argument("--model", required=True)
    parser.add_argument("--nav-confidence", type=float, default=0.0)
    parser.add_argument("--skill-confidence", type=float, default=0.02)
    parser.add_argument("--skill-cooldown", type=float, default=1.2)
    parser.add_argument("--hz", type=float, default=10.0)
    parser.add_argument("--debug", action="store_true")
    if include_startup_delay:
        parser.add_argument("--startup-delay", type=float, default=3.0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Kage Pilot v0.2 - temporal local imitation-learning pilot for Shinobi Story Online")
    sub = parser.add_subparsers(dest="command", required=True)

    record = sub.add_parser("record", help="Record demonstrations / Gravar demonstrações")
    record.add_argument("--data-dir")
    record.add_argument("--fps", type=float, default=10.0)
    record.set_defaults(func=command_record)

    mark = sub.add_parser("mark", help="Change session result / Alterar resultado")
    mark.add_argument("session")
    mark.add_argument("result", choices=("victory", "defeat", "unknown"))
    mark.add_argument("--data-dir")
    mark.set_defaults(func=command_mark)

    train = sub.add_parser("train", help="Legacy v0.1 trainer / Treinador legado v0.1")
    train.add_argument("--data-dir")
    train.add_argument("--model", default="kage_pilot_model.json")
    train.add_argument("--stride", type=int, default=1)
    train.add_argument("--include-defeats", action="store_true")
    train.add_argument("--no-idle", action="store_true")
    train.add_argument("--exclude-key", action="append", default=[])
    train.add_argument("--frame-samples", action="store_true")
    train.set_defaults(func=command_train)

    train_v2 = sub.add_parser("train-v2", help="Train temporal navigation + skills / Treinar navegação temporal + jutsus")
    train_v2.add_argument("--data-dir")
    train_v2.add_argument("--model", default="kage_pilot_v02.json")
    train_v2.add_argument("--stride", type=int, default=1)
    train_v2.add_argument("--history-frames", type=int, default=2)
    train_v2.add_argument("--include-defeats", action="store_true")
    train_v2.add_argument("--base-key", action="append", default=[])
    train_v2.add_argument("--skill-key", action="append", default=[])
    train_v2.add_argument(
        "--post-combat-key",
        action="append",
        default=[],
        help="Key that marks the post-fight tail, default V / Tecla que marca o pós-luta, padrão V",
    )
    train_v2.set_defaults(func=command_train_v2)

    pilot = sub.add_parser("pilot", help="Legacy v0.1 Pilot / Pilot legado v0.1")
    pilot.add_argument("--model", required=True)
    pilot.add_argument("--seconds", type=float)
    pilot.add_argument("--confidence", type=float, default=0.08)
    pilot.add_argument("--hz", type=float, default=10.0)
    pilot.add_argument("--hold-key", action="append", default=[])
    pilot.set_defaults(func=command_pilot)

    pilot_v2 = sub.add_parser("pilot-v2", help="Run temporal v0.2 combat / Executar combate temporal v0.2")
    _add_v2_runtime_args(pilot_v2, include_startup_delay=True)
    pilot_v2.add_argument("--seconds", type=float)
    pilot_v2.set_defaults(func=command_pilot_v2)

    template = sub.add_parser("capture-template", help="Capture visual state template / Capturar template visual")
    template.add_argument("--output", required=True)
    template.add_argument("--region", nargs=4, metavar=("X", "Y", "W", "H"), required=True)
    template.set_defaults(func=command_template)

    init_config = sub.add_parser("init-config", help="Create Dojo configuration / Criar configuração do Dojo")
    init_config.add_argument("--output", default="dojo_config.json")
    init_config.add_argument("--force", action="store_true")
    init_config.set_defaults(func=command_init_config)

    dojo = sub.add_parser("dojo", help="Legacy v0.1 Dojo loop / Loop Dojo legado v0.1")
    dojo.add_argument("--model", required=True)
    dojo.add_argument("--config", required=True)
    dojo.add_argument("--cycles", type=int, default=1)
    dojo.add_argument("--confidence", type=float, default=0.08)
    dojo.add_argument("--hz", type=float, default=10.0)
    dojo.add_argument("--hold-key", action="append", default=[])
    dojo.set_defaults(func=command_dojo)

    dojo_v2 = sub.add_parser("dojo-v2", help="Run v0.2 Dojo loop / Executar loop Dojo v0.2")
    _add_v2_runtime_args(dojo_v2, include_startup_delay=False)
    dojo_v2.add_argument("--config", required=True)
    dojo_v2.add_argument("--cycles", type=int, default=1)
    dojo_v2.set_defaults(func=command_dojo_v2)
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
