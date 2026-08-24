from __future__ import annotations

from pc_agent.game_numpad_diagonal import translate_shinobi_directions


def test_cardinal_directions_remain_arrow_keys() -> None:
    assert translate_shinobi_directions({"up"}) == frozenset({"up"})
    assert translate_shinobi_directions({"down"}) == frozenset({"down"})
    assert translate_shinobi_directions({"left"}) == frozenset({"left"})
    assert translate_shinobi_directions({"right"}) == frozenset({"right"})


def test_shinobi_diagonals_use_native_numpad_keys() -> None:
    assert translate_shinobi_directions({"down", "left"}) == frozenset({"numpad1"})
    assert translate_shinobi_directions({"down", "right"}) == frozenset({"numpad3"})
    assert translate_shinobi_directions({"up", "left"}) == frozenset({"numpad7"})
    assert translate_shinobi_directions({"up", "right"}) == frozenset({"numpad9"})


def test_actions_are_preserved_while_diagonal_is_translated() -> None:
    assert translate_shinobi_directions({"up", "right", "h"}) == frozenset({"numpad9", "h"})


def test_opposing_direction_input_is_not_invented_into_a_diagonal() -> None:
    assert translate_shinobi_directions({"up", "down"}) == frozenset({"up", "down"})
    assert translate_shinobi_directions({"left", "right"}) == frozenset({"left", "right"})
