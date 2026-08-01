from __future__ import annotations

from pathlib import Path
import tempfile
import threading
import time
import unittest

from pc_agent.kage_pilot import DojoTrainingConfig, DojoTrainingPhase, DojoTrainingService


class BlockingProcess:
    def __init__(self) -> None:
        self.pid = 0
        self.terminated = threading.Event()
        self.killed = False
        self.return_code = -15
        self.stdout = self._output()

    def _output(self):
        while not self.terminated.wait(0.02):
            continue
        if False:
            yield ""

    def poll(self):
        return self.return_code if self.terminated.is_set() else None

    def wait(self, timeout=None):
        if not self.terminated.wait(timeout):
            raise TimeoutError("process still running")
        return self.return_code

    def terminate(self):
        self.terminated.set()

    def kill(self):
        self.killed = True
        self.terminated.set()


class ImmediateProcess:
    pid = 0

    def __init__(self) -> None:
        self.stdout = iter(("DOJO_LOOP_STOPPED completed=0\n",))

    def poll(self):
        return 0

    def wait(self, timeout=None):
        del timeout
        return 0

    def terminate(self):
        return None

    def kill(self):
        return None


class DojoStopReliabilityV351Tests(unittest.TestCase):
    def _service(self, root: Path, factory) -> DojoTrainingService:
        (root / "kage_pilot_loop.py").write_text("# test\n", encoding="utf-8")
        return DojoTrainingService(
            project_dir=root,
            python_executable="python-test",
            popen_factory=factory,
        )

    def test_stop_cancels_process_created_while_popen_is_still_returning(self):
        factory_entered = threading.Event()
        allow_factory_return = threading.Event()
        process = BlockingProcess()

        def delayed_factory(*args, **kwargs):
            del args, kwargs
            factory_entered.set()
            if not allow_factory_return.wait(3.0):
                raise TimeoutError("test did not release Popen")
            return process

        with tempfile.TemporaryDirectory() as directory:
            service = self._service(Path(directory), delayed_factory)
            self.assertTrue(service.start(DojoTrainingConfig()))
            self.assertTrue(factory_entered.wait(1.0))

            result: list[bool] = []
            stop_thread = threading.Thread(
                target=lambda: result.append(service.stop(timeout=2.5)),
                daemon=True,
            )
            stop_thread.start()
            time.sleep(0.10)
            allow_factory_return.set()
            stop_thread.join(4.0)
            snapshot = service.wait(timeout=2.0)

        self.assertFalse(stop_thread.is_alive())
        self.assertEqual(result, [True])
        self.assertTrue(process.terminated.is_set())
        self.assertFalse(snapshot.running)
        self.assertEqual(snapshot.phase, DojoTrainingPhase.STOPPED)

    def test_stale_running_snapshot_does_not_block_next_start(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self._service(Path(directory), lambda *args, **kwargs: ImmediateProcess())
            service._set_phase(DojoTrainingPhase.STARTING, running=True)
            service._thread = None

            self.assertTrue(service.start(DojoTrainingConfig()))
            snapshot = service.wait(timeout=2.0)

        self.assertFalse(snapshot.running)
        self.assertEqual(snapshot.phase, DojoTrainingPhase.STOPPED)

    def test_stop_is_idempotent_after_startup_failure(self):
        def failing_factory(*args, **kwargs):
            del args, kwargs
            raise RuntimeError("Popen failed")

        with tempfile.TemporaryDirectory() as directory:
            service = self._service(Path(directory), failing_factory)
            self.assertTrue(service.start(DojoTrainingConfig()))
            failed = service.wait(timeout=2.0)
            first = service.stop(timeout=0.5)
            second = service.stop(timeout=0.5)
            stopped = service.snapshot()

        self.assertEqual(failed.phase, DojoTrainingPhase.ERROR)
        self.assertFalse(first)
        self.assertFalse(second)
        self.assertFalse(stopped.running)
        self.assertEqual(stopped.phase, DojoTrainingPhase.STOPPED)


if __name__ == "__main__":
    unittest.main()
