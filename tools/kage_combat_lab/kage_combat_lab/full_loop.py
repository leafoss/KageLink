from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any


ROUND_MODULE = "kage_combat_lab.full_round_daynight"
POST_OK_GATE_ARG = "--pr25-post-ok"


def replace_source_round_command(command: list[str]) -> list[str]:
    """Replace the validated source round after the outer loop accepted OK/spawn."""

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
    """Route only the isolated combat round to the PR25 full-round adapter."""

    original = validated_engine._round_command

    def full_round_command(args, *, round_number: int) -> tuple[list[str], Path]:
        command, cwd = original(args, round_number=round_number)
        if bool(getattr(validated_engine.sys, "frozen", False)):
            raise RuntimeError(
                "FULL_LOOP_SOURCE_CHECKOUT_ONLY: use the local KageLink checkout, "
                "not the installed KagePilotDojo.exe"
            )
        replaced = replace_source_round_command(list(command))
        print(
            f"ROUND {round_number}: PR25_FULL_ROUND=FACING_AUTHORITY "
            "POST_OK_GATE=CONFIRMED POST=VALIDATED_DOJO_RECOVERY"
        )
        return replaced, cwd

    validated_engine._round_command = full_round_command
    return full_round_command


def main() -> int:
    from .dojo_multitemplate import install_day_night_dojo_detector
    from .post_ok_facing import install_post_ok_right_pulse

    install_day_night_dojo_detector()
    install_post_ok_right_pulse()
    import kage_pilot_loop as canonical_loop

    validated_engine = getattr(canonical_loop, "_validated_engine", None)
    if validated_engine is None:
        raise RuntimeError("FULL_LOOP_VALIDATED_ENGINE_MISSING")

    install_full_loop_round(validated_engine)
    print("KAGE COMBAT LAB - FULL DOJO LOOP")
    print("TRAINER: multi-template 64px day/night detector enabled")
    print("FLOW: trainer -> dialog/OK -> RIGHT before spawn -> acquire -> align -> combat")
    print("AUTHORITY: SEARCH/REID/TURN_ALIGN never hold R or fire H")
    print("FLOW: authoritative KO -> return to Trainer -> meditation -> READY")
    print("MEDITATION: second V is physically blocked for at least 5.25 seconds")
    print("F12: emergency stop remains active in search, startup, combat and recovery")
    return int(canonical_loop.main())


if __name__ == "__main__":
    raise SystemExit(main())
