"""First-entry events, transactional entry, movement and seeded integration."""

from copy import deepcopy
from dataclasses import replace
import json
from random import Random

import pytest

from engine.cards import DEFAULT_CONFIG_PATH, draw_cards, load_card_config
from engine.directions import DIRECTIONS, OPPOSITE, neighbor_pos
from engine.events import EventConfig, EventOutcome, load_event_config, resolve_event
from engine.game import START_POS, BuildSession
from engine.models import Tile, make_empty_board
from engine.resources import Resources
from tests.test_game import choose_legal, snapshot


def category_session(category, *, resources=None, event_config=None):
    config = load_card_config()
    config = replace(config, room_types=tuple(
        replace(room, event_weights=((category, 1),)) for room in config.room_types
    ))
    return BuildSession(seed=42, config=config, resources=resources, event_config=event_config)


def build(session):
    option = choose_legal(session)
    assert session.place(option.pos) == (True, "ok")
    return option.pos


@pytest.mark.parametrize("category,hp,supplies", [("supply", 6, 3), ("danger", 5, 2), ("neutral", 6, 2)])
def test_auto_entry_resolves_exactly_once_and_backtracking_is_free(category, hp, supplies):
    session = category_session(category)
    pos = build(session)
    tile = session.board[pos[0]][pos[1]]
    assert tile.event_resolved and tile.event_category == category
    assert (session.resources.hp, session.resources.supplies) == (hp, supplies)
    assert session.current_event.pos == pos and session.current_event.category == category
    notification = session.current_event
    session.select_card(1)
    session.rotate_selected()
    hand = session.draw_result, session.selected_index, session.rotations[:], session.rng.getstate()
    board = deepcopy(session.board)
    for _ in range(5):
        assert session.move(START_POS) == (True, "ok")
        assert session.move(pos) == (True, "ok")
    assert session.board == board
    assert session.current_event == notification
    assert (session.resources.hp, session.resources.supplies) == (hp, supplies)
    assert session.build_turn == 1
    assert (session.draw_result, session.selected_index, session.rotations, session.rng.getstate()) == hand


def test_preview_and_rotation_hide_outcomes_and_do_not_change_resources():
    session = category_session("danger")
    before = deepcopy(session.board), session.resources, session.current_event, session.rng.getstate()
    choose_legal(session)
    card = session.selected_card
    assert card.event_category == "danger" and not hasattr(card, "event_outcome")
    for _ in range(4):
        session.rotate_selected()
        session.preview((3, 1))
        session.legal_cells()
    assert session.selected_card.event_category == card.event_category
    assert (session.board, session.resources, session.current_event, session.rng.getstate()) == before


@pytest.mark.parametrize("pos", [(-1, 0), (7, 0), (3, -1), (3, 7), START_POS, (3, 1), (0, 6)])
def test_invalid_movement_does_not_resolve_or_change_any_state(pos):
    session = category_session("supply")
    before = snapshot(session)
    assert not session.move(pos)[0]
    assert snapshot(session) == before


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_walking_and_returning_use_matching_doors_in_each_direction(direction):
    session = category_session("supply")
    session.board = make_empty_board()
    session.player_pos = (3, 3)
    doors = tuple(side == direction for side in DIRECTIONS)
    target_doors = tuple(side == OPPOSITE[direction] for side in DIRECTIONS)
    pos = neighbor_pos(3, 3, direction)
    session.board[3][3] = Tile("start", doors)
    session.board[pos[0]][pos[1]] = Tile("dead_end", target_doors, event_category="supply")
    assert session.move(pos) == (True, "ok")
    assert session.resources.supplies == 3
    assert session.move((3, 3)) == (True, "ok")
    assert session.move(pos) == (True, "ok")
    assert session.resources.supplies == 3


@pytest.mark.parametrize("source_door,target_door", [(False, True), (True, False), (False, False)])
def test_walls_prevent_events(source_door, target_door):
    session = category_session("supply")
    session.board[3][0].doors = (False, source_door, False, False)
    session.board[3][1] = Tile("dead_end", (False, False, False, target_door), event_category="supply")
    before = snapshot(session)
    assert session.move((3, 1)) == (False, "doors_not_connected")
    assert snapshot(session) == before


def test_locked_core_blocks_entry_without_events_then_can_be_unlocked():
    session = category_session("supply")
    session.board[3][1] = Tile("core", (False, False, False, True),
                               event_category="supply", special_state="locked")
    before = snapshot(session)
    assert session.move((3, 1)) == (False, "room_locked")
    assert snapshot(session) == before
    session.board[3][1].special_state = "unlocked"
    assert session.move((3, 1)) == (True, "ok")
    assert session.resources == session.initial_resources
    assert session.current_event is None  # Special objectives are outside this phase.


def test_capped_reward_is_consumed_once_and_reports_actual_change():
    session = category_session("supply", resources=Resources(6, 6, 5, 5))
    pos = build(session)
    assert session.board[pos[0]][pos[1]].event_resolved
    assert session.current_event.supplies_delta == 0
    session.resources = session.resources.apply(supplies_delta=-2)
    assert session.move(START_POS)[0] and session.move(pos)[0]
    assert session.resources.supplies == 3


def test_zero_hp_is_safe_exposed_and_does_not_invent_game_over():
    session = category_session("danger", resources=Resources(1, 6, 2, 5))
    pos = build(session)
    assert session.hp_depleted and session.resources.hp == 0
    assert session.current_event.hp_delta == -1
    assert session.move(START_POS)[0] and session.move(pos)[0]
    assert session.hp_depleted and session.build_turn == 1


