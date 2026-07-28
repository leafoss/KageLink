from __future__ import annotations

import argparse
import ctypes
import time

from pc_agent.kage_pilot.entity_observer import decode_jpeg
from pc_agent.kage_pilot.post_combat_v03b import (
    CalibratedDojoLeaderDetector,
    CalibratedHudResourceReader,
)
from pc_agent.kage_pilot.recorder import WindowsGameFrameSource


VK_F12 = 0x7B


def _f12_pressed() -> bool:
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(VK_F12) & 0x8000)
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only calibrated Dojo leader + HP/Chakra probe / probe calibrado"
    )
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--interval", type=float, default=0.50)
    parser.add_argument("--leader-threshold", type=float, default=0.72)
    args = parser.parse_args()

    source = WindowsGameFrameSource()
    leader = CalibratedDojoLeaderDetector(threshold=args.leader_threshold)
    resources = CalibratedHudResourceReader()
    started = time.monotonic()
    next_print = started

    print("Kage Pilot v0.3b POST-COMBAT PROBE")
    print("READ ONLY / SOMENTE LEITURA - NO KEYS / NENHUMA TECLA")
    print(f"LEADER TEMPLATE / TEMPLATE DO LIDER: {leader.template_source} -> {leader.template_path}")
    print("F12 = stop / parar")

    try:
        while time.monotonic() - started < max(1.0, float(args.seconds)):
            if _f12_pressed():
                break
            frame = decode_jpeg(bytes(source.capture().jpeg))
            now = time.monotonic()
            match = leader.find(frame, now=now)
            levels = resources.read(frame)
            if now >= next_print:
                score = "none" if match is None else f"{match.score:.3f}"
                source_text = "-" if match is None else match.source
                bbox = "-" if match is None else ",".join(str(value) for value in match.bbox)
                raw_xy = "-" if leader.last_raw_location is None else f"{leader.last_raw_location[0]},{leader.last_raw_location[1]}"
                hp = "?" if levels.health is None else f"{levels.health * 100:.0f}%"
                chakra = "?" if levels.chakra is None else f"{levels.chakra * 100:.0f}%"
                print(
                    f"PROBE leader_score={score} source={source_text} bbox={bbox} "
                    f"best_raw={leader.last_raw_score:.3f}@{leader.last_raw_scale:.2f} xy={raw_xy} "
                    f"HP={hp} Chakra={chakra} "
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
