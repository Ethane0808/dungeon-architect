"""Construction transactions and persistent previews without a pygame dependency."""

from copy import deepcopy
from dataclasses import replace
import os
from pathlib import Path
from random import Random
import subprocess
import sys

import pytest

from engine.cards import draw_cards, load_card_config
from engine.game import START_POS, BuildSession
from engine.models import Tile, make_empty_board
from engine.placement import reachable_rooms


def snapshot(session):
    return deepcopy((session.board, session.player_pos, session.draw_result,
                     session.build_turn, session.selected_index, session.rotations,
                     session.resources, session.current_event)), session.rng.getstate()


def choose_legal(session):
    dealt_kinds = {card.kind for card in session.draw_result.cards}
    option = next(option for option in session.draw_result.legal_placements if option.kind in dealt_kinds)
    index = next(index for index, card in enumerate(session.draw_result.cards) if card.kind == option.kind)
    session.select_card(index)
    session.rotate_selected(option.rotation - session.rotations[index])
    return option


@pytest.fixture
def session():
    return BuildSession(seed=42)


def test_initial_hand_is_dealt_before_selection(session):
    assert session.selected_card is None
    assert len(session.draw_result.cards) == 3
    assert not session.blocked
    assert session.player_pos == START_POS
    assert session.build_turn == 0
    assert sum(tile is not None for row in session.board for tile in row) == 1


def test_selection_rotation_and_queries_do_not_reroll_or_write_board(session):
    before = deepcopy(session.board), session.draw_result, session.rng.getstate()
    assert session.select_card(0)
    original = session.selected_card
    assert session.rotate_selected()
    rotated = session.selected_card
    assert rotated == original.rotated()
    assert session.select_card(1)
    assert session.select_card(0)
    assert session.selected_card == rotated
    session.legal_cells()
    session.preview((3, 1))
    assert (session.board, session.draw_result, session.rng.getstate()) == before
    assert session.build_turn == 0
    for _ in range(3):
        session.rotate_selected()
    assert session.selected_card == original


@pytest.mark.parametrize("pos", [START_POS, (-1, 0), (7, 0), (0, 6)])
def test_invalid_placement_is_a_noop(session, pos):
    choose_legal(session)
    before = snapshot(session)
    assert not session.place(pos)[0]
    assert snapshot(session) == before


def test_no_selection_and_invalid_selection_are_safe(session):
    before = snapshot(session)
    assert session.preview((3, 1)) == (False, "no_card_selected")
    assert session.place((3, 1)) == (False, "no_card_selected")
    assert session.legal_cells() == set()
    assert not session.rotate_selected()
    assert not session.select_card(-1)
    assert not session.select_card(3)
    assert snapshot(session) == before


def test_build_commits_orientation_category_and_next_hand(session):
    option = choose_legal(session)
    card = session.selected_card
    previous_board = deepcopy(session.board)
    assert option.pos in session.legal_cells()
    assert session.place(option.pos) == (True, "ok")
    tile = session.board[option.pos[0]][option.pos[1]]
    assert (tile.kind, tile.doors, tile.event_category) == (card.kind, card.doors, card.event_category)
    assert tile.event_resolved
    assert session.current_event.category == card.event_category
    assert tile.event_outcome == {"hp": session.current_event.hp_delta,
                                  "supplies": session.current_event.supplies_delta}
    assert session.player_pos == option.pos and session.build_turn == 1
    assert session.selected_card is None
    assert session.rotations == [0] * len(session.draw_result.cards)
    for row in range(7):
        for col in range(7):
            if (row, col) != option.pos:
                assert session.board[row][col] == previous_board[row][col]
    assert session.draw_result.legal_card_indices or session.blocked


def test_commit_revalidates_after_external_board_change(session):
    option = choose_legal(session)
    session.board[option.pos[0]][option.pos[1]] = Tile("room", (False, False, False, False))
    before = snapshot(session)
    assert session.place(option.pos) == (False, "cell_occupied")
    assert snapshot(session) == before


def test_failed_next_draw_rolls_back_board_hand_and_rng(session, monkeypatch):
    option = choose_legal(session)
    before = snapshot(session)

    def failed_draw(*args, rng, **kwargs):
        rng.random()
        raise RuntimeError("simulated next-draw failure")

    monkeypatch.setattr("engine.game.draw_cards", failed_draw)
    with pytest.raises(RuntimeError, match="next-draw"):
        session.place(option.pos)
    assert snapshot(session) == before


def test_blocked_session_can_restart_without_becoming_game_over():
    config = load_card_config()
    config = replace(config, room_types=tuple(room for room in config.room_types if room.kind == "dead_end"))
    session = BuildSession(seed=9, config=config)
    initial = snapshot(session)
    for _ in range(3):
        option = choose_legal(session)
        assert session.place(option.pos)[0]
    assert session.blocked and session.build_turn == 3
    assert session.draw_result.cards == ()
    before = snapshot(session)
    assert session.place((3, 1)) == (False, "no_normal_placement")
    assert not session.select_card(0)
    assert not session.rotate_selected()
    assert snapshot(session) == before
    session.restart()
    assert snapshot(session) == initial


