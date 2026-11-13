"""MVP objectives, tools, terminal states and transactional integration."""

from copy import deepcopy
from dataclasses import replace

import pytest

from engine.cards import draw_cards, load_card_config
from engine.level import LevelConfig, SpecialRoom
from engine.models import Tile
from engine.mvp import GameStatus, MvpSession
from engine.placement import reachable_rooms
from engine.resources import Resources
from engine.tools import ToolConfig, ToolRule


def compact_level():
    return LevelConfig(
        SpecialRoom("start", (3, 0), (False, True, False, False)),
        (SpecialRoom("altar_a", (2, 2), (False, False, True, False)),
         SpecialRoom("altar_b", (4, 2), (True, False, False, False))),
        SpecialRoom("core", (3, 3), (False, False, False, True)),
    )


def cross_config(category="neutral"):
    config = load_card_config()
    cross = next(room for room in config.room_types if room.kind == "cross")
    return replace(config, room_types=(replace(cross, event_weights=((category, 1),)),))


def game_snapshot(session):
    return deepcopy((session.board, session.player_pos, session.draw_result,
                     session.build_turn, session.selected_index, session.rotations,
                     session.resources, session.current_event, session.activated_altars,
                     session.status, session.loss_reason, session.objective_message,
                     session.tool_uses)), session.rng.getstate()


@pytest.fixture
def game():
    return MvpSession(seed=42, config=cross_config(), level=compact_level())


def build_bridge(game):
    for pos in ((3, 1), (3, 2)):
        assert game.select_card(0)
        assert game.place(pos) == (True, "ok")


def win_compact(game, order=((2, 2), (4, 2))):
    build_bridge(game)
    for pos in order:
        assert game.move(pos) == (True, "ok")
        assert game.move((3, 2)) == (True, "ok")
    assert game.move((3, 3)) == (True, "ok")


def test_default_game_starts_with_visible_reserved_objectives_and_protected_hand():
    game = MvpSession(seed=159)
    assert game.status == GameStatus.PLAYING and not game.core_unlocked
    assert game.activated_altars == frozenset()
    assert len(game.level.altars) == 2
    assert sum(room is not None for row in game.board for room in row) == 4
    assert len(game.draw_result.cards) == 3 and game.draw_result.legal_card_indices
    assert game.player_pos == game.level.start.pos
    assert game.board[3][6].special_state == "locked"
    assert game.resources == Resources(6, 6, 2, 5)
    assert game.current_event is None and not any(game.tool_uses.values())


@pytest.mark.parametrize("order", [((2, 2), (4, 2)), ((4, 2), (2, 2))])
def test_both_altars_must_be_entered_in_either_order_before_core_entry(game, order):
    build_bridge(game)
    reachable = reachable_rooms(game.board, game.player_pos)
    assert all(altar.pos in reachable for altar in game.level.altars)
    assert game.activated_altars == frozenset()  # Geometric reachability is not activation.
    assert game.move((3, 3)) == (False, "room_locked")
    before_board = deepcopy(game.board)
    assert game.move(order[0]) == (True, "ok")
    assert len(game.activated_altars) == 1 and not game.core_unlocked
    assert game.board[3][3].special_state == "locked"
    for row in range(7):
        for col in range(7):
            if (row, col) != order[0]:
                assert game.board[row][col] == before_board[row][col]
    assert game.move((3, 2))[0]
    assert game.move(order[1])[0]
    assert game.core_unlocked and game.board[3][3].special_state == "unlocked"
    assert game.status == GameStatus.PLAYING
    assert game.move((3, 2))[0]
    assert game.move((3, 3)) == (True, "ok")
    assert game.status == GameStatus.WON


def test_preview_and_inaccessible_movement_cannot_activate_objectives(game):
    game.select_card(0)
    before = game_snapshot(game)
    assert not game.move((2, 2))[0]
    assert not game.place((2, 2))[0]
    assert not game.preview((2, 2))[0]
    assert game_snapshot(game) == before


def test_last_altar_preserves_hand_rotations_and_rng_while_refreshing_metadata(game):
    build_bridge(game)
    game.select_card(1)
    game.rotate_selected()
    cards, rotations, index = game.draw_result.cards, game.rotations[:], game.selected_index
    rng = game.rng.getstate()
    turn = game.build_turn
    for pos in ((2, 2), (3, 2), (4, 2)):
        assert game.move(pos)[0]
    assert game.core_unlocked
    assert (game.draw_result.cards, game.rotations, game.selected_index) == (cards, rotations, index)
    assert game.rng.getstate() == rng and game.build_turn == turn
    assert game.level.core.pos in reachable_rooms(game.board, game.player_pos)


def test_first_altar_milestone_is_bounded_and_never_repeated(game):
    build_bridge(game)
    game.resources = Resources(6, 6, 4, 5)
    assert game.move((2, 2))[0]
    assert game.resources.supplies == 5
    assert game.current_event.supplies_delta == 1
    game.resources = game.resources.apply(supplies_delta=-2)
    for pos in ((3, 2), (2, 2), (3, 2), (4, 2)):
        assert game.move(pos)[0]
    assert game.resources.supplies == 3
    assert len(game.activated_altars) == 2


