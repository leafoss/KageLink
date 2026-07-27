from __future__ import annotations

import io
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageStat


@dataclass(frozen=True, slots=True)
class TemplateRule:
    path: Path
    region: tuple[float, float, float, float]
    max_distance: float = 0.08

    @classmethod
    def from_dict(cls, raw: dict[str, Any], *, base_dir: Path) -> "TemplateRule":
        region = tuple(float(v) for v in raw["region"])
        if len(region) != 4 or any(v < 0.0 or v > 1.0 for v in region):
            raise ValueError("INVALID_TEMPLATE_REGION")
        if region[2] <= 0.0 or region[3] <= 0.0 or region[0] + region[2] > 1.0 or region[1] + region[3] > 1.0:
            raise ValueError("INVALID_TEMPLATE_REGION")
        raw_path = Path(raw["path"])
        return cls(
            path=(base_dir / raw_path).resolve() if not raw_path.is_absolute() else raw_path,
            region=region,
            max_distance=float(raw.get("max_distance", 0.08)),
        )


class VisualTemplateDetector:
    def __init__(self, rule: TemplateRule) -> None:
        self.rule = rule
        with Image.open(rule.path) as image:
            self.template = image.convert("L").copy()

    @staticmethod
    def crop_frame(jpeg: bytes, region: tuple[float, float, float, float]) -> Image.Image:
        with Image.open(io.BytesIO(jpeg)) as image:
            gray = image.convert("L")
            width, height = gray.size
            x, y, w, h = region
            box = (
                max(0, round(x * width)),
                max(0, round(y * height)),
                min(width, round((x + w) * width)),
                min(height, round((y + h) * height)),
            )
            return gray.crop(box).copy()

    def distance(self, jpeg: bytes) -> float:
        crop = self.crop_frame(jpeg, self.rule.region)
        if crop.size != self.template.size:
            crop = crop.resize(self.template.size, Image.Resampling.BILINEAR)
        diff = ImageChops.difference(crop, self.template)
        mean = ImageStat.Stat(diff).mean[0]
        return float(mean) / 255.0

    def matches(self, jpeg: bytes) -> bool:
        return self.distance(jpeg) <= self.rule.max_distance


@dataclass(frozen=True, slots=True)
class DojoConfig:
    start_sequence: tuple[dict[str, Any], ...]
    rest_sequence: tuple[dict[str, Any], ...]
    post_start_delay_seconds: float
    post_result_delay_seconds: float
    rest_seconds: float
    combat_timeout_seconds: float
    victory: TemplateRule
    defeat: TemplateRule | None = None
    rested: TemplateRule | None = None

    @classmethod
    def load(cls, path: Path) -> "DojoConfig":
        config_path = Path(path)
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        base = config_path.parent
        return cls(
            start_sequence=tuple(raw.get("start_sequence", ())),
            rest_sequence=tuple(raw.get("rest_sequence", ())),
            post_start_delay_seconds=float(raw.get("post_start_delay_seconds", 1.0)),
            post_result_delay_seconds=float(raw.get("post_result_delay_seconds", 1.0)),
            rest_seconds=float(raw.get("rest_seconds", 5.0)),
            combat_timeout_seconds=float(raw.get("combat_timeout_seconds", 180.0)),
            victory=TemplateRule.from_dict(raw["victory"], base_dir=base),
            defeat=TemplateRule.from_dict(raw["defeat"], base_dir=base) if raw.get("defeat") else None,
            rested=TemplateRule.from_dict(raw["rested"], base_dir=base) if raw.get("rested") else None,
        )


