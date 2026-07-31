from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys
import threading

import kage_pilot_loop_v03g as legacy_loop

from pc_agent.kage_pilot.dojo_precombat_guard_v351 import (
    release_precombat_handoff,
)
from pc_agent.kage_pilot.dojo_request import request_taijutsu_dojo_spar_single_click
from pc_agent.kage_pilot.dojo_templates import install_user_dojo_leader_detector
from pc_agent.kage_pilot.ko_identity import extract_ko_identity


_LAST_ACCEPTED_KO_NAME = ""
_ROUND_HANDOFF_TIMEOUT_SECONDS = 20.0


def _round_command(args, *, round_number: int) -> tuple[list[str], Path]:
    """Resolve the isolated round runtime for source and installed builds."""

    log_path = args.log_dir / f"round_{round_number:03d}.jsonl"
    if bool(getattr(sys, "frozen", False)):
        executable = Path(sys.executable).resolve().with_name("KagePilotRound.exe")
        command = [str(executable)]
        cwd = executable.parent
    else:
        script = Path(__file__).with_name("kage_pilot_round.py")
        command = [sys.executable, str(script)]
        cwd = Path(__file__).resolve().parent

    recovery_hp_percent, recovery_chakra_percent = legacy_loop._validate_recovery_targets(args)
    command.extend(
        [
            "--seconds",
            str(max(1.0, float(args.combat_seconds))),
            "--post-combat-timeout",
            str(max(5.0, float(args.post_combat_timeout))),
            "--startup-delay",
            str(max(0.0, float(args.round_startup_delay))),
            "--chat-poll-seconds",
            str(max(0.10, min(2.0, float(args.chat_poll_seconds)))),
            "--recovery-hp",
            str(recovery_hp_percent / 100.0),
            "--recovery-chakra",
            str(recovery_chakra_percent / 100.0),
            "--leader-threshold",
            str(float(args.leader_threshold)),
            "--log",
            str(log_path),
        ]
    )
    if _LAST_ACCEPTED_KO_NAME:
        command.extend(["--previous-ko-name", _LAST_ACCEPTED_KO_NAME])
    if args.disable_h:
        command.append("--disable-h")
    return command, cwd


def _round_creationflags() -> int:
    if os.name == "nt" and bool(getattr(sys, "frozen", False)):
        return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return 0


def _run_round_with_ko_buffer(args, *, round_number: int) -> bool:
    """Run one validated round while carrying the last accepted opponent name forward."""

    global _LAST_ACCEPTED_KO_NAME

    command, cwd = _round_command(args, round_number=round_number)
    print(f"ROUND {round_number}: START COMBAT RUNTIME / INICIAR COMBATE")
    print(
        f"ROUND {round_number}: KO_BUFFER previous="
        f"{_LAST_ACCEPTED_KO_NAME or '-'}"
    )
    print("COMMAND:", subprocess.list2cmdline(command))

    timeout = threading.Timer(
        _ROUND_HANDOFF_TIMEOUT_SECONDS,
        release_precombat_handoff,
        kwargs={"reason": "round_start_timeout"},
    )
    timeout.daemon = True
    process = None
    try:
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=_round_creationflags(),
        )
        timeout.start()
    except Exception:
        release_precombat_handoff("round_process_start_failed")
        raise

    ready = False
    victory = False
    accepted_ko_name: str | None = None
    handoff_complete = False
    assert process.stdout is not None
    try:
        for line in process.stdout:
            print(line, end="")
            lowered = line.casefold()
            if (
                not handoff_complete
                and "dojo_precombat_r_hold state=armed source=round_startup" in lowered
            ):
                handoff_complete = release_precombat_handoff("round_child_armed")
                timeout.cancel()
            if "victory_chat / vitoria_chat" in lowered:
                victory = True
                _, _, payload = line.partition(":")
                accepted_ko_name = extract_ko_identity(payload)
            if "result=ready" in lowered:
                ready = True
    finally:
        timeout.cancel()
        release_precombat_handoff("round_child_exit")

    return_code = process.wait()
    if return_code != 0:
        print(f"ROUND {round_number}: CHILD_EXIT={return_code}")
        return False
    if not victory:
        print(f"ROUND {round_number}: NO VICTORY CHAT / SEM VITORIA PELO CHAT")
        return False
    if not accepted_ko_name:
        print(f"ROUND {round_number}: KO_IDENTITY_MISSING_AFTER_VICTORY")
        return False
    if not ready:
        print(f"ROUND {round_number}: NO READY RESULT / SEM RESULTADO READY")
        return False

    previous = _LAST_ACCEPTED_KO_NAME
    _LAST_ACCEPTED_KO_NAME = accepted_ko_name
    print(
        f"ROUND {round_number}: KO_BUFFER_UPDATE previous={previous or '-'} "
        f"current={_LAST_ACCEPTED_KO_NAME}"
    )
    return True


def main() -> int:
    global _LAST_ACCEPTED_KO_NAME
    _LAST_ACCEPTED_KO_NAME = ""
    release_precombat_handoff("loop_start_cleanup")

    install_user_dojo_leader_detector()
    print("Kage Pilot: CANONICAL DOJO LOOP OVER VALIDATED COMPATIBILITY ENGINE")
    print("TRAINER: external user templates for game modes 32x32 and 64x64")
    print("TRAINER: exactly one click; dialog retries never re-click or re-search the trainer")
    print("DIALOG: one initial check + configured retries; failed dialog round does not stop loop")
    print("BURST: only one confirmed adjacent facing pulse; movement and H remain blocked")
    print("KO: remember accepted opponent; repeated previous name is rejected")
    print("KO REJECT: release all, invalidate target memory, reacquire, continue combat")
    print("PRECOMBAT: parent R remains held until the round child confirms its own R")

    legacy_loop.REQUEST_DOJO_FIGHT = request_taijutsu_dojo_spar_single_click
    legacy_loop.DIALOG_RETRY_POLICY_ENABLED = True
    legacy_loop.ROUND_SCRIPT_NAME = "kage_pilot_round.py"
    legacy_loop._run_round = _run_round_with_ko_buffer
    try:
        return legacy_loop.main()
    finally:
        release_precombat_handoff("loop_exit")


if __name__ == "__main__":
    raise SystemExit(main())
