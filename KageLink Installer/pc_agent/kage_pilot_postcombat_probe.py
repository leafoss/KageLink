from __future__ import annotations

import argparse
import ctypes
import time

from pc_agent.kage_pilot.entity_observer import decode_jpeg
from pc_agent.kage_pilot.post_combat_v03 import DojoLeaderDetector, HudResourceReader
from pc_agent.kage_pilot.recorder import WindowsGameFrameSource


VK_F12 = 0x7B


def _f12_pressed() -> bool:
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(VK_F12) & 0x8000)
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Dojo leader + HP/Chakra calibration probe / probe somente leitura"
    )
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--interval", type=float, default=0.50)
    args = parser.parse_args()

    source = WindowsGameFrameSource()
    # Low threshold in the probe so the raw score remains observable before choosing the
    # production cutoff. The live controller still uses its stricter default threshold.
    leader = DojoLeaderDetector(threshold=0.45)
    resources = HudResourceReader()
    started = time.monotonic()
    next_print = started

    print("Kage Pilot v0.3 POST-COMBAT PROBE")
    print("READ ONLY / SOMENTE LEITURA - NO KEYS / NENHUMA TECLA")
    print("F12 = stop / parar")

    try:
        while time.monotonic() - started < max(1.0, float(args.seconds)):
            if _f12_pressed():
                break
            captured = source.capture()
            frame = decode_jpeg(bytes(captured.jpeg))
            match = leader.find(frame)
            levels = resources.read(frame)
            now = time.monotonic()
            if now >= next_print:
                score = "none" if match is None else f"{match.score:.3f}"
                hp = "?" if levels.health is None else f"{levels.health * 100:.0f}%"
                chakra = "?" if levels.chakra is None else f"{levels.chakra * 100:.0f}%"
                print(
                    f"PROBE leader_score={score} HP={hp} Chakra={chakra} "
                    f"fill_px[hp={levels.health_fill_px},chakra={levels.chakra_fill_px}]"
                )
                next_print = now + max(0.1, float(args.interval))
            time.sleep(0.05)
    finally:
        source.close()

    print("Probe stopped / Probe encerrado")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
