from __future__ import annotations


class EnemyPerceptionWindow:
    """Small live diagnostic window for the passive enemy perception laboratory."""

    def __init__(
        self,
        engine,
        capture,
        capture_interval: float = 0.20,
        title: str = "Kage Enemy Perception Lab",
    ) -> None:
        self.engine = engine
        self.capture = capture
        self.interval = max(0.05, float(capture_interval))
        self.title = title
        self.running = True

    def run(self) -> None:
        import tkinter as tk

        from PIL import Image, ImageTk

        root = tk.Tk()
        root.title(self.title)
        label = tk.Label(root)
        label.pack(fill="both", expand=True)
        status = tk.StringVar(value="starting")
        tk.Label(root, textvariable=status, anchor="w").pack(fill="x")

        def tick() -> None:
            if not self.running:
                return
            try:
                import cv2

                frame, bounds = self.capture.capture()
                result, images = self.engine.process_frame(
                    frame,
                    {
                        "title": bounds.title,
                        "hwnd": bounds.hwnd,
                        "width": bounds.width,
                        "height": bounds.height,
                        "capture_backend": bounds.capture_backend,
                    },
                )
                rgb = cv2.cvtColor(
                    images["08_hostility_overlay.png"],
                    cv2.COLOR_BGR2RGB,
                )
                photo = ImageTk.PhotoImage(Image.fromarray(rgb))
                label.configure(image=photo)
                label.image = photo
                debug_path = (
                    self.engine.recorder.session_root
                    if self.engine.recorder
                    else "off"
                )
                status.set(
                    f"frame={result.frame_index} entities={len(result.entities)} "
                    f"ms={result.processing_time_ms:.1f} debug={debug_path}"
                )
            except Exception as exc:
                status.set(f"error: {exc}")
            root.after(int(self.interval * 1000), tick)

        def close() -> None:
            self.running = False
            if self.engine.recorder:
                self.engine.recorder.finalize(self.engine.tracker.tracks)
            self.capture.close()
            root.destroy()

        root.protocol("WM_DELETE_WINDOW", close)
        root.after(1, tick)
        root.mainloop()
