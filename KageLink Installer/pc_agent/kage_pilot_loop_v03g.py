from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import time

from pc_agent.config import load_config
from pc_agent.kage_pilot.dojo_fight_v03e import DojoFightRequestError, f12_pressed
from pc_agent.kage_pilot.dojo_fight_v03f import request_taijutsu_dojo_spar


ROUND_SCRIPT_NAME = "kage_pilot_live_v03g_round.py"
REQUEST_DOJO_FIGHT = request_taijutsu_dojo_spar
MIN_SAFE_RECOVERY_HP_PERCENT = 90.0
MIN_SAFE_RECOVERY_CHAKRA_PERCENT = 50.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Kage Pilot v0.3g Dojo loop: find trainer -> click OK -> fight -> robust KO -> "
            "recover -> repeat / buscar treinador -> clicar OK -> lutar -> KO robusto -> "
            "recuperar -> repetir"
        )
    )
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--combat-seconds", type=float, default=120.0)
    parser.add_argument("--post-combat-timeout", type=float, default=240.0)
    parser.add_argument("--dialog-delay", type=float, default=5.0)
    parser.add_argument("--dialog-timeout", type=float, default=4.0)
    parser.add_argument("--spawn-delay", type=float, default=5.0)
    parser.add_argument("--trainer-search-timeout", type=float, default=90.0)
    parser.add_argument("--interaction-attempts", type=int, default=6)
    parser.add_argument("--round-startup-delay", type=float, default=1.0)
    parser.add_argument("--chat-poll-seconds", type=float, default=0.15)
    parser.add_argument("--recovery-hp-percent", type=float, default=90.0)
    parser.add_argument("--recovery-chakra-percent", type=float, default=50.0)
    parser.add_argument("--leader-threshold", type=float, default=0.88)
    parser.add_argument("--log-dir", type=Path, default=Path("kage_pilot_loop_logs"))
    parser.add_argument("--disable-h", action="store_true")
    return parser


def _validate_recovery_targets(args) -> tuple[float, float]:
    hp = float(args.recovery_hp_percent)
    chakra = float(args.recovery_chakra_percent)
    if not MIN_SAFE_RECOVERY_HP_PERCENT <= hp <= 100.0:
        raise ValueError(
            f"RECOVERY_HP_PERCENT_OUT_OF_RANGE:{hp:g}; "
            f"allowed={MIN_SAFE_RECOVERY_HP_PERCENT:g}..100"
        )
    if not MIN_SAFE_RECOVERY_CHAKRA_PERCENT <= chakra <= 100.0:
        raise ValueError(
            f"RECOVERY_CHAKRA_PERCENT_OUT_OF_RANGE:{chakra:g}; "
            f"allowed={MIN_SAFE_RECOVERY_CHAKRA_PERCENT:g}..100"
        )
    return hp, chakra


def _run_round(args, *, round_number: int) -> bool:
    recovery_hp_percent, recovery_chakra_percent = _validate_recovery_targets(args)
    script = Path(__file__).with_name(ROUND_SCRIPT_NAME)
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
    if args.disable_h:
        command.append("--disable-h")

    print(f"ROUND {round_number}: START COMBAT RUNTIME / INICIAR COMBATE")
    print("COMMAND:", " ".join(command))
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
    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="")
        lowered = line.casefold()
        if "victory_chat / vitoria_chat" in lowered:
            victory = True
        if "result=ready" in lowered:
            ready = True

    return_code = process.wait()
    if return_code != 0:
        print(f"ROUND {round_number}: CHILD_EXIT={return_code}")
        return False
    if not victory:
        print(f"ROUND {round_number}: NO VICTORY CHAT / SEM VITORIA PELO CHAT")
        return False
    if not ready:
        print(f"ROUND {round_number}: NO READY RESULT / SEM RESULTADO READY")
        return False
    return True


def main() -> int:
    args = build_parser().parse_args()
    try:
        recovery_hp_percent, recovery_chakra_percent = _validate_recovery_targets(args)
    except (TypeError, ValueError) as exc:
        print(f"DOJO_CONFIG_ERROR / ERRO_CONFIG_DOJO: {exc}")
        return 2

    rounds = max(0, int(args.rounds))
    args.log_dir.mkdir(parents=True, exist_ok=True)
    config = load_config()

    print("Kage Pilot v0.3g FULL DOJO LOOP")
    print(
        f"FIND TRAINER -> CLICK SPRITE -> WAIT {max(0.0, float(args.dialog_delay)):.1f}s "
        f"-> CLICK DIALOG OK -> WAIT {max(0.0, float(args.spawn_delay)):.1f}s"
    )
    print("COMBAT -> NEW CHAT KO -> RELEASE ALL -> RETURN/SEARCH -> RECOVER -> REPEAT")
    print(
        f"recovery=HP>={recovery_hp_percent:.0f}% "
        f"Chakra>={recovery_chakra_percent:.0f}% / "
        f"recuperacao=HP>={recovery_hp_percent:.0f}% Chakra>={recovery_chakra_percent:.0f}%"
    )
    print(f"rounds={'until F12' if rounds == 0 else rounds} / rodadas={'ate F12' if rounds == 0 else rounds}")
    print("START ANYWHERE IN THE DOJO, RECOVERED, NOT MEDITATING")
    print("F12 = EMERGENCY STOP / PARADA IMEDIATA")

    completed = 0
    round_number = 1
    while rounds == 0 or round_number <= rounds:
        if f12_pressed():
            print("F12 STOP before request / PARADA F12 antes do pedido")
            break

        print(f"ROUND {round_number}: SEARCH AND REQUEST TAIJUTSU DOJO SPAR")
        try:
            click = REQUEST_DOJO_FIGHT(
                config.game_title,
                dialog_delay_seconds=args.dialog_delay,
                dialog_find_timeout_seconds=args.dialog_timeout,
                spawn_delay_seconds=args.spawn_delay,
                leader_threshold=args.leader_threshold,
                trainer_search_timeout_seconds=args.trainer_search_timeout,
                interaction_attempts=args.interaction_attempts,
            )
        except DojoFightRequestError as error:
            print(f"ROUND {round_number}: DOJO_REQUEST_FAILED: {error}")
            break
        except Exception as error:
            print(
                f"ROUND {round_number}: DOJO_REQUEST_STOPPED: "
                f"{type(error).__name__}: {error}"
            )
            break

        print(
            f"ROUND {round_number}: DOJO_REQUEST_OK score={click.score:.3f} "
            f"visual_d={click.grid_distance}"
        )
        if not _run_round(args, round_number=round_number):
            break

        completed += 1
        print(f"ROUND {round_number}: COMPLETE / CONCLUIDA")
        round_number += 1
        time.sleep(0.25)

    print(f"DOJO_LOOP_STOPPED completed={completed} / LOOP_ENCERRADO concluidas={completed}")
    return 0 if completed > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
