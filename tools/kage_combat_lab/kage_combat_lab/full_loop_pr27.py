from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any


ROUND_MODULE = "kage_combat_lab.full_round_daynight_pr27"
POST_OK_GATE_ARG = "--pr27-post-ok"
BASELINE_SECONDS_ENV = "KAGE_PR27_PRESPAWN_BASELINE_SECONDS"


def replace_source_round_command(command: list[str]) -> list[str]:
    """Route the inherited outer loop to the isolated PR27 round."""

    if len(command) < 2:
        raise ValueError("FULL_LOOP_ROUND_COMMAND_INVALID")
    executable = str(command[0])
    round_entry = str(command[1])
    if not round_entry.casefold().endswith(".py"):
        raise RuntimeError(
            "FULL_LOOP_SOURCE_CHECKOUT_ONLY: expected a Python round script, "
            f"got {round_entry!r}"
        )
    return [executable, "-m", ROUND_MODULE, POST_OK_GATE_ARG, *command[2:]]


def install_full_loop_round(validated_engine: Any) -> Callable[..., tuple[list[str], Path]]:
    """Preserve trainer/dialog/recovery and replace only the combat subprocess."""

    from .pr27_pre_trainer_baseline import reset_native_baseline_capture

    original = validated_engine._round_command
    request_owner = getattr(validated_engine, "legacy_loop", None)
    if request_owner is not None and hasattr(request_owner, "_request_kwargs"):
        original_request_kwargs = request_owner._request_kwargs

        def pr27_request_kwargs(args, *, round_number: int) -> dict:
            values = original_request_kwargs(args, round_number=round_number)
            spawn_seconds = max(1.0, float(values.get("spawn_delay_seconds", 0.0)))
            os.environ[BASELINE_SECONDS_ENV] = str(spawn_seconds)
            reset_native_baseline_capture()
            print(
                f"ROUND {round_number}: PR27_NATIVE_BASELINE_RESERVED "
                f"duration={spawn_seconds:.2f}s phase=BEFORE_TRAINER_CLICK"
            )
            return values

        request_owner._request_kwargs = pr27_request_kwargs

    def full_round_command(args, *, round_number: int) -> tuple[list[str], Path]:
        command, cwd = original(args, round_number=round_number)
        if bool(getattr(validated_engine.sys, "frozen", False)):
            raise RuntimeError(
                "FULL_LOOP_SOURCE_CHECKOUT_ONLY: use the local KageLink checkout, "
                "not the installed KagePilotDojo.exe"
            )
        replaced = replace_source_round_command(list(command))
        print(
            f"ROUND {round_number}: PR27_COMBAT_SUBPROCESS=NATIVE_GRID_SPRITE_TRACKER "
            "OUTER_FLOW=TRAINER_DIALOG_OK_AND_POST_KO_ONLY"
        )
        return replaced, cwd

    validated_engine._round_command = full_round_command
    return full_round_command


def main() -> int:
    from .dojo_multitemplate import install_day_night_dojo_detector
    from .pr27_pre_trainer_baseline import install_native_pre_trainer_baseline_capture

    install_day_night_dojo_detector()
    install_native_pre_trainer_baseline_capture()
    import kage_pilot_loop as canonical_loop

    validated_engine = getattr(canonical_loop, "_validated_engine", None)
    if validated_engine is None:
        raise RuntimeError("FULL_LOOP_VALIDATED_ENGINE_MISSING")

    install_full_loop_round(validated_engine)
    print("KAGE COMBAT LAB - PR27 FULL DOJO LOOP")
    print("OUTER FLOW: find Trainer -> native baseline -> click -> dialog -> OK -> PR27 combat")
    print("POST FLOW: authoritative KO -> find Trainer -> protected meditation -> READY")
    print("PR27 COMBAT: no PR26 runtime patch chain is installed")
    print("MEDITATION: second V remains physically blocked for at least 5.25 seconds")
    print("F12: emergency stop remains active")
    return int(canonical_loop.main())


if __name__ == "__main__":
    raise SystemExit(main())
