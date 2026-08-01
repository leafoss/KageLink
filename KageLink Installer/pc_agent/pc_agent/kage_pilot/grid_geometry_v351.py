from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Callable, Literal


GridCellSize = Literal[32, 64]
GridMode = Literal["32", "64"]
Telemetry = Callable[[str, dict[str, object]], None]


class InvalidGridGeometryError(ValueError):
    pass


_EMITTED_SIGNATURES: set[tuple[str, int, float]] = set()
_ACTIVE_GEOMETRY: "GridGeometry | None" = None


def _fail(
    reason: str,
    *,
    mode: object,
    cell_size: object,
    telemetry: Telemetry | None = None,
) -> None:
    fields = {
        "reason": str(reason),
        "game_mode": str(mode),
        "cell_size": str(cell_size),
        "allowed_cell_sizes": "32,64",
        "source": "game_mode",
    }
    if telemetry is not None:
        telemetry("DOJO_INVALID_GRID_GEOMETRY", fields)
    else:
        print(
            "DOJO_INVALID_GRID_GEOMETRY " + json.dumps(fields, sort_keys=True),
            flush=True,
        )
    raise InvalidGridGeometryError(f"DOJO_INVALID_GRID_GEOMETRY:{reason}")


@dataclass(frozen=True, slots=True)
class GridGeometry:
    """Absolute navigation geometry for the original RAW client frame.

    Trainer crops and character bboxes are visual evidence only. They never define
    the logical grid. The game exposes exactly two cell modes: 32 and 64 pixels.
    """

    mode: GridMode
    cell_size: GridCellSize
    source: str = "game_mode"
    capture_scale: float = 1.0
    template_dimensions_ignored: bool = True

    @classmethod
    def from_mode(
        cls,
        mode: str | int,
        *,
        cell_size: int | float | None = None,
        template_dimensions: tuple[int, int] | None = None,
        telemetry: Telemetry | None = None,
    ) -> "GridGeometry":
        del template_dimensions
        normalized = str(mode).strip()
        if normalized not in {"32", "64"}:
            _fail(
                "MODE_NOT_32_OR_64",
                mode=mode,
                cell_size=cell_size,
                telemetry=telemetry,
            )
        expected = int(normalized)
        actual = expected if cell_size is None else int(round(float(cell_size)))
        if actual not in {32, 64}:
            _fail(
                "CELL_SIZE_NOT_32_OR_64",
                mode=normalized,
                cell_size=cell_size,
                telemetry=telemetry,
            )
        if actual != expected:
            _fail(
                "MODE_CELL_SIZE_MISMATCH",
                mode=normalized,
                cell_size=actual,
                telemetry=telemetry,
            )
        return cls(
            mode=normalized,  # type: ignore[arg-type]
            cell_size=actual,  # type: ignore[arg-type]
        )

    @classmethod
    def from_cell_size(
        cls,
        cell_size: int | float,
        *,
        telemetry: Telemetry | None = None,
    ) -> "GridGeometry":
        try:
            numeric = float(cell_size)
        except (TypeError, ValueError):
            _fail(
                "CELL_SIZE_NOT_NUMERIC",
                mode="-",
                cell_size=cell_size,
                telemetry=telemetry,
            )
        rounded = int(round(numeric))
        if abs(numeric - rounded) > 1e-9 or rounded not in {32, 64}:
            _fail(
                "CELL_SIZE_NOT_32_OR_64",
                mode="-",
                cell_size=cell_size,
                telemetry=telemetry,
            )
        return cls.from_mode(str(rounded), cell_size=rounded, telemetry=telemetry)

    def as_telemetry(self) -> dict[str, object]:
        return {
            "game_mode": self.mode,
            "cell_size": self.cell_size,
            "source": self.source,
            "capture_scale": self.capture_scale,
            "template_dimensions_ignored": self.template_dimensions_ignored,
        }


def emit_grid_geometry(
    geometry: GridGeometry,
    *,
    telemetry: Telemetry | None = None,
) -> dict[str, object]:
    global _ACTIVE_GEOMETRY
    _ACTIVE_GEOMETRY = geometry
    fields = geometry.as_telemetry()
    signature = (geometry.mode, geometry.cell_size, geometry.capture_scale)
    if signature in _EMITTED_SIGNATURES:
        return fields
    _EMITTED_SIGNATURES.add(signature)
    if telemetry is not None:
        telemetry("DOJO_GRID_GEOMETRY", fields)
    else:
        print("DOJO_GRID_GEOMETRY " + json.dumps(fields, sort_keys=True), flush=True)
    return fields


def current_grid_geometry() -> GridGeometry | None:
    return _ACTIVE_GEOMETRY


def reset_grid_geometry_telemetry_for_tests() -> None:
    global _ACTIVE_GEOMETRY
    _EMITTED_SIGNATURES.clear()
    _ACTIVE_GEOMETRY = None


__all__ = [
    "GridCellSize",
    "GridGeometry",
    "GridMode",
    "InvalidGridGeometryError",
    "current_grid_geometry",
    "emit_grid_geometry",
    "reset_grid_geometry_telemetry_for_tests",
]
