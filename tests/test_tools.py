"""Pure recovery tools preserve geometry and leave failed operations unchanged."""

from copy import deepcopy
from dataclasses import FrozenInstanceError
import json

import pytest

from engine.cards import Card, DEFAULT_CONFIG_PATH
from engine.directions import DIRECTIONS, OPPOSITE, neighbor_pos
from engine.models import Tile, make_empty_board
from engine.placement import can_place, frontier_cells, reachable_rooms
from engine.tools import ToolConfig, ToolRule, chisel_board, chisel_preview, load_tool_config, seal_card


def test_tool_defaults_reuse_existing_provisional_costs_and_limits():
    assert load_tool_config() == ToolConfig(ToolRule(1, 3), ToolRule(2, 2))
    with pytest.raises(FrozenInstanceError):
        load_tool_config().door_seal.cost_supplies = 0


@pytest.mark.parametrize("cost,limit", [
    (0, 1), (-1, 1), (True, 1), (1.5, 1), ("1", 1),
    (1, -1), (1, True), (1, 1.5), (1, "1"),
])
def test_invalid_cost_or_usage_limit_is_rejected(cost, limit):
    with pytest.raises(ValueError):
        ToolRule(cost, limit)


def test_zero_usage_limit_can_disable_a_tool_without_making_it_free():
    assert ToolRule(2, 0).max_uses_per_game == 0


@pytest.mark.parametrize("data", [{}, {"items": {}}, {"items": None}])
def test_missing_tool_configuration_is_rejected(data):
    with pytest.raises(ValueError, match="tool configuration"):
        ToolConfig.from_mapping(data)


def test_tool_config_snapshots_external_data():
    data = json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    config = ToolConfig.from_mapping(data)
    data["items"]["door_seal"]["cost_supplies"] = 99
    assert config.door_seal.cost_supplies == 1


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_seal_closes_only_selected_door_and_keeps_event_preview(direction):
    original = Card("cross", (True, True, True, True), "danger")
    result = seal_card(original, direction)
    assert result.kind == original.kind and result.event_category == original.event_category
    assert result.doors == tuple(side != direction for side in DIRECTIONS)
    assert original.doors == (True, True, True, True)


@pytest.mark.parametrize("direction", [-1, 4, True, None, "0", 1.5])
def test_invalid_seal_direction_is_rejected(direction):
    card = Card("straight", (True, False, True, False), "neutral")
    with pytest.raises(ValueError, match="invalid_direction"):
        seal_card(card, direction)


def test_cannot_seal_a_wall_or_the_only_entrance():
    card = Card("dead_end", (True, False, False, False), "supply")
    with pytest.raises(ValueError, match="not_a_door"):
        seal_card(card, 1)
    with pytest.raises(ValueError, match="no_entrance"):
        seal_card(card, 0)


def test_sealed_shape_still_requires_a_reachable_entrance_and_matching_edges():
    board = make_empty_board()
    board[3][2] = Tile("start", (False, True, False, False))
    board[2][3] = Tile("dead_end", (False, False, False, False))
    card = Card("t_junction", (True, True, False, True), "supply")
    reachable = {(3, 2)}
    assert not can_place(Tile(card.kind, card.doors), (3, 3), board, reachable)[0]
    sealed = seal_card(card, 0)
    assert can_place(Tile(sealed.kind, sealed.doors), (3, 3), board, reachable) == (True, "ok")
    sealed_entrance = seal_card(card, 3)
    assert can_place(Tile(sealed_entrance.kind, sealed_entrance.doors), (3, 3), board, reachable) == (
        False, "no_reachable_source"
    )


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_chisel_opens_both_shared_walls_and_updates_reachable_frontier(direction):
    board = make_empty_board()
    source = (3, 3)
    target = neighbor_pos(*source, direction)
    board[source[0]][source[1]] = Tile("start", (False, False, False, False))
    target_doors = tuple(side == direction for side in DIRECTIONS)
    board[target[0]][target[1]] = Tile("corner", target_doors, event_category="supply",
                                     event_outcome={"hp": 0, "supplies": 1}, event_resolved=True)
    before = deepcopy(board)
    reachable = reachable_rooms(board, source)
    assert reachable == {source}
    assert chisel_preview(board, source, target, reachable) == (True, "ok")
    prepared = chisel_board(board, source, target, reachable)
    assert board == before
    assert prepared[source[0]][source[1]].doors[direction]
    assert prepared[target[0]][target[1]].doors[OPPOSITE[direction]]
    assert reachable_rooms(prepared, source) == {source, target}
    assert frontier_cells(prepared, reachable_rooms(prepared, source)) == {neighbor_pos(*target, direction)}
    original_target = before[target[0]][target[1]]
    updated_target = prepared[target[0]][target[1]]
    assert (updated_target.event_category, updated_target.event_outcome, updated_target.event_resolved) == (
        original_target.event_category, original_target.event_outcome, original_target.event_resolved
    )
    assert prepared[source[0]] is not board[source[0]]
    assert prepared[target[0]] is not board[target[0]]


