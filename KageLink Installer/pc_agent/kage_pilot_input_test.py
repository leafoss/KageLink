from __future__ import annotations

import argparse
import ctypes
import time
from ctypes import wintypes

from pc_agent.game_control import INPUT, INPUT_KEYBOARD, INPUT_UNION, KEYBDINPUT, _user32
from pc_agent.kage_pilot.pilot import WindowsGameController


KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
MAPVK_VK_TO_VSC = 0

# Reuse the exact INPUT/INPUT_UNION/KEYBDINPUT layout from game_control.py.
# BYOND supports +REP macros, so this diagnostic intentionally differs from
# the previous pulse test: one initial key-down is followed by repeated
# key-down events WITHOUT key-up in between, then a single final key-up.
_user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
_user32.MapVirtualKeyW.restype = wintypes.UINT


def _scan_code_for_letter(key: str) -> int:
    value = str(key).strip().upper()
    if len(value) != 1 or not value.isalpha():
        raise ValueError("SCAN_CODE_TEST_REQUIRES_A_Z")
    scan_code = int(_user32.MapVirtualKeyW(ord(value), MAPVK_VK_TO_VSC))
    if not scan_code:
        raise RuntimeError(f"SCAN_CODE_NOT_FOUND:{value}")
    return scan_code


def _send_scan_code(scan_code: int, *, down: bool) -> None:
    flags = KEYEVENTF_SCANCODE
    if not down:
        flags |= KEYEVENTF_KEYUP
    event = INPUT(
        type=INPUT_KEYBOARD,
        union=INPUT_UNION(
            ki=KEYBDINPUT(
                wVk=0,
                wScan=int(scan_code),
                dwFlags=flags,
                time=0,
                dwExtraInfo=0,
            )
        ),
    )
    sent = _user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))
    if sent != 1:
        raise ctypes.WinError(ctypes.get_last_error())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Kage Pilot BYOND +REP diagnostic / diagnóstico de repetição BYOND"
    )
    parser.add_argument("--repeat-key", default="r", help="Letter to hold/repeat / Letra para manter e repetir")
    parser.add_argument("--repeat-seconds", type=float, default=4.0, help="Total repeat test duration / Duração total")
    parser.add_argument("--repeat-delay", type=float, default=0.35, help="Delay before repeats begin / Atraso antes da repetição")
    parser.add_argument("--repeat-interval", type=float, default=0.05, help="Seconds between repeated key-down events / Intervalo")
    parser.add_argument("--tap-key", default="h", help="Known-good comparison key / Tecla de comparação")
    parser.add_argument("--tap-seconds", type=float, default=0.15, help="Comparison tap duration / Duração do toque")
    parser.add_argument("--startup-delay", type=float, default=3.0, help="Seconds after game focus before input / Atraso após foco")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    repeat_key = str(args.repeat_key).strip().lower()
    tap_key = str(args.tap_key).strip().lower()
    repeat_seconds = max(0.8, float(args.repeat_seconds))
    repeat_delay = max(0.05, float(args.repeat_delay))
    repeat_interval = max(0.01, float(args.repeat_interval))
    tap_seconds = max(0.03, float(args.tap_seconds))
    startup_delay = max(0.0, float(args.startup_delay))
    scan_code = _scan_code_for_letter(repeat_key)

    print("Kage Pilot BYOND +REP INPUT TEST / TESTE DE REPETIÇÃO BYOND")
    print(f"hardware scan: {repeat_key.upper()} = 0x{scan_code:02X}")
    print(f"INPUT struct size={ctypes.sizeof(INPUT)} bytes")

    controller = WindowsGameController(recover_foreground=True, debug=True)
    controller.activate()
    controller.release_all()

    print("Shinobi Story Online em foco / in foreground")
    print(f"Em / in {startup_delay:.1f}s: {repeat_key.upper()} DOWN + repeated DOWN events")
    print(f"repeat_delay={repeat_delay:.2f}s repeat_interval={repeat_interval:.2f}s")
    time.sleep(startup_delay)

    repeats = 0
    pressed = False
    try:
        print(f"INPUT repeat_hold={repeat_key}")
        _send_scan_code(scan_code, down=True)
        pressed = True

        # Mimic a physical held key more closely than the previous pulse tests.
        # The key stays logically down while repeated KEYDOWN events are emitted.
        time.sleep(repeat_delay)
        repeat_started = time.monotonic()
        repeat_budget = max(0.0, repeat_seconds - repeat_delay)
        while time.monotonic() - repeat_started < repeat_budget:
            _send_scan_code(scan_code, down=True)
            repeats += 1
            time.sleep(repeat_interval)

        _send_scan_code(scan_code, down=False)
        pressed = False
        print(f"INPUT repeated_down_events={repeats}")

        print(f"INPUT comparison_tap={tap_key}")
        controller.apply_keys((tap_key,))
        time.sleep(tap_seconds)
        controller.apply_keys(())
        time.sleep(0.35)
        print("INPUT TEST COMPLETE / TESTE CONCLUÍDO")
        return 0
    finally:
        if pressed:
            try:
                _send_scan_code(scan_code, down=False)
            except Exception:
                pass
        controller.release_all()


if __name__ == "__main__":
    raise SystemExit(main())