def test_build_sequences_reproduce_with_the_same_seed():
    left, right = BuildSession(seed=123), BuildSession(seed=123)
    for _ in range(12):
        assert snapshot(left) == snapshot(right)
        if left.blocked:
            break
        option = choose_legal(left)
        index = left.selected_index
        right.select_card(index)
        right.rotate_selected(option.rotation)
        assert left.place(option.pos) == right.place(option.pos) == (True, "ok")
    assert snapshot(left) == snapshot(right)


def test_session_can_run_without_pygame():
    script = """
import sys
sys.modules['pygame'] = None
from engine.game import BuildSession
session = BuildSession(seed=42)
assert len(session.draw_result.cards) == 3
"""
    result = subprocess.run([sys.executable, "-B", "-c", script],
                            cwd=Path(__file__).resolve().parents[1], env=os.environ.copy(),
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("hole", [(0, 0), (0, 6), (6, 0), (6, 6), (0, 3), (6, 3), (3, 0), (3, 6), (3, 3)])
def test_last_empty_cell_commits_then_blocks_without_corruption(hole):
    session = BuildSession(seed=4)
    deltas = ((-1, 0), (0, 1), (1, 0), (0, -1))
    board = make_empty_board()
    for row in range(7):
        for col in range(7):
            if (row, col) != hole:
                doors = tuple(0 <= row + dr < 7 and 0 <= col + dc < 7 for dr, dc in deltas)
                board[row][col] = Tile("room", doors)
    # Install a complete test fixture, including a freshly dealt hand.
    session.board = board
    session.player_pos = (3, 1) if hole == START_POS else START_POS
    session.build_turn = 47
    session.draw_result = draw_cards(board, session.player_pos, rng=session.rng, config=session.config)
    session.rotations = [0] * len(session.draw_result.cards)
    assert {option.pos for option in session.draw_result.legal_placements} == {hole}
    option = choose_legal(session)
    assert session.legal_cells() == {hole}
    assert session.place(option.pos) == (True, "ok")
    assert session.blocked and session.build_turn == 48
    assert session.player_pos == hole
    assert len(reachable_rooms(session.board, hole)) == 49
    before = snapshot(session)
    assert not session.place(hole)[0]
    assert snapshot(session) == before


@pytest.mark.parametrize("seed", [0, 1, 7, 42, 123])
def test_seeded_runs_preserve_all_shared_edges_and_terminate(seed):
    session = BuildSession(seed=seed)
    initial = snapshot(session)
    choices = Random(seed + 9000)
    deltas = ((-1, 0), (0, 1), (1, 0), (0, -1))
    for _ in range(49):
        occupied = {(r, c) for r in range(7) for c in range(7) if session.board[r][c] is not None}
        assert len(occupied) == session.build_turn + 1
        assert reachable_rooms(session.board, session.player_pos) == occupied
        for row, col in occupied:
            tile = session.board[row][col]
            for side, (dr, dc) in enumerate(deltas):
                nr, nc = row + dr, col + dc
                if not (0 <= nr < 7 and 0 <= nc < 7):
                    assert not tile.doors[side]
                elif (nr, nc) in occupied:
                    assert tile.doors[side] == session.board[nr][nc].doors[(side + 2) % 4]
        if session.blocked:
            break
        kinds = {card.kind for card in session.draw_result.cards}
        option = choices.choice([option for option in session.draw_result.legal_placements if option.kind in kinds])
        index = next(i for i, card in enumerate(session.draw_result.cards) if card.kind == option.kind)
        session.select_card(index)
        session.rotate_selected(option.rotation)
        assert session.place(option.pos) == (True, "ok")
    assert session.blocked
    session.restart()
    assert snapshot(session) == initial


@pytest.mark.parametrize("state", ["locked", "unlocked"])
def test_auto_entry_and_next_frontier_respect_existing_core_lock(state):
    config = load_card_config()
    config = replace(config, room_types=tuple(room for room in config.room_types if room.kind == "straight"))
    session = BuildSession(seed=42, config=config)
    board = make_empty_board()
    board[3][0] = Tile("start", (False, True, False, False))
    board[3][2] = Tile("core", (False, True, False, True), special_state=state)
    session.board = board
    session.draw_result = draw_cards(board, START_POS, rng=session.rng, config=config)
    session.rotations = [0] * len(session.draw_result.cards)
    option = choose_legal(session)
    assert option.pos == (3, 1)  # Geometry may match a locked room without entering it.
    assert session.place(option.pos) == (True, "ok")
    assert session.player_pos == (3, 1)
    reachable = reachable_rooms(session.board, session.player_pos)
    assert ((3, 2) in reachable) == (state == "unlocked")
    assert session.board[3][2].special_state == state
    assert session.blocked == (state == "locked")
    if state == "unlocked":
        assert {placement.pos for placement in session.draw_result.legal_placements} == {(3, 3)}
