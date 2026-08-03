from __future__ import annotations

import tkinter as tk

from capture_runtime import TsharkCapture, TsharkInterface
from observer_ui import ObserverApp

__all__ = ["ObserverApp", "TsharkCapture", "TsharkInterface"]


def main() -> int:
    root = tk.Tk()
    ObserverApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
