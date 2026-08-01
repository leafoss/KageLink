from __future__ import annotations


MESSAGE = """DOJO_TRAINER_CALIBRATION_DISABLED

PT-BR:
As imagens oficiais do Dojo Trainer são referências RAW imutáveis fornecidas por Rafael.
Este utilitário não captura, recorta, redimensiona, filtra ou substitui essas imagens.
Use os modos de célula 32 e 64 já incluídos no KageLink.

EN-US:
The official Dojo Trainer images are immutable RAW references supplied by Rafael.
This utility does not capture, crop, resize, filter, or replace those images.
Use the cell modes 32 and 64 already included with KageLink.
"""


def main() -> int:
    print(MESSAGE.strip())
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
