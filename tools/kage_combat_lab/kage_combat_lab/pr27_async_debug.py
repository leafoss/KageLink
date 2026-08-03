from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, Thread
from typing import Callable

import cv2
import numpy as np


@dataclass(frozen=True, slots=True)
class DebugWriteItem:
    image: np.ndarray
    path: Path


class AsyncDebugWriter:
    """Bounded non-blocking PNG writer for combat diagnostics."""

    def __init__(self, *, max_queue: int = 24, imwrite: Callable = cv2.imwrite) -> None:
        self.queue: Queue[DebugWriteItem | None] = Queue(maxsize=max(2, int(max_queue)))
        self.imwrite = imwrite
        self.saved_frames = 0
        self.dropped_frames = 0
        self.failed_frames = 0
        self._closed = False
        self._done = Event()
        self._thread = Thread(target=self._run, name="PR27AsyncDebugWriter", daemon=True)
        self._thread.start()

    def enqueue(self, image: np.ndarray, path: Path) -> bool:
        if self._closed:
            self.dropped_frames += 1
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        item = DebugWriteItem(np.ascontiguousarray(image).copy(), path)
        try:
            self.queue.put_nowait(item)
            return True
        except Full:
            self.dropped_frames += 1
            return False

    def _run(self) -> None:
        try:
            while True:
                try:
                    item = self.queue.get(timeout=0.1)
                except Empty:
                    if self._closed:
                        break
                    continue
                try:
                    if item is None:
                        break
                    success = bool(self.imwrite(str(item.path), item.image))
                    if success:
                        self.saved_frames += 1
                    else:
                        self.failed_frames += 1
                except Exception:
                    self.failed_frames += 1
                finally:
                    self.queue.task_done()
        finally:
            self._done.set()

    def close(self, *, timeout: float = 8.0) -> None:
        if self._closed:
            self._done.wait(timeout=max(0.0, timeout))
            return
        self._closed = True
        try:
            self.queue.put_nowait(None)
        except Full:
            # Drop one pending debug image rather than block combat shutdown.
            try:
                self.queue.get_nowait()
                self.queue.task_done()
                self.dropped_frames += 1
            except Empty:
                pass
            try:
                self.queue.put_nowait(None)
            except Full:
                pass
        self._done.wait(timeout=max(0.0, timeout))

    @property
    def pending_frames(self) -> int:
        return self.queue.qsize()