def test_configured_recovery_and_supply_loss_apply_with_bounds():
    events = EventConfig((("neutral", EventOutcome("A spring restores you.", hp_delta=20, supplies_delta=-10)),))
    session = category_session("neutral", resources=Resources(2, 6, 2, 5), event_config=events)
    build(session)
    assert session.resources == Resources(6, 6, 0, 5)
    assert (session.current_event.hp_delta, session.current_event.supplies_delta) == (4, -2)


@pytest.mark.parametrize("category", ["supply", "danger", "neutral"])
def test_restart_resets_rooms_resources_notifications_and_seed(category):
    session = category_session(category)
    initial = snapshot(session)
    pos = build(session)
    notification = session.current_event
    session.move(START_POS)
    session.restart()
    assert snapshot(session) == initial
    assert build(session) == pos
    assert session.current_event == notification


@pytest.mark.parametrize("failure", ["event", "draw"])
def test_failed_build_keeps_board_resources_event_and_random_state(failure, monkeypatch):
    session = category_session("supply")
    build(session)  # Preserve an existing notification as well as initial resources.
    option = choose_legal(session)
    before = snapshot(session)

    def fail(*args, **kwargs):
        if "rng" in kwargs:
            kwargs["rng"].random()
        raise RuntimeError("simulated entry failure")

    monkeypatch.setattr("engine.game." + ("resolve_event" if failure == "event" else "draw_cards"), fail)
    with pytest.raises(RuntimeError, match="entry failure"):
        session.place(option.pos)
    assert snapshot(session) == before


def test_failed_walk_does_not_partially_enter_or_resolve(monkeypatch):
    session = category_session("supply")
    session.board[3][1] = Tile("dead_end", (False, False, False, True), event_category="supply")
    before = snapshot(session)

    def fail(*args):
        raise RuntimeError("simulated event failure")

    monkeypatch.setattr("engine.game.resolve_event", fail)
    with pytest.raises(RuntimeError, match="event failure"):
        session.move((3, 1))
    assert snapshot(session) == before


def test_walking_remains_available_when_no_normal_room_can_be_placed():
    config = load_card_config()
    config = replace(config, room_types=tuple(room for room in config.room_types if room.kind == "dead_end"))
    session = BuildSession(seed=0, config=config)
    for _ in range(3):
        build(session)
    assert session.blocked
    before = session.resources, session.draw_result, session.build_turn, session.rng.getstate()
    assert session.move(START_POS) == (True, "ok")
    assert (session.resources, session.draw_result, session.build_turn, session.rng.getstate()) == before


def test_fixed_seed_reproduces_events_resources_and_protected_draws():
    left, right = BuildSession(seed=7), BuildSession(seed=7)
    for _ in range(20):
        assert snapshot(left) == snapshot(right)
        if left.blocked:
            break
        assert left.draw_result.legal_card_indices
        option = choose_legal(left)
        card = left.selected_card
        # Compare against the unchanged Phase 2 draw API without resolving events.
        next_board = deepcopy(left.board)
        next_board[option.pos[0]][option.pos[1]] = Tile(card.kind, card.doors, event_category=card.event_category)
        reference = Random()
        reference.setstate(left.rng.getstate())
        expected = draw_cards(next_board, option.pos, rng=reference, config=left.config)
        assert left.place(option.pos) == (True, "ok")
        assert build(right) == option.pos
        assert left.draw_result == expected
        assert left.rng.getstate() == reference.getstate()
    assert snapshot(left) == snapshot(right)


def test_custom_mystery_category_can_use_configured_data_without_changing_defaults():
    data = json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    data["events"]["categories"] = ["mystery"]
    data["events"]["outcomes"] = {"mystery": {"message": "A hidden cache!", "supplies_delta": 2}}
    events = EventConfig.from_mapping(data)
    session = category_session("mystery", event_config=events)
    build(session)
    assert session.current_event.category == "mystery"
    assert session.resources.supplies == 4


def test_event_config_validates_every_category_used_by_cards():
    with pytest.raises(ValueError, match="configured outcome"):
        category_session("unknown")


@pytest.mark.parametrize("change", ["missing", "extra", "float", "bool", "message", "unknown", "duplicate"])
def test_invalid_event_configuration_is_rejected(change):
    data = json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    events = data["events"]
    if change == "missing":
        del events["outcomes"]["danger"]
    elif change == "extra":
        events["outcomes"]["unknown"] = {}
    elif change in {"float", "bool"}:
        events["outcomes"]["danger"]["hp_delta"] = 1.5 if change == "float" else True
    elif change == "message":
        events["outcomes"]["neutral"]["message"] = ""
    elif change == "unknown":
        events["outcomes"]["danger"]["hp_dleta"] = -1
    else:
        events["categories"].append("supply")
    with pytest.raises(ValueError):
        EventConfig.from_mapping(data)


def test_loaded_config_and_pure_resolution_work_without_mutation():
    config = load_event_config()
    initial = Resources(6, 6, 2, 5)
    updated, notice = resolve_event("danger", (2, 0), initial, config)
    assert initial.hp == 6 and updated.hp == 5
    assert notice.message == "You encountered a trap!"
    assert notice.hp_delta == -1 and notice.supplies_delta == 0
