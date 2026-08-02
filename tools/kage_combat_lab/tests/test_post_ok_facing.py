from pathlib import Path

from kage_combat_lab.post_ok_facing import perform_post_ok_right_pulse


class FakeController:
    def __init__(self):
        self.repeat_keys = {"r"}
        self.calls = []

    def activate(self):
        self.calls.append(("activate",))

    def apply_keys(self, keys):
        self.calls.append(tuple(keys))

    def release_all(self):
        self.calls.append(("release_all",))


def test_post_ok_right_pulse_is_exclusive_and_has_exact_timing():
    controller = FakeController()
    sleeps = []
    actions = perform_post_ok_right_pulse(controller, sleep_fn=sleeps.append)
    assert controller.repeat_keys == set()
    assert controller.calls.count(("right",)) == 1
    assert ("r", "right") not in controller.calls
    assert ("r",) not in controller.calls
    assert sleeps == [0.3, 0.09, 0.12]
    assert actions == (
        "POST_OK_SETTLE_300MS",
        "STARTUP_RIGHT_PULSE_90MS",
        "STARTUP_RIGHT_SETTLE_120MS",
    )


def test_runtime_order_places_pulse_before_loop_and_prevents_child_duplicate():
    package_root = Path(__file__).resolve().parents[1] / "kage_combat_lab"
    full_loop = (package_root / "full_loop.py").read_text(encoding="utf-8")
    child = (package_root / "full_round_daynight.py").read_text(encoding="utf-8")
    inherited = (package_root / "runtime_startup_inherited.py").read_text(encoding="utf-8")

    assert full_loop.index("install_post_ok_right_pulse()") < full_loop.index(
        "import kage_pilot_loop as canonical_loop"
    )
    assert child.index("install_runtime_facing_patch(full_round_module)") < child.index(
        "install_inherited_post_ok_startup()"
    )
    assert "duplicate=false" in inherited
    assert "self.controller.release_all()" in inherited
    assert "startup_face_right()" not in inherited
