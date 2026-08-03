from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import cv2


def _capture_pre_spawn_scene(path: Path) -> None:
    from pc_agent.game_capture import GameCapture
    capture = GameCapture()
    try:
        native = capture.capture_native()
        path.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(path), native.bgr):
            raise RuntimeError(f"PR27_9_PRE_SPAWN_WRITE_FAILED:{path}")
        print(
            f"PR27_9_PRE_SPAWN_SCENE_READY path={path.resolve()} "
            f"native={native.source_width}x{native.source_height}"
        )
    finally:
        capture.close()


def _wait_for_spawn(seconds: float, f12_pressed) -> None:
    deadline = time.monotonic() + max(0.0, float(seconds))
    while time.monotonic() < deadline:
        if bool(f12_pressed()):
            raise RuntimeError("F12_STOP")
        time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))


def _perception_runtime_argv(args, log_path: Path) -> list[str]:
    return [
        "full_round_pr27_8",
        "--seconds",
        str(max(1.0, float(args.combat_seconds))),
        "--post-combat-timeout",
        str(max(5.0, float(args.post_combat_timeout))),
        "--startup-delay",
        str(max(0.0, float(args.round_startup_delay))),
        "--chat-poll-seconds",
        str(max(0.10, min(2.0, float(args.chat_poll_seconds)))),
        "--recovery-hp",
        str(max(0.90, float(args.recovery_hp_percent) / 100.0)),
        "--recovery-chakra",
        str(max(0.50, float(args.recovery_chakra_percent) / 100.0)),
        "--leader-threshold",
        str(float(args.leader_threshold)),
        "--log",
        str(log_path),
    ]


def main() -> int:
    import kage_pilot_loop_v03g as legacy_loop
    from pc_agent.config import load_config
    from pc_agent.kage_pilot.dojo_request import request_taijutsu_dojo_spar_single_click
    from pc_agent.kage_pilot.dojo_templates import install_user_dojo_leader_detector

    args = legacy_loop.build_parser().parse_args()
    if int(args.rounds) != 1:
        print("PR27_9_ONE_PERCEPTION_ROUND_ONLY")
        return 2

    print("KAGE COMBAT LAB - PR27.9 NOISE-AWARE OBJECT PERCEPTION LOOP")
    print("OUTER FLOW: Trainer identity before click -> dialog OK -> PRE_SPAWN_SCENE -> perception")
    print("CONTROL: physically disabled; no R, H or directional keys")
    print("GRID: native 1920x1037, 64px, offset=(0,21), SELF absolute=(6,15)")
    print("F12: emergency stop remains active")

    log_path = (Path(args.log_dir) / "round_001.jsonl").resolve()
    identity_scene = Path(
        os.environ.get(
            "KAGE_PR279_TRAINER_IDENTITY_SCENE",
            str(log_path.parent / "pr27_9_trainer_pre_click.png"),
        )
    ).resolve()
    identity_scene.parent.mkdir(parents=True, exist_ok=True)
    os.environ["KAGE_PR279_TRAINER_IDENTITY_SCENE"] = str(identity_scene)

    install_user_dojo_leader_detector()
    config = load_config()
    click = request_taijutsu_dojo_spar_single_click(
        config.game_title,
        dialog_delay_seconds=max(0.0, float(args.dialog_delay)),
        dialog_find_timeout_seconds=max(0.5, float(args.dialog_timeout)),
        dialog_retries=max(0, min(10, int(args.dialog_retries))),
        spawn_delay_seconds=0.0,
        leader_threshold=float(args.leader_threshold),
        trainer_search_timeout_seconds=max(10.0, float(args.trainer_search_timeout)),
        interaction_attempts=1,
        round_number=1,
    )
    bbox = getattr(click, "bbox", None)
    if bbox is not None:
        values = tuple(int(value) for value in bbox)
        if len(values) == 4:
            os.environ["KAGE_PR278_TRAINER_BBOX_OUTPUT"] = ",".join(str(value) for value in values)
            os.environ["KAGE_PR279_TRAINER_SCORE"] = str(float(getattr(click, "score", 0.0)))
            print(f"PR27_9_TRAINER_BBOX_OUTPUT={values}")
            print(f"PR27_9_TRAINER_IDENTITY_SCENE={identity_scene}")

    pre_spawn_path = Path(
        os.environ.get(
            "KAGE_PR278_PRE_SPAWN_FILE",
            str(log_path.parent / "pr27_9_pre_spawn_scene.png"),
        )
    ).resolve()
    os.environ["KAGE_PR278_PRE_SPAWN_FILE"] = str(pre_spawn_path)
    _capture_pre_spawn_scene(pre_spawn_path)
    _wait_for_spawn(float(args.spawn_delay), legacy_loop.f12_pressed)

    from . import full_round_pr27_8
    previous_argv = list(sys.argv)
    sys.argv = _perception_runtime_argv(args, log_path)
    try:
        return int(full_round_pr27_8.main())
    finally:
        sys.argv = previous_argv


if __name__ == "__main__":
    raise SystemExit(main())