def test_number_of_altars_is_configurable_and_blocked_does_not_mean_loss():
    east_west = (False, True, False, True)
    level = LevelConfig(
        SpecialRoom("start", (3, 0), (False, True, False, False)),
        tuple(SpecialRoom(f"altar_{i}", (3, i + 1), east_west) for i in range(3)),
        SpecialRoom("core", (3, 4), (False, False, False, True)),
    )
    game = MvpSession(level=level)
    assert game.blocked and game.status == GameStatus.PLAYING
    for col in range(1, 4):
        assert game.move((3, col))[0]
        assert game.core_unlocked == (col == 3)
    assert game.move((3, 4))[0]
    assert game.status == GameStatus.WON and len(game.activated_altars) == 3


def test_hp_depletion_causes_loss_after_exactly_one_room_event():
    game = MvpSession(level=compact_level(), config=cross_config("danger"),
                      resources=Resources(1, 6, 2, 5))
    game.select_card(0)
    assert game.place((3, 1))[0]
    assert game.status == GameStatus.LOST and game.hp_depleted
    assert game.current_event.hp_delta == -1
    assert game.board[3][1].event_resolved
    assert game.build_turn == 1 and game.loss_reason == "HP reached zero."


@pytest.mark.parametrize("terminal", [GameStatus.WON, GameStatus.LOST])
def test_terminal_states_reject_every_gameplay_action_without_changes(game, terminal):
    if terminal == GameStatus.WON:
        win_compact(game)
    else:
        game = MvpSession(level=compact_level(), config=cross_config("danger"),
                          resources=Resources(1, 6, 2, 5))
        game.select_card(0)
        assert game.place((3, 1))[0]
    before = game_snapshot(game)
    assert not game.select_card(0) and not game.rotate_selected()
    assert game.preview((3, 1)) == (False, "game_over")
    assert game.move((3, 2)) == (False, "game_over")
    assert game.place((3, 1)) == (False, "game_over")
    assert game.place_with_seal((3, 1), 0) == (False, "game_over")
    assert game.chisel((3, 0), (2, 0)) == (False, "game_over")
    assert game.legal_cells() == set() and game.legal_cells_with_seal(0) == set()
    assert game_snapshot(game) == before


def test_restart_resets_terminal_state_all_objectives_tools_and_resources(game):
    initial = game_snapshot(game)
    win_compact(game)
    game.restart()
    assert game_snapshot(game) == initial
    win_compact(game)
    assert game.status == GameStatus.WON


def test_zero_initial_hp_starts_lost_and_cannot_be_healed_by_exploration():
    game = MvpSession(resources=Resources(0, 6, 2, 5))
    assert game.status == GameStatus.LOST
    before = game_snapshot(game)
    assert not game.move((2, 0))[0] and not game.place((2, 0))[0]
    assert game_snapshot(game) == before


def test_door_seal_preview_is_read_only_then_charges_once_after_legal_build(game):
    game.select_card(0)
    before = game_snapshot(game)
    assert game.preview_with_seal((3, 1), 0) == (True, "ok")
    assert (3, 1) in game.legal_cells_with_seal(0)
    assert game_snapshot(game) == before
    assert game.place_with_seal((3, 1), 0) == (True, "ok")
    assert game.board[3][1].doors == (False, True, True, True)
    assert game.resources.supplies == 1 and game.tool_uses["door_seal"] == 1
    assert game.board[3][1].event_category == "neutral" and game.board[3][1].event_resolved
    assert game.build_turn == 1 and game.player_pos == (3, 1)


@pytest.mark.parametrize("direction", [3, -1, 4, True])
def test_invalid_seal_preserves_entrance_resources_cards_and_rng(game, direction):
    game.select_card(0)
    before = game_snapshot(game)
    assert not game.place_with_seal((3, 1), direction)[0]
    assert game_snapshot(game) == before


def test_seal_revalidates_every_occupied_neighbor(game):
    game.select_card(0)
    assert game.place((3, 1))[0]
    game.select_card(0)
    before = game_snapshot(game)
    ok, reason = game.place_with_seal((3, 2), 0)
    assert not ok and reason.startswith("edge_mismatch")
    assert game_snapshot(game) == before


def test_tools_require_full_cost_above_configured_supply_floor(game):
    game.resources = Resources(6, 6, 1, 5, supplies_min=1)
    game.select_card(0)
    before = game_snapshot(game)
    assert game.place_with_seal((3, 1), 0) == (False, "insufficient_supplies")
    assert game.chisel((3, 0), (2, 0)) == (False, "insufficient_supplies")
    assert game_snapshot(game) == before


def test_configured_tool_limits_are_enforced(game):
    game.tools = ToolConfig(ToolRule(1, 1), ToolRule(2, 0))
    game.select_card(0)
    assert game.place_with_seal((3, 1), 0)[0]
    game.select_card(0)
    before = game_snapshot(game)
    assert game.place_with_seal((4, 1), 1) == (False, "tool_limit_reached")
    assert game.chisel((3, 0), (2, 0)) == (False, "tool_limit_reached")
    assert game_snapshot(game) == before


