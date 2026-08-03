from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from typing import Any


class AsyncDebugWriter:
    """Bounded background writer with explicit flush and error collection."""

    def __init__(self, max_queue_size: int = 64) -> None:
        self.queue: queue.Queue[Any] = queue.Queue(maxsize=max(4, int(max_queue_size)))
        self.errors: list[str] = []
        self._closed = False
        self._thread = threading.Thread(target=self._run, name="enemy-debug-writer", daemon=True)
        self._thread.start()

    @property
    def pending(self) -> int:
        return self.queue.qsize()

    def submit(self, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        if self._closed:
            raise RuntimeError("debug writer is closed")
        self.queue.put((callback, args, kwargs))

    def _run(self) -> None:
        while True:
            item = self.queue.get()
            try:
                if item is None:
                    return
                callback, args, kwargs = item
                callback(*args, **kwargs)
            except Exception as exc:  # debug failures must not kill perception
                self.errors.append(f"{type(exc).__name__}: {exc}")
            finally:
                self.queue.task_done()

    def flush(self) -> None:
        self.queue.join()

    def close(self) -> None:
        if self._closed:
            return
        self.flush()
        self._closed = True
        self.queue.put(None)
        self._thread.join(timeout=10.0)
