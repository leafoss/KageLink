from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import kage_pilot_loop_v03g as loop_v03g

from pc_agent.kage_pilot.dojo_fight_v03i import request_taijutsu_dojo_spar_single_click
from pc_agent.kage_pilot.dojo_leader_v03l import install_clear_dojo_leader_detector
from pc_agent.kage_pilot.ko_identity_v03k import extract_ko_identity


_LAST_ACCEPTED_KO_NAME = ""


def _run_round_with_ko_buffer(args, *, round_number: int) -> bool:
    """Run one validated round while carrying the last accepted opponent name forward."""

    global _LAST_ACCEPTED_KO_NAME
    recovery_hp_percent, recovery_chakra_percent = loop_v03g._validate_recovery_targets(args)
    script = Path(__file__).with_name("kage_pilot_live_v03k_round.py")
    log_path = args.log_dir / f"round_{round_number:03d}.jsonl"
    command = [
        sys.executable,
        str(script),
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
    if _LAST_ACCEPTED_KO_NAME:
        command.extend(["--previous-ko-name", _LAST_ACCEPTED_KO_NAME])
    if args.disable_h:
        command.append("--disable-h")

    print(f"ROUND {round_number}: START COMBAT RUNTIME / INICIAR COMBATE")
    print(
        f"ROUND {round_number}: KO_BUFFER previous="
        f"{_LAST_ACCEPTED_KO_NAME or '-'}"
    )
    print("COMMAND:", subprocess.list2cmdline(command))
    process = subprocess.Popen(
        command,
        cwd=str(Path(__file__).resolve().parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    ready = False
    victory = False
    accepted_ko_name: str | None = None
    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="")
        lowered = line.casefold()
        if "victory_chat / vitoria_chat" in lowered:
            victory = True
            _, _, payload = line.partition(":")
            accepted_ko_name = extract_ko_identity(payload)
        if "result=ready" in lowered:
            ready = True

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

    install_clear_dojo_leader_detector()
    print("Kage Pilot v0.3j: OPPONENT-AWARE KO BUFFER HOTFIX")
    print("TRAINER: local calibration + native 68x77 and compact 32x45 templates")
    print("TRAINER: exactly one click; dialog retries never re-click or re-search the trainer")
    print("DIALOG: one initial check + configured retries; failed dialog round does not stop loop")
    print("BURST: only one confirmed adjacent facing pulse; movement and H remain blocked")
    print("KO: remember accepted opponent; repeated previous name is rejected")
    print("KO REJECT: release all, invalidate target memory, reacquire, continue combat")

    loop_v03g.REQUEST_DOJO_FIGHT = request_taijutsu_dojo_spar_single_click
    loop_v03g.DIALOG_RETRY_POLICY_ENABLED = True
    loop_v03g.ROUND_SCRIPT_NAME = "kage_pilot_live_v03k_round.py"
    loop_v03g._run_round = _run_round_with_ko_buffer
    return loop_v03g.main()


if __name__ == "__main__":
    raise SystemExit(main())
