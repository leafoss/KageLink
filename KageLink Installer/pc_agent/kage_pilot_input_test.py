from __future__ import annotations

import argparse
import time

from pc_agent.kage_pilot.pilot import WindowsGameController


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Kage Pilot raw keyboard diagnostic / diagnóstico bruto de teclado"
    )
    parser.add_argument("--pulse-key", default="r", help="Key to pulse repeatedly / Tecla para pulsos repetidos")
    parser.add_argument("--pulse-seconds", type=float, default=4.0, help="Total pulse test duration / Duração total")
    parser.add_argument("--pulse-down", type=float, default=0.08, help="Seconds key stays down per pulse / Tempo pressionado por pulso")
    parser.add_argument("--pulse-gap", type=float, default=0.08, help="Seconds between pulses / Intervalo entre pulsos")
    parser.add_argument("--tap-key", default="h", help="Known-good comparison key / Tecla de comparação")
    parser.add_argument("--tap-seconds", type=float, default=0.15, help="Comparison tap duration / Duração do toque")
    parser.add_argument("--startup-delay", type=float, default=3.0, help="Seconds after game focus before input / Atraso após focar o jogo")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    pulse_key = str(args.pulse_key).strip().lower()
    tap_key = str(args.tap_key).strip().lower()
    pulse_seconds = max(0.5, float(args.pulse_seconds))
    pulse_down = max(0.02, float(args.pulse_down))
    pulse_gap = max(0.02, float(args.pulse_gap))
    tap_seconds = max(0.03, float(args.tap_seconds))
    startup_delay = max(0.0, float(args.startup_delay))

    print("Kage Pilot INPUT TEST / TESTE DE ENTRADA")

    controller = WindowsGameController(recover_foreground=True, debug=True)
    controller.activate()
    controller.release_all()

    print("Shinobi Story Online em foco / in foreground")
    print(f"Em / in {startup_delay:.1f}s: pulsar/pulse {pulse_key.upper()} por {pulse_seconds:.1f}s")
    print(
        f"Pulso / pulse: down={pulse_down:.2f}s gap={pulse_gap:.2f}s | "
        f"depois / then tap {tap_key.upper()}={tap_seconds:.2f}s"
    )
    time.sleep(startup_delay)

    started = time.monotonic()
    pulses = 0
    try:
        print(f"INPUT pulse={pulse_key}")
        while time.monotonic() - started < pulse_seconds:
            controller.apply_keys((pulse_key,))
            time.sleep(pulse_down)
            controller.apply_keys(())
            pulses += 1
            time.sleep(pulse_gap)

        print(f"INPUT pulses={pulses}")
        print(f"INPUT comparison_tap={tap_key}")
        controller.apply_keys((tap_key,))
        time.sleep(tap_seconds)
        controller.apply_keys(())
        time.sleep(0.35)
        print("INPUT TEST COMPLETE / TESTE CONCLUÍDO")
        return 0
    finally:
        controller.release_all()


if __name__ == "__main__":
    raise SystemExit(main())