class SequenceExecutor:
    def __init__(self, controller, *, sleep_fn=time.sleep) -> None:
        self.controller = controller
        self.sleep_fn = sleep_fn

    def execute(self, sequence: tuple[dict[str, Any], ...]) -> None:
        for step in sequence:
            kind = str(step.get("type", "")).strip().lower()
            if kind == "key":
                self.controller.tap(str(step["key"]), float(step.get("duration", 0.08)))
            elif kind == "click":
                self.controller.click_normalized(float(step["x"]), float(step["y"]))
            elif kind == "wait":
                self.sleep_fn(max(0.0, float(step.get("seconds", 0.1))))
            else:
                raise ValueError(f"INVALID_DOJO_STEP:{kind}")


class DojoManager:
    """Deterministic outer loop; learned Pilot owns only combat decisions."""

    def __init__(
        self,
        config: DojoConfig,
        frame_source,
        controller,
        pilot,
        *,
        victory_detector=None,
        defeat_detector=None,
        rested_detector=None,
        sleep_fn=time.sleep,
        time_fn=time.monotonic,
    ) -> None:
        self.config = config
        self.frame_source = frame_source
        self.controller = controller
        self.pilot = pilot
        self.sleep_fn = sleep_fn
        self.time_fn = time_fn
        self.sequence = SequenceExecutor(controller, sleep_fn=sleep_fn)
        self.victory_detector = victory_detector or VisualTemplateDetector(config.victory)
        self.defeat_detector = defeat_detector or (VisualTemplateDetector(config.defeat) if config.defeat else None)
        self.rested_detector = rested_detector or (VisualTemplateDetector(config.rested) if config.rested else None)

    def run_cycle(self) -> str:
        self.controller.activate()
        self.controller.release_all()
        reset = getattr(self.pilot, "reset", None)
        if callable(reset):
            reset()
        self.sequence.execute(self.config.start_sequence)
        self.sleep_fn(max(0.0, self.config.post_start_delay_seconds))
        started = self.time_fn()
        result = "timeout"
        try:
            while self.time_fn() - started < self.config.combat_timeout_seconds:
                frame = self.frame_source.capture()
                jpeg = bytes(frame.jpeg)
                if self.victory_detector.matches(jpeg):
                    result = "victory"
                    break
                if self.defeat_detector is not None and self.defeat_detector.matches(jpeg):
                    result = "defeat"
                    break
                self.pilot.step()
                self.sleep_fn(1.0 / self.pilot.decision_hz)
        finally:
            self.controller.release_all()
        if result == "timeout":
            return result
        self.sleep_fn(max(0.0, self.config.post_result_delay_seconds))
        self.sequence.execute(self.config.rest_sequence)
        if self.rested_detector is None:
            self.sleep_fn(max(0.0, self.config.rest_seconds))
        else:
            rest_started = self.time_fn()
            while self.time_fn() - rest_started < max(self.config.rest_seconds, 1.0) * 6.0:
                frame = self.frame_source.capture()
                if self.rested_detector.matches(bytes(frame.jpeg)):
                    break
                self.sleep_fn(0.25)
        return result

    def run(self, cycles: int = 1) -> list[str]:
        output: list[str] = []
        for _ in range(max(1, int(cycles))):
            result = self.run_cycle()
            output.append(result)
            if result == "timeout":
                break
        return output


def save_template(jpeg: bytes, region: tuple[float, float, float, float], output: Path) -> Path:
    crop = VisualTemplateDetector.crop_frame(jpeg, region)
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    crop.save(path, format="PNG")
    return path


def default_config_text() -> str:
    payload = {
        "start_sequence": [
            {"type": "click", "x": 0.50, "y": 0.50},
            {"type": "wait", "seconds": 0.25},
            {"type": "key", "key": "enter", "duration": 0.08},
        ],
        "rest_sequence": [
            {"type": "key", "key": "v", "duration": 0.08},
        ],
        "post_start_delay_seconds": 1.0,
        "post_result_delay_seconds": 1.0,
        "rest_seconds": 5.0,
        "combat_timeout_seconds": 180.0,
        "victory": {"path": "templates/victory.png", "region": [0.35, 0.15, 0.30, 0.15], "max_distance": 0.08},
        "defeat": None,
        "rested": None,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
