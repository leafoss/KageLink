from __future__ import annotations

import os
import subprocess
import threading
import time

from .dojo_training import DojoTrainingPhase


class _DojoStartupCancellation:
    """Per-service cancellation state that also covers the Popen registration race."""

    def __init__(self) -> None:
        self.event = threading.Event()


def _process_alive(process) -> bool:
    if process is None:
        return False
    try:
        return process.poll() is None
    except Exception:
        return True


def _taskkill_pid(pid: int, timeout: float) -> None:
    if os.name != "nt" or int(pid) <= 0:
        return
    try:
        subprocess.run(
            ["taskkill", "/PID", str(int(pid)), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=max(1.0, float(timeout)),
            check=False,
            creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
        )
    except Exception:
        pass


def _taskkill_helpers(timeout: float) -> None:
    if os.name != "nt":
        return
    for image in ("KagePilotRound.exe", "KagePilotDojo.exe"):
        try:
            subprocess.run(
                ["taskkill", "/IM", image, "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=max(1.0, float(timeout)),
                check=False,
                creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
            )
        except Exception:
            pass


def _terminate_process_tree(process, *, timeout: float) -> None:
    if process is None:
        return
    pid = int(getattr(process, "pid", 0) or 0)
    if os.name == "nt" and pid > 0:
        _taskkill_pid(pid, timeout)
    else:
        try:
            process.terminate()
        except Exception:
            pass

    try:
        process.wait(timeout=max(0.25, float(timeout)))
        return
    except Exception:
        pass

    try:
        process.kill()
    except Exception:
        pass
    try:
        process.wait(timeout=1.0)
    except Exception:
        pass


def install_dojo_stop_reliability(service_class) -> None:
    """Make Stop work before, during and after a failed Dojo startup."""

    if bool(getattr(service_class, "_kagelink_stop_reliability", False)):
        return

    original_init = service_class.__init__
    original_start = service_class.start
    original_run = service_class._run

    def __init__(self, *args, **kwargs) -> None:
        original_init(self, *args, **kwargs)
        self._dojo_startup_cancellation = _DojoStartupCancellation()

    def start(self, config=None, **kwargs) -> bool:
        cancellation = getattr(self, "_dojo_startup_cancellation", None)
        if cancellation is None:
            cancellation = _DojoStartupCancellation()
            self._dojo_startup_cancellation = cancellation

        # A previous helper may have died between status polls. Never let a stale
        # running snapshot permanently block a new Start.
        with self._lock:
            thread = self._thread
            stale = self.snapshot().running and (thread is None or not thread.is_alive())
        if stale:
            self._set_phase(DojoTrainingPhase.STOPPED, running=False)
        cancellation.event.clear()
        return original_start(self, config, **kwargs)

    def _run(self, config) -> None:
        cancellation = getattr(self, "_dojo_startup_cancellation", None)
        if cancellation is None:
            cancellation = _DojoStartupCancellation()
            self._dojo_startup_cancellation = cancellation
        if cancellation.event.is_set():
            self._stop_requested = True
            self._set_phase(DojoTrainingPhase.STOPPED, running=False)
            return

        original_factory = self._popen_factory

        def cancellation_aware_factory(*args, **kwargs):
            process = original_factory(*args, **kwargs)
            # Stop may be clicked while Popen is still returning. Kill the new process
            # before it can enter Trainer search, then let the normal reader unwind.
            if cancellation.event.is_set():
                _terminate_process_tree(process, timeout=2.0)
            return process

        self._popen_factory = cancellation_aware_factory
        try:
            original_run(self, config)
        finally:
            if self._popen_factory is cancellation_aware_factory:
                self._popen_factory = original_factory
            if cancellation.event.is_set():
                self._set_phase(
                    DojoTrainingPhase.STOPPED,
                    running=False,
                    last_error=self.snapshot().last_error,
                )

    def stop(self, *, timeout: float = 8.0) -> bool:
        cancellation = getattr(self, "_dojo_startup_cancellation", None)
        if cancellation is None:
            cancellation = _DojoStartupCancellation()
            self._dojo_startup_cancellation = cancellation
        cancellation.event.set()

        with self._lock:
            process = self._process
            thread = self._thread
            snapshot = self._snapshot
            thread_alive = thread is not None and thread.is_alive()
            active = bool(snapshot.running or thread_alive or _process_alive(process))
            self._stop_requested = True

        journal = getattr(self, "_journal", None)
        if journal is not None:
            try:
                journal.write("STOP", "requested_by_desktop_startup_safe")
            except Exception:
                pass

        if active:
            self._set_phase(DojoTrainingPhase.STOPPING, running=True)

        # Cover the short interval between Thread.start() and self._process assignment.
        registration_deadline = time.monotonic() + min(1.25, max(0.25, float(timeout) * 0.25))
        while process is None and thread_alive and time.monotonic() < registration_deadline:
            time.sleep(0.025)
            with self._lock:
                process = self._process
                thread = self._thread
                thread_alive = thread is not None and thread.is_alive()

        if process is not None:
            _terminate_process_tree(process, timeout=max(1.0, float(timeout) * 0.55))

        # /T normally catches the isolated round helper. The image-name fallback is
        # intentionally limited to Kage Pilot helpers and never touches KageLink.exe.
        if os.name == "nt" and (process is None or _process_alive(process)):
            _taskkill_helpers(max(1.0, float(timeout) * 0.35))

        if thread is not None:
            thread.join(timeout=max(0.5, float(timeout)))
            if thread.is_alive() and os.name == "nt":
                _taskkill_helpers(2.0)
                thread.join(timeout=1.0)

        with self._lock:
            current_thread = self._thread
            current_process = self._process
            if current_thread is not None and not current_thread.is_alive():
                self._thread = None
            if current_process is not None and not _process_alive(current_process):
                self._process = None

        self._set_phase(
            DojoTrainingPhase.STOPPED,
            running=False,
            last_error=self.snapshot().last_error,
        )
        return active

    service_class.__init__ = __init__
    service_class.start = start
    service_class._run = _run
    service_class.stop = stop
    service_class._kagelink_stop_reliability = True


__all__ = ["install_dojo_stop_reliability"]
