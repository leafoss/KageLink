from __future__ import annotations

import argparse

from pc_agent.config import load_config
from pc_agent.kage_pilot.dojo_fight_v03e import DojoFightRequestError
from pc_agent.kage_pilot.dojo_fight_v03f import request_taijutsu_dojo_spar


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Kage Pilot v0.3f isolated Dojo request test: search trainer + click dialog OK / "
            "teste isolado: procurar treinador + clicar OK"
        )
    )
    parser.add_argument("--trainer-search-timeout", type=float, default=90.0)
    parser.add_argument("--dialog-delay", type=float, default=10.0)
    parser.add_argument("--dialog-timeout", type=float, default=4.0)
    parser.add_argument("--spawn-delay", type=float, default=5.0)
    parser.add_argument("--interaction-attempts", type=int, default=6)
    parser.add_argument("--leader-threshold", type=float, default=0.88)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = load_config()
    print("Kage Pilot v0.3f DOJO REQUEST TEST")
    print("SEARCH TRAINER -> CLICK SPRITE -> WAIT 10s -> DIRECT BUTTON OK CLICK -> WAIT 5s")
    print("NO COMBAT RUNTIME / SEM COMBATE")
    print("START ANYWHERE IN THE DOJO, NOT MEDITATING / INICIE FORA DA MEDITACAO")
    print("F12 = EMERGENCY STOP / PARADA IMEDIATA")
    try:
        target = request_taijutsu_dojo_spar(
            config.game_title,
            dialog_delay_seconds=args.dialog_delay,
            dialog_find_timeout_seconds=args.dialog_timeout,
            spawn_delay_seconds=args.spawn_delay,
            leader_threshold=args.leader_threshold,
            trainer_search_timeout_seconds=args.trainer_search_timeout,
            interaction_attempts=args.interaction_attempts,
        )
    except DojoFightRequestError as error:
        print(f"DOJO_REQUEST_TEST_FAILED: {error}")
        return 1
    except Exception as error:
        print(f"DOJO_REQUEST_TEST_STOPPED: {type(error).__name__}: {error}")
        return 1

    print(
        f"DOJO_REQUEST_TEST_OK score={target.score:.3f} "
        f"visual_d={target.grid_distance} bbox={target.bbox}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
