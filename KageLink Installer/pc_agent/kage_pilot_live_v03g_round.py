from __future__ import annotations

import time

import kage_pilot_live_v03 as live_v03

from pc_agent.kage_pilot.chat_victory_v03g import RobustChatVictoryWatcher


# Patch the authoritative watcher before importing v0.3e. Its transition subclass will then
# inherit the robust multi-control implementation while preserving begin_post_combat().
live_v03.ChatVictoryWatcher = RobustChatVictoryWatcher

import kage_pilot_live_v03e_round as round_v03e  # noqa: E402


_ACTIVE_CONTROLLER = None


class ClosingMovementProbeController(round_v03e.MovementProbeController):
    """v0.3e movement probe controller with explicit repeat-worker shutdown."""

    def __init__(self, *args, **kwargs) -> None:
        global _ACTIVE_CONTROLLER
        super().__init__(*args, **kwargs)
        self._kage_closed = False
        _ACTIVE_CONTROLLER = self

    def close(self) -> None:
        if self._kage_closed:
            return
        self._kage_closed = True

        # Stop the worker before releasing R so no new repeat KEYDOWN can race with shutdown.
        stop = getattr(self, "_repeat_stop", None)
        if stop is not None:
            stop.set()

        try:
            self.release_all()
        except Exception:
            pass

        thread = getattr(self, "_repeat_thread", None)
        if thread is not None and thread.is_alive():
            thread.join(timeout=0.40)

        # One final key-up after the worker has stopped closes the race completely.
        try:
            self.release_all()
        except Exception:
            pass

        core = getattr(self, "_controller", None)
        if core is not None and hasattr(core, "deactivate"):
            try:
                core.deactivate()
            except Exception:
                pass

        # Let queued keyboard messages drain while the game still owns foreground.
        time.sleep(0.08)


# v0.3e already installed obstacle-aware observer/recovery patches. Replace only its controller.
live_v03.WindowsGameController = ClosingMovementProbeController


def main() -> int:
    print("Kage Pilot v0.3g ROUND: ROBUST MULTI-CHAT VICTORY + SAFE R SHUTDOWN")
    print("KO: any new 'has been Knocked-Out' line -> release all -> post-combat")
    print("COMBAT/OBSTACLE POLICY UNCHANGED / POLITICA DE COMBATE E OBSTACULOS INALTERADA")
    try:
        return round_v03e.main()
    finally:
        controller = _ACTIVE_CONTROLLER
        if controller is not None:
            controller.close()


if __name__ == "__main__":
    raise SystemExit(main())
