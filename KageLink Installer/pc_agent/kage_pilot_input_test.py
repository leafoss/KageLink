from __future__ import annotations

import argparse
import ctypes
import time
from ctypes import wintypes

from pc_agent.kage_pilot.pilot import WindowsGameController


INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
MAPVK_VK_TO_VSC = 0
ULONG_PTR = ctypes.c_size_t


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
_user32.SendInput.restype = wintypes.UINT
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
        description="Kage Pilot hardware scan-code diagnostic / diagnóstico por scan code físico"
    )
    parser.add_argument("--scan-key", default="r", help="Letter to test by hardware scan code / Letra para testar")
    parser.add_argument("--scan-seconds", type=float, default=4.0, help="Total scan-code test duration / Duração total")
    parser.add_argument("--pulse-down", type=float, default=0.08, help="Seconds scan code stays down / Tempo pressionado")
    parser.add_argument("--pulse-gap", type=float, default=0.08, help="Seconds between scan-code pulses / Intervalo")
    parser.add_argument("--tap-key", default="h", help="Known-good virtual-key comparison / Tecla de comparação")
    parser.add_argument("--tap-seconds", type=float, default=0.15, help="Comparison tap duration / Duração do toque")
    parser.add_argument("--startup-delay", type=float, default=3.0, help="Seconds after game focus before input / Atraso após foco")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    scan_key = str(args.scan_key).strip().lower()
    tap_key = str(args.tap_key).strip().lower()
    scan_seconds = max(0.5, float(args.scan_seconds))
    pulse_down = max(0.02, float(args.pulse_down))
    pulse_gap = max(0.02, float(args.pulse_gap))
    tap_seconds = max(0.03, float(args.tap_seconds))
    startup_delay = max(0.0, float(args.startup_delay))
    scan_code = _scan_code_for_letter(scan_key)

    print("Kage Pilot SCAN-CODE INPUT TEST / TESTE DE SCAN CODE")
    print(f"hardware scan: {scan_key.upper()} = 0x{scan_code:02X}")

    controller = WindowsGameController(recover_foreground=True, debug=True)
    controller.activate()
    controller.release_all()

    print("Shinobi Story Online em foco / in foreground")
    print(f"Em / in {startup_delay:.1f}s: pulsos físicos / hardware pulses {scan_key.upper()}")
    time.sleep(startup_delay)

    started = time.monotonic()
    pulses = 0
    try:
        print(f"INPUT scan_pulse={scan_key}")
        while time.monotonic() - started < scan_seconds:
            _send_scan_code(scan_code, down=True)
            time.sleep(pulse_down)
            _send_scan_code(scan_code, down=False)
            pulses += 1
            time.sleep(pulse_gap)

        print(f"INPUT scan_pulses={pulses}")
        print(f"INPUT comparison_tap={tap_key}")
        controller.apply_keys((tap_key,))
        time.sleep(tap_seconds)
        controller.apply_keys(())
        time.sleep(0.35)
        print("INPUT TEST COMPLETE / TESTE CONCLUÍDO")
        return 0
    finally:
        # Always release the scan-code key as well as controller-managed keys.
        try:
            _send_scan_code(scan_code, down=False)
        except Exception:
            pass
        controller.release_all()


if __name__ == "__main__":
    raise SystemExit(main())
