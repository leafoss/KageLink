from __future__ import annotations

import argparse
import time

from pc_agent.kage_pilot.pilot import WindowsGameController


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Kage Pilot raw keyboard diagnostic / diagnóstico bruto de teclado"
    )
    parser.add_argument("--hold-key", default="r", help="Key to keep held / Tecla a manter pressionada")
    parser.add_argument("--hold-seconds", type=float, default=3.0, help="Hold duration / Duração")
    parser.add_argument("--tap-key", default="h", help="Key to tap while base key stays held / Tecla para toque")
    parser.add_argument("--tap-seconds", type=float, default=0.15, help="Tap duration / Duração do toque")
    parser.add_argument("--startup-delay", type=float, default=3.0, help="Seconds after game focus before input / Atraso após focar o jogo")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    hold_key = str(args.hold_key).strip().lower()
    tap_key = str(args.tap_key).strip().lower()
    hold_seconds = max(0.2, float(args.hold_seconds))
    tap_seconds = max(0.03, float(args.tap_seconds))
    startup_delay = max(0.0, float(args.startup_delay))

    print("Kage Pilot INPUT TEST / TESTE DE ENTRADA")

    controller = WindowsGameController(recover_foreground=True, debug=True)
    controller.activate()
    controller.release_all()

    print("Shinobi Story Online em foco / in foreground")
    print(f"Em / in {startup_delay:.1f}s: segurar/hold {hold_key.upper()} por {hold_seconds:.1f}s")
    print(f"Depois / then: {hold_key.upper()} + toque/tap {tap_key.upper()} por {tap_seconds:.2f}s")
    time.sleep(startup_delay)

    interval = 0.10
    started = time.monotonic()
    try:
        print(f"INPUT hold={hold_key}")
        while time.monotonic() - started < hold_seconds:
            controller.apply_keys((hold_key,))
            time.sleep(interval)

        print(f"INPUT tap={tap_key} with_hold={hold_key}")
        controller.apply_keys((hold_key, tap_key))
        time.sleep(tap_seconds)
        controller.apply_keys((hold_key,))
        time.sleep(0.35)
        print("INPUT TEST COMPLETE / TESTE CONCLUÍDO")
        return 0
    finally:
        controller.release_all()


if __name__ == "__main__":
    raise SystemExit(main())
