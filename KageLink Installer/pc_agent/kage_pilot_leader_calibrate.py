from __future__ import annotations

import argparse
from pathlib import Path
import time

import cv2

from pc_agent.kage_pilot.entity_observer import decode_jpeg
from pc_agent.kage_pilot.post_combat_v03b import DEFAULT_LEADER_TEMPLATE_PATH
from pc_agent.kage_pilot.recorder import WindowsGameFrameSource


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Capture the current game frame and teach the fixed Dojo leader sprite / "
            "captura o jogo e ensina o sprite fixo do lider do Dojo"
        )
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_LEADER_TEMPLATE_PATH)
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()

    source = WindowsGameFrameSource()
    try:
        print("Kage Pilot v0.3b DOJO LEADER CALIBRATION")
        print("READ ONLY / SOMENTE LEITURA - nenhuma tecla sera enviada ao jogo")
        print("Deixe o lider totalmente visivel. Captura em / capture in %.1fs" % max(0.0, args.delay))
        time.sleep(max(0.0, float(args.delay)))
        frame = decode_jpeg(bytes(source.capture().jpeg))
    finally:
        source.close()

    window = "Kage Pilot - Select Dojo Leader / Selecione o Lider"
    print("Na janela: arraste um retangulo em torno do lider + pequena margem do piso.")
    print("ENTER ou ESPACO confirma; ESC cancela.")
    roi = cv2.selectROI(window, frame, showCrosshair=True, fromCenter=False)
    cv2.destroyWindow(window)

    x, y, width, height = (int(value) for value in roi)
    if width < 8 or height < 8:
        print("Calibration cancelled / Calibracao cancelada: ROI muito pequena ou ESC")
        return 2

    crop = frame[y:y + height, x:x + width]
    if crop.size == 0:
        print("Calibration failed / Falha na calibracao: recorte vazio")
        return 3

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), crop):
        print(f"Calibration failed / Falha ao salvar: {output}")
        return 4

    diagnostic = output.with_name(output.stem + "_frame.png")
    marked = frame.copy()
    cv2.rectangle(marked, (x, y), (x + width, y + height), (255, 255, 255), 2)
    cv2.imwrite(str(diagnostic), marked)

    print(f"CALIBRATION_OK / CALIBRACAO_OK: {output}")
    print(f"bbox={x},{y},{width},{height} template={width}x{height}")
    print(f"diagnostic_frame={diagnostic}")
    print("Agora rode kage_pilot_postcombat_probe_v2.py / Now run the v2 probe")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
