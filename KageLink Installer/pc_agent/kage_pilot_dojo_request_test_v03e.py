from __future__ import annotations

import argparse

from pc_agent.config import load_config
from pc_agent.kage_pilot.dojo_fight_v03e import (
    DojoFightRequestError,
    request_taijutsu_dojo_spar,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Kage Pilot v0.3e isolated Dojo request test: click trainer, wait, Enter / "
            "teste isolado: clicar treinador, aguardar e Enter"
        )
    )
    parser.add_argument("--dialog-delay", type=float, default=10.0)
    parser.add_argument("--dialog-timeout", type=float, default=4.0)
    parser.add_argument("--spawn-delay", type=float, default=5.0)
    parser.add_argument("--leader-threshold", type=float, default=0.88)
    args = parser.parse_args()

    config = load_config()
    print("Kage Pilot v0.3e DOJO REQUEST TEST")
    print("START ADJACENT TO TRAINER, NOT MEDITATING / INICIE ADJACENTE E FORA DA MEDITACAO")
    print("ACTION: one trainer click -> wait 10s -> ListBox option 0 -> Enter -> wait 5s")
    print("F12 = EMERGENCY STOP / PARADA IMEDIATA")

    try:
        target = request_taijutsu_dojo_spar(
            config.game_title,
            dialog_delay_seconds=args.dialog_delay,
            dialog_find_timeout_seconds=args.dialog_timeout,
            spawn_delay_seconds=args.spawn_delay,
            leader_threshold=args.leader_threshold,
        )
    except DojoFightRequestError as error:
        print(f"DOJO_REQUEST_FAILED / PEDIDO_FALHOU: {error}")
        return 1
    except Exception as error:
        print(f"DOJO_REQUEST_STOPPED / PEDIDO_INTERROMPIDO: {type(error).__name__}: {error}")
        return 1

    print(
        f"DOJO_REQUEST_OK / PEDIDO_OK score={target.score:.3f} "
        f"d={target.grid_distance} bbox={target.bbox}"
    )
    print("FIGHT SHOULD NOW BE ACTIVE / A LUTA DEVE ESTAR ATIVA")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
