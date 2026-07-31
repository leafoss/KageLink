import pytest

from kage_combat_lab.domain import CELL_SIZE_PX, GridCell, require_canonical_cell_size


def test_grid_is_immutably_64_pixels() -> None:
    assert CELL_SIZE_PX == 64
    assert require_canonical_cell_size(64) == 64


@pytest.mark.parametrize("invalid", [16, 32, 48, 63, 65, 96, 128, 64.5])
def test_any_non_64_cell_size_fails_closed(invalid: float) -> None:
    with pytest.raises(ValueError, match="KAGE_GRID_CELL_SIZE_IMMUTABLE"):
        require_canonical_cell_size(invalid)


def test_diagonal_is_adjacent() -> None:
    assert GridCell(0, 0).is_adjacent_to(GridCell(1, 1))
    assert GridCell(0, 0).chebyshev_distance(GridCell(-1, -1)) == 1
