from __future__ import annotations

from pathlib import Path
import os
import re
import subprocess
import sys

from .dojo_debug_v351 import (
    DojoDebugSettings,
    canonical_debug_control_path,
    read_debug_settings,
    write_debug_settings,
)
from .dojo_journal_v351 import (
    DojoSessionJournal,
    canonical_dojo_log_dir,
    latest_dojo_error,
)
from .dojo_templates import DEFAULT_DOJO_TEMPLATE_STORE
from .dojo_training import (
    DojoTrainingConfig,
    DojoTrainingPhase,
    DojoTrainingService as _BaseDojoTrainingService,
    DojoTrainingSnapshot,
)


class DojoTrainingService(_BaseDojoTrainingService):
    """Stable public facade with crash-safe 3.5.1 Dojo diagnostics."""

    _COMPLETED_RE = re.compile(
        r"^\s*(?:DOJO_LOOP_(?:FINISHED|STOPPED)|DOJO_FINAL)\b.*\bcompleted=(\d+)\b",
        re.IGNORECASE,
    )
    _FLOAT_FIELD = re.compile(r"\b(?P<key>x|y|confidence|position_confidence)=(-?\d+(?:\.\d+)?)")
    _POSITION_STATE = re.compile(r"\bposition_state=(KNOWN|UNCERTAIN|LOST)\b", re.IGNORECASE)
    _DIRECT_STATE = re.compile(r"^DOJO_POSITION_STATE\b.*\bstate=(KNOWN|UNCERTAIN|LOST)\b", re.IGNORECASE)
    _TELEMETRY_FIELD = re.compile(r"\b(?P<key>[a-z_]+)=(?P<value>\"[^\"]*\"|\S+)", re.IGNORECASE)
    _POST_STATE = re.compile(r"^POST\s+(?P<state>[A-Z_]+)\b", re.IGNORECASE)
    _ACTION_MARKERS = (
        "ROUND ",
        "DOJO_ANCHOR_SET",
        "DOJO_POSITION_UPDATE",
        "DOJO_EXTERNAL_DISPLACEMENT",
        "DOJO_VISUAL_ODOMETRY_LOST",
        "DOJO_RELOCALIZATION_",
        "DOJO_RETURN_",
        "DOJO_SAFE_LOCAL_SEARCH_",
        "DOJO_SEARCH_FALLBACK_BEGIN",
        "DOJO_MEDITATION_",
        "DOJO_COMBAT_START_BLOCKED",
        "DOJO_RECOVERY_ABORTED",
        "DOJO_DEBUG_OVERLAY_",
        "VICTORY_CHAT",
        "POST_COMBAT",
        "READY / PRONTO",
        "F12 STOP",
    )

    def __init__(self, *args, **kwargs) -> None:
        self._journal: DojoSessionJournal | None = None
        self._last_journal_path = ""
        self.position_state = "LOST"
        self.position_x = 0.0
        self.position_y = 0.0
        self.position_confidence = 0.0
        self.recent_actions: tuple[str, ...] = ()
        self.debug_settings = read_debug_settings()
        self.meditation_state = "IDLE"
        self.meditation_elapsed = 0.0
        self.meditation_hp: float | None = None
        self.meditation_chakra: float | None = None
        self.v_cooldown_remaining = 0.0
        self.combat_start_blocked = False
        DojoSessionJournal.recover_abandoned()
        super().__init__(*args, **kwargs)

    @property
    def is_frozen_runtime(self) -> bool:
        return bool(getattr(sys, "frozen", False))

    @property
    def packaged_helper_path(self) -> Path:
        return Path(sys.executable).resolve().with_name("KagePilotDojo.exe")

    @property
    def script_path(self) -> Path:
        if self.is_frozen_runtime:
            return self.packaged_helper_path
        return self.project_dir / "kage_pilot_loop.py"

    def build_command(self, config: DojoTrainingConfig) -> list[str]:
        value = config.normalized()
        if self.is_frozen_runtime:
            return [str(self.packaged_helper_path), *value.to_cli_args()]
        return [self.python_executable, str(self.script_path), *value.to_cli_args()]

    def runtime_available(self) -> bool:
        return self.script_path.exists()

    def log_status(self) -> dict:
        payload = latest_dojo_error().to_dict()
        payload["directory"] = str(canonical_dojo_log_dir())
        return payload

    def current_debug_settings(self) -> DojoDebugSettings:
        """Refresh settings written by the UI or the in-game F10 toggle."""

        self.debug_settings = read_debug_settings()
        return self.debug_settings

    def configure_debug(
        self,
        *,
        enabled: bool | None = None,
        opacity: float | None = None,
        fps: float | None = None,
        level: str | None = None,
        meditation_enter_delay_seconds: float | None = None,
        meditation_exit_delay_seconds: float | None = None,
        meditation_timeout_seconds: float | None = None,
    ) -> DojoDebugSettings:
        current = self.debug_settings
        settings = DojoDebugSettings(
            enabled=current.enabled if enabled is None else bool(enabled),
            opacity=current.opacity if opacity is None else float(opacity),
            fps=current.fps if fps is None else float(fps),
            level=current.level if level is None else str(level),
            meditation_enter_delay_seconds=(
                current.meditation_enter_delay_seconds
                if meditation_enter_delay_seconds is None
                else float(meditation_enter_delay_seconds)
            ),
            meditation_exit_delay_seconds=(
                current.meditation_exit_delay_seconds
                if meditation_exit_delay_seconds is None
                else float(meditation_exit_delay_seconds)
            ),
            meditation_timeout_seconds=(
                current.meditation_timeout_seconds
                if meditation_timeout_seconds is None
                else float(meditation_timeout_seconds)
            ),
        ).normalized()
        write_debug_settings(settings)
        self.debug_settings = settings
        action = (
            f"DOJO_DEBUG_OVERLAY_SETTINGS enabled={str(settings.enabled).lower()} "
            f"level={settings.level} opacity={settings.opacity:.2f} fps={settings.fps:.1f}"
        )
        self.recent_actions = tuple([*self.recent_actions, action][-8:])
        journal = self._journal
        if journal is not None:
            journal.write("DEBUG_SETTINGS", action)
        return settings

    def _journal_metadata(self, config: DojoTrainingConfig) -> dict:
        try:
            templates = DEFAULT_DOJO_TEMPLATE_STORE.public_status()
        except Exception as exc:
            templates = {"metadata_error": f"{type(exc).__name__}:{exc}"}
        return {
            "kagelink_version": "3.5.1",
            "kage_pilot_runtime": "canonical+visual-position-3.5.1",
            "frozen_runtime": self.is_frozen_runtime,
            "command": self.build_command(config),
            "configuration": config.to_public_dict(),
            "debug": self.debug_settings.to_dict(),
            "templates": templates,
        }

    def start(self, config: DojoTrainingConfig | None = None, **kwargs) -> bool:
        value = (config or DojoTrainingConfig()).normalized()
        self.position_state = "LOST"
        self.position_x = 0.0
        self.position_y = 0.0
        self.position_confidence = 0.0
        self.recent_actions = ()
        self.meditation_state = "IDLE"
        self.meditation_elapsed = 0.0
        self.meditation_hp = None
        self.meditation_chakra = None
        self.v_cooldown_remaining = 0.0
        self.combat_start_blocked = False
        write_debug_settings(self.debug_settings)
        journal = DojoSessionJournal(metadata=self._journal_metadata(value))
        self._journal = journal
        started = super().start(value, **kwargs)
        if not started:
            snapshot = self.snapshot()
            destination = journal.finalize(
                success=False,
                error=snapshot.last_error or "DOJO_START_REJECTED",
                return_code=snapshot.return_code,
                summary={
                    "phase": snapshot.phase.value,
                    "current_round": snapshot.current_round,
                    "completed_rounds": snapshot.completed_rounds,
                },
            )
            self._last_journal_path = str(destination or "")
            self._journal = None
        return started

    @classmethod
    def phase_for_line(cls, line: str, current: DojoTrainingPhase) -> DojoTrainingPhase:
        text = str(line or "").casefold()
        if "dojo_loop_finished" in text or "dojo_loop_stopped" in text:
            return DojoTrainingPhase.STOPPED
        if "dojo_final" in text and "phase=stopped" in text:
            return DojoTrainingPhase.STOPPED
        return super().phase_for_line(line, current)

    @staticmethod
    def _float_value(fields: dict[str, str], key: str) -> float | None:
        value = str(fields.get(key, "") or "").strip().strip('"')
        if not value or value == "-":
            return None
        try:
            return float(value)
        except ValueError:
            return None

    def _update_meditation_telemetry(self, clean: str) -> None:
        post_match = self._POST_STATE.search(clean)
        fields = {
            match.group("key").lower(): match.group("value").strip('"')
            for match in self._TELEMETRY_FIELD.finditer(clean)
        }
        if clean.startswith("DOJO_MEDITATION_STATE"):
            self.meditation_state = str(fields.get("state") or self.meditation_state).upper()
        elif clean.startswith("DOJO_MEDITATION_ENTER_REQUESTED"):
            self.meditation_state = "ENTERING_MEDITATION"
        elif clean.startswith("DOJO_MEDITATION_ENTER_CONFIRMED"):
            self.meditation_state = "MEDITATING"
        elif clean.startswith("DOJO_MEDITATION_EXIT_REQUESTED"):
            self.meditation_state = "EXITING_MEDITATION"
        elif clean.startswith("DOJO_MEDITATION_EXIT_CONFIRMED"):
            self.meditation_state = "READY"
            self.combat_start_blocked = False
        elif clean.startswith("DOJO_MEDITATION_SKIPPED"):
            self.meditation_state = "READY"
            self.combat_start_blocked = False
        elif clean.startswith("DOJO_MEDITATION_TIMEOUT"):
            self.meditation_state = "MEDITATION_TIMEOUT"
            self.combat_start_blocked = True
        elif clean.startswith("DOJO_RECOVERY_ABORTED"):
            self.meditation_state = "ABORTED"
            self.combat_start_blocked = True
        elif post_match is not None:
            state = post_match.group("state").upper()
            if state in {
                "ENTERING_MEDITATION",
                "MEDITATING",
                "EXITING_MEDITATION",
                "MEDITATION_TIMEOUT",
                "READY",
            }:
                self.meditation_state = state

        if clean.startswith("DOJO_COMBAT_START_BLOCKED"):
            self.combat_start_blocked = True
        if self.meditation_state in {"ENTERING_MEDITATION", "MEDITATING", "EXITING_MEDITATION"}:
            self.combat_start_blocked = True

        elapsed = self._float_value(fields, "elapsed")
        cooldown = self._float_value(fields, "cooldown")
        hp = self._float_value(fields, "hp")
        chakra = self._float_value(fields, "chakra")
        if elapsed is not None:
            self.meditation_elapsed = max(0.0, elapsed)
        if cooldown is not None:
            self.v_cooldown_remaining = max(0.0, cooldown)
        if hp is not None:
            self.meditation_hp = max(0.0, min(1.0, hp))
        if chakra is not None:
            self.meditation_chakra = max(0.0, min(1.0, chakra))

    def _update_reliability_telemetry(self, line: str) -> None:
        clean = str(line or "").strip()
        state_match = self._POSITION_STATE.search(clean) or self._DIRECT_STATE.search(clean)
        if state_match is not None:
            self.position_state = state_match.group(1).upper()
        fields: dict[str, float] = {}
        for match in self._FLOAT_FIELD.finditer(clean):
            try:
                fields[match.group("key")] = float(match.group(2))
            except ValueError:
                continue
        if "x" in fields:
            self.position_x = fields["x"]
        if "y" in fields:
            self.position_y = fields["y"]
        if "position_confidence" in fields:
            self.position_confidence = fields["position_confidence"]
        elif "confidence" in fields and any(
            marker in clean
            for marker in (
                "DOJO_POSITION_",
                "DOJO_RELOCALIZATION_CONFIRMED",
                "DOJO_ANCHOR_SET",
            )
        ):
            self.position_confidence = fields["confidence"]
        if clean.startswith("DOJO_ANCHOR_SET"):
            self.position_state = "KNOWN"
            self.position_x = 0.0
            self.position_y = 0.0
            self.position_confidence = 1.0
        if clean.startswith("DOJO_VISUAL_ODOMETRY_LOST") or clean.startswith("DOJO_POSITION_UNKNOWN"):
            self.position_state = "LOST"
        self._update_meditation_telemetry(clean)
        if any(clean.startswith(marker) for marker in self._ACTION_MARKERS):
            actions = [*self.recent_actions, clean]
            self.recent_actions = tuple(actions[-8:])

    def _consume_output_line(self, line: str) -> None:
        journal = self._journal
        if journal is not None:
            journal.write_output(line)
        self._update_reliability_telemetry(line)
        super()._consume_output_line(line)

    def _creation_flags(self) -> int:
        if os.name != "nt":
            return 0
        flags = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        if self.is_frozen_runtime:
            flags |= int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return flags

    def _run(self, config: DojoTrainingConfig) -> None:
        command = self.build_command(config)
        cwd = self.packaged_helper_path.parent if self.is_frozen_runtime else self.project_dir
        caught: BaseException | None = None
        control_path = canonical_debug_control_path()
        write_debug_settings(self.debug_settings, control_path)
        child_env = os.environ.copy()
        child_env["KAGELINK_DOJO_DEBUG_CONTROL"] = str(control_path)
        try:
            process = self._popen_factory(
                command,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=self._creation_flags(),
                env=child_env,
            )
            with self._lock:
                self._process = process
            self._set_phase(DojoTrainingPhase.STARTING, running=True)
            for line in process.stdout or ():
                self._consume_output_line(line)
            return_code = int(process.wait())
            previous = self.snapshot()
            if self._stop_requested:
                final_phase = DojoTrainingPhase.STOPPED
                error = previous.last_error
            elif return_code != 0 or previous.phase == DojoTrainingPhase.ERROR:
                final_phase = DojoTrainingPhase.ERROR
                error = previous.last_error or f"DOJO_PROCESS_EXIT:{return_code}"
            else:
                final_phase = DojoTrainingPhase.STOPPED
                error = previous.last_error
            self._set_phase(
                final_phase,
                running=False,
                last_error=error,
                return_code=return_code,
            )
        except Exception as exc:
            caught = exc
            journal = self._journal
            if journal is not None:
                journal.write_exception(exc)
            self._set_phase(
                DojoTrainingPhase.ERROR,
                running=False,
                last_error=f"{type(exc).__name__}:{exc}",
            )
        finally:
            with self._lock:
                self._process = None
            snapshot = self.snapshot()
            success = snapshot.phase != DojoTrainingPhase.ERROR and (
                snapshot.return_code in (None, 0) or self._stop_requested
            )
            journal = self._journal
            if journal is not None:
                destination = journal.finalize(
                    success=success,
                    error=(
                        snapshot.last_error
                        or (f"{type(caught).__name__}:{caught}" if caught is not None else "")
                    ),
                    return_code=snapshot.return_code,
                    summary={
                        "phase": snapshot.phase.value,
                        "current_round": snapshot.current_round,
                        "completed_rounds": snapshot.completed_rounds,
                        "stop_requested": self._stop_requested,
                        "last_line": snapshot.last_line,
                        "position_state": self.position_state,
                        "position_x": self.position_x,
                        "position_y": self.position_y,
                        "position_confidence": self.position_confidence,
                        "meditation_state": self.meditation_state,
                        "meditation_elapsed": self.meditation_elapsed,
                        "v_cooldown_remaining": self.v_cooldown_remaining,
                        "combat_start_blocked": self.combat_start_blocked,
                        "debug": self.debug_settings.to_dict(),
                    },
                )
                self._last_journal_path = str(destination or "")
                self._journal = None

    def stop(self, *, timeout: float = 8.0) -> bool:
        if not self.is_frozen_runtime or os.name != "nt":
            journal = self._journal
            if journal is not None:
                journal.write("STOP", "requested_by_desktop")
            return super().stop(timeout=timeout)

        with self._lock:
            process = self._process
            thread = self._thread
            if thread is None or not thread.is_alive():
                return False
            self._stop_requested = True
        journal = self._journal
        if journal is not None:
            journal.write("STOP", "requested_by_desktop")
        self._set_phase(DojoTrainingPhase.STOPPING, running=True)

        if process is not None and process.poll() is None:
            pid = int(getattr(process, "pid", 0) or 0)
            if pid > 0:
                try:
                    subprocess.run(
                        ["taskkill", "/PID", str(pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=max(2.0, float(timeout)),
                        check=False,
                        creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
                    )
                except Exception:
                    pass
            try:
                process.wait(timeout=max(0.5, float(timeout)))
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass

        thread.join(timeout=max(0.5, float(timeout)))
        return True


__all__ = [
    "DojoTrainingConfig",
    "DojoTrainingPhase",
    "DojoTrainingService",
    "DojoTrainingSnapshot",
]
