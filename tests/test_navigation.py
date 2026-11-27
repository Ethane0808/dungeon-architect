from engine.cards import Card
from engine.models import Tile, make_empty_board
from engine.navigation import (
    build_entries,
    is_local_build_source,
    route_to_build_site,
    shortest_path,
)
from engine.tools import seal_card


ALL = (True, True, True, True)
HORIZONTAL = (False, True, False, True)


def test_local_preview_only_with_adjacent_matching_door():
    board = make_empty_board()
    board[3][2] = Tile("room", HORIZONTAL)

    assert is_local_build_source(board, (3, 2), (3, 3), HORIZONTAL)
    assert not is_local_build_source(board, (3, 2), (3, 4), HORIZONTAL)
    assert not is_local_build_source(board, (3, 2), (3, 3), (True, True, False, False))


def test_shortest_route_deterministic_tie_break():
    board = make_empty_board()
    for row, col in ((3, 3), (2, 3), (2, 4), (3, 4)):
        board[row][col] = Tile("room", ALL)

    assert shortest_path(board, (3, 3), (2, 4)) == ((3, 3), (2, 3), (2, 4))


def test_equal_distance_entries_choose_lowest_row_then_column():
    board = make_empty_board()
    for row, col in ((3, 1), (2, 1), (2, 2), (2, 3), (4, 1), (4, 2), (4, 3)):
        board[row][col] = Tile("room", ALL)

    route = route_to_build_site(board, (3, 1), (3, 3), (True, False, True, False))

    assert route is not None
    assert route.entry == (2, 3)
    assert route.steps == 3


def test_navigation_never_uses_locked_core_rubble_or_empty_cell():
    board = make_empty_board()
    board[3][1] = Tile("room", ALL)
    board[3][2] = Tile("core", ALL, special_state="locked")
    board[3][3] = Tile("room", ALL)
    board[2][1] = Tile("rubble", ALL)

    assert shortest_path(board, (3, 1), (3, 3)) is None
    assert shortest_path(board, (3, 1), (2, 1)) is None
    assert shortest_path(board, (3, 1), (4, 1)) is None


def test_build_entries_require_door_to_door_and_reachable_room():
    board = make_empty_board()
    board[3][2] = Tile("west", HORIZONTAL)
    board[2][3] = Tile("north", (False, False, True, False))
    board[3][4] = Tile("east-wall", (False, False, False, False))

    assert build_entries(board, (3, 3), ALL, {(3, 2), (2, 3), (3, 4)}) == ((2, 3), (3, 2))
    assert build_entries(board, (-1, 3), ALL, {(2, 3)}) == ()


def test_remote_build_entrance_across_portal_requires_broken_seal():
    board = make_empty_board()
    start, core, entrance, target = ((3, c) for c in range(1, 5))
    for row, col in (start, entrance):
        board[row][col] = Tile("straight", HORIZONTAL)
    board[3][2] = Tile("core", HORIZONTAL, special_state="locked")
    assert route_to_build_site(board, start, target, HORIZONTAL) is None
    board[3][2] = Tile("core", HORIZONTAL, special_state="unlocked")
    assert route_to_build_site(board, start, target, HORIZONTAL).path == (start, core, entrance)


def test_rotated_or_sealed_doors_change_valid_build_entry():
    board = make_empty_board()
    board[3][2] = Tile("west", HORIZONTAL)
    board[2][3] = Tile("north", (False, False, True, False))
    card = Card("corner", (True, False, False, True), "neutral")

    assert build_entries(board, (3, 3), card.doors, {(3, 2), (2, 3)}) == ((2, 3), (3, 2))
    sealed = seal_card(card, 0)
    assert build_entries(board, (3, 3), sealed.doors, {(3, 2), (2, 3)}) == ((3, 2),)