@pytest.mark.parametrize("source,target,reason", [
    ((3, 3), (3, 3), "not_adjacent"),
    ((3, 3), (4, 4), "not_adjacent"),
    ((3, 3), (3, 5), "not_adjacent"),
    ((0, 0), (-1, 0), "out_of_bounds"),
    ((6, 6), (6, 7), "out_of_bounds"),
    ((-1, 3), (0, 3), "out_of_bounds"),
    ((3, 3), (3, 4), "no_room"),
    ((True, 3), (1, 4), "invalid_position"),
])
def test_invalid_chisel_targets_are_safe(source, target, reason):
    board = make_empty_board()
    board[3][3] = Tile("start", (False, False, False, False))
    before = deepcopy(board)
    assert chisel_preview(board, source, target, {source}) == (False, reason)
    with pytest.raises(ValueError, match=reason):
        chisel_board(board, source, target, {source})
    assert board == before


@pytest.mark.parametrize("doors,reason", [
    ((True, True), "already_connected"),
    ((True, False), "edge_mismatch"),
    ((False, True), "edge_mismatch"),
])
def test_chisel_cannot_reopen_doors_or_repair_an_invalid_half_door(doors, reason):
    board = make_empty_board()
    board[3][3] = Tile("start", (False, doors[0], False, False))
    board[3][4] = Tile("straight", (False, False, False, doors[1]))
    assert chisel_preview(board, (3, 3), (3, 4), {(3, 3)}) == (False, reason)


def test_chisel_cannot_start_from_an_unreachable_room():
    board = make_empty_board()
    board[3][3] = Tile("dead_end", (True, False, False, False))
    board[3][4] = Tile("dead_end", (True, False, False, False))
    assert chisel_preview(board, (3, 3), (3, 4), {(0, 0)}) == (False, "source_unreachable")


@pytest.mark.parametrize("locked_source", [False, True])
def test_chisel_never_bypasses_a_locked_core_or_enters_from_it(locked_source):
    board = make_empty_board()
    board[3][3] = Tile("start", (True, False, False, False))
    board[3][4] = Tile("core", (False, False, True, False), special_state="locked")
    source, target = ((3, 4), (3, 3)) if locked_source else ((3, 3), (3, 4))
    before = deepcopy(board)
    assert chisel_preview(board, source, target, {source}) == (False, "room_locked")
    with pytest.raises(ValueError, match="room_locked"):
        chisel_board(board, source, target, {source})
    assert board == before


@pytest.mark.parametrize("kind,state", [("altar_a", None), ("altar_b", "activated"), ("core", "unlocked")])
def test_chisel_connects_unlocked_special_rooms_without_activating_them(kind, state):
    board = make_empty_board()
    board[3][3] = Tile("start", (True, False, False, False))
    board[3][4] = Tile(kind, (False, False, True, False), special_state=state)
    prepared = chisel_board(board, (3, 3), (3, 4), {(3, 3)})
    assert prepared[3][4].special_state == state
    assert prepared[3][4].kind == kind


def test_chisel_changes_only_one_edge_pair_and_keeps_unrelated_tiles():
    board = make_empty_board()
    board[3][3] = Tile("start", (True, False, False, False))
    board[3][4] = Tile("corner", (True, False, False, False), event_category="danger")
    board[2][3] = Tile("straight", (True, False, True, False))
    board[2][4] = Tile("straight", (True, False, True, False))
    before = deepcopy(board)
    prepared = chisel_board(board, (3, 3), (3, 4), reachable_rooms(board, (3, 3)))
    assert board == before
    for row in range(7):
        for col in range(7):
            if (row, col) not in {(3, 3), (3, 4)}:
                assert prepared[row][col] == before[row][col]
            tile = prepared[row][col]
            if tile is None:
                continue
            for side in DIRECTIONS:
                nr, nc = neighbor_pos(row, col, side)
                if 0 <= nr < 7 and 0 <= nc < 7 and prepared[nr][nc] is not None:
                    assert tile.doors[side] == prepared[nr][nc].doors[OPPOSITE[side]]


def test_chisel_queries_reject_malformed_board():
    with pytest.raises(ValueError, match="7x7"):
        chisel_preview([], (0, 0), (0, 1), {(0, 0)})