def test_chisel_updates_connectivity_without_entering_or_triggering_events(game):
    game.board[2][0] = Tile("dead_end", (True, False, False, False), event_category="supply")
    hand, rotations, rng = game.draw_result.cards, game.rotations[:], game.rng.getstate()
    assert (2, 0) not in reachable_rooms(game.board, game.player_pos)
    assert game.chisel((3, 0), (2, 0)) == (True, "ok")
    assert (2, 0) in reachable_rooms(game.board, game.player_pos)
    assert not game.board[2][0].event_resolved and game.current_event is None
    assert game.player_pos == (3, 0) and game.resources.supplies == 0
    assert game.tool_uses["emergency_chisel"] == 1
    assert (game.draw_result.cards, game.rotations, game.rng.getstate()) == (hand, rotations, rng)
    assert game.move((2, 0))[0] and game.resources.supplies == 1
    assert game.move((3, 0))[0] and game.move((2, 0))[0]
    assert game.resources.supplies == 1


def test_chisel_connects_an_altar_but_only_walking_into_it_activates_it(game):
    game.select_card(0)
    assert game.place((3, 1))[0]
    game.board[2][1] = Tile("dead_end", (False, False, True, False),
                           event_category="neutral", event_resolved=True)
    assert game.move((2, 1))[0]
    assert game.chisel((2, 1), (2, 2)) == (True, "ok")
    assert game.activated_altars == frozenset() and game.resources.supplies == 0
    assert not game.core_unlocked
    assert game.move((2, 2))[0]
    assert game.activated_altars == {"altar_a"} and game.resources.supplies == 1
    assert not game.core_unlocked


def blocked_game(game):
    game.board[3][1] = Tile("dead_end", (False, False, False, True), event_category="neutral", event_resolved=True)
    game.board[2][1] = Tile("dead_end", (True, False, False, False), event_category="supply")
    game.player_pos = (3, 1)
    game.draw_result = draw_cards(game.board, game.player_pos, rng=game.rng, config=game.config)
    game.selected_index = None
    game.rotations = [0] * len(game.draw_result.cards)
    assert game.blocked and game.status == GameStatus.PLAYING
    return game


def test_blocked_construction_can_recover_with_chisel_and_protected_new_hand(game):
    game = blocked_game(game)
    assert game.draw_result.cards == ()
    assert game.chisel((3, 1), (2, 1)) == (True, "ok")
    assert game.status == GameStatus.PLAYING and not game.blocked
    assert len(game.draw_result.cards) == 3 and game.draw_result.legal_card_indices
    assert game.resources.supplies == 0 and not game.board[2][1].event_resolved
    assert game.move((2, 1))[0] and game.resources.supplies == 1


def test_blocked_without_affordable_tools_still_allows_free_walking(game):
    game = blocked_game(game)
    game.resources = game.resources.apply(supplies_delta=-2)
    before = game.resources, game.draw_result.cards, game.build_turn, game.rng.getstate()
    assert game.move((3, 0))[0]
    assert game.status == GameStatus.PLAYING and game.blocked
    assert (game.resources, game.draw_result.cards, game.build_turn, game.rng.getstate()) == before


def test_chisel_cannot_bypass_core_lock_even_if_external_tile_state_is_wrong(game):
    build_bridge(game)
    core_pos = game.level.core.pos
    game.board[core_pos[0]][core_pos[1]].special_state = "unlocked"
    before = game_snapshot(game)
    assert game.move(core_pos) == (False, "room_locked")
    assert game.chisel((3, 2), core_pos) == (False, "room_locked")
    assert game_snapshot(game) == before


@pytest.mark.parametrize("kind", ["normal_build", "sealed_build", "chisel_recovery", "last_altar"])
def test_failures_roll_back_complete_mvp_state_including_objectives_and_tool_costs(game, monkeypatch, kind):
    if kind == "chisel_recovery":
        game = blocked_game(game)
        target = "engine.mvp.draw_cards"
        action = lambda: game.chisel((3, 1), (2, 1))
    elif kind == "last_altar":
        build_bridge(game)
        assert game.move((2, 2))[0] and game.move((3, 2))[0]
        target = "engine.mvp.enumerate_legal_placements"
        action = lambda: game.move((4, 2))
    else:
        game.select_card(0)
        target = "engine.game.draw_cards"
        action = lambda: (game.place((3, 1)) if kind == "normal_build" else game.place_with_seal((3, 1), 0))
    before = game_snapshot(game)

    def fail(*args, **kwargs):
        if "rng" in kwargs:
            kwargs["rng"].random()
        raise RuntimeError("simulated MVP preparation failure")

    monkeypatch.setattr(target, fail)
    with pytest.raises(RuntimeError, match="MVP preparation"):
        action()
    assert game_snapshot(game) == before
