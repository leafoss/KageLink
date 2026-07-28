from __future__ import annotations

import argparse
import ctypes
import time

import cv2

from pc_agent.kage_pilot.entity_observer import decode_jpeg
from pc_agent.kage_pilot.post_combat_v03 import DojoLeaderDetector, HudResourceReader
from pc_agent.kage_pilot.recorder import WindowsGameFrameSource


VK_F12 = 0x7B


def _f12_pressed() -> bool:
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(VK_F12) & 0x8000)
    except Exception:
        return False


def _best_multiscale(frame_bgr, detector: DojoLeaderDetector):
    """Diagnostic-only search that reports the best match even below production threshold."""
    if frame_bgr is None or frame_bgr.size == 0:
        return None

    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    frame_edge = cv2.Canny(gray, 45, 120)
    base = detector.template_gray
    best_gray = (-1.0, 1.0, (0, 0), base.shape[1], base.shape[0])
    best_edge = (-1.0, 1.0, (0, 0), base.shape[1], base.shape[0])

    for scale in (0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.15, 1.20, 1.25, 1.30):
        width = max(8, round(base.shape[1] * scale))
        height = max(8, round(base.shape[0] * scale))
        if width >= gray.shape[1] or height >= gray.shape[0]:
            continue

        interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
        template = cv2.resize(base, (width, height), interpolation=interpolation)
        result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
        _, score, _, location = cv2.minMaxLoc(result)
        if float(score) > best_gray[0]:
            best_gray = (float(score), float(scale), location, width, height)

        template_edge = cv2.Canny(template, 45, 120)
        if cv2.countNonZero(template_edge) > 5:
            edge_result = cv2.matchTemplate(frame_edge, template_edge, cv2.TM_CCOEFF_NORMED)
            _, edge_score, _, edge_location = cv2.minMaxLoc(edge_result)
            if float(edge_score) > best_edge[0]:
                best_edge = (float(edge_score), float(scale), edge_location, width, height)

    return best_gray, best_edge


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Dojo leader + HP/Chakra calibration probe / probe somente leitura"
    )
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--interval", type=float, default=0.50)
    args = parser.parse_args()

    source = WindowsGameFrameSource()
    # Production remains unchanged. This threshold only controls the legacy match field;
    # diagnostic best_gray/best_edge below always report the best candidate found.
    leader = DojoLeaderDetector(threshold=0.45)
    resources = HudResourceReader()
    started = time.monotonic()
    next_print = started

    print("Kage Pilot v0.3 POST-COMBAT PROBE")
    print("READ ONLY / SOMENTE LEITURA - NO KEYS / NENHUMA TECLA")
    print("LEADER DIAGNOSTIC: multiscale grayscale + edges / diagnostico multi-escala")
    print("F12 = stop / parar")

    try:
        while time.monotonic() - started < max(1.0, float(args.seconds)):
            if _f12_pressed():
                break
            captured = source.capture()
            frame = decode_jpeg(bytes(captured.jpeg))
            match = leader.find(frame)
            diagnostics = _best_multiscale(frame, leader)
            levels = resources.read(frame)
            now = time.monotonic()
            if now >= next_print:
                score = "none" if match is None else f"{match.score:.3f}"
                hp = "?" if levels.health is None else f"{levels.health * 100:.0f}%"
                chakra = "?" if levels.chakra is None else f"{levels.chakra * 100:.0f}%"
                if diagnostics is None:
                    diagnostic_text = "best_gray=none best_edge=none"
                else:
                    best_gray, best_edge = diagnostics
                    diagnostic_text = (
                        f"best_gray={best_gray[0]:.3f}@{best_gray[1]:.2f} "
                        f"xy={best_gray[2][0]},{best_gray[2][1]} "
                        f"best_edge={best_edge[0]:.3f}@{best_edge[1]:.2f} "
                        f"edge_xy={best_edge[2][0]},{best_edge[2][1]}"
                    )
                print(
                    f"PROBE leader_score={score} {diagnostic_text} "
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
