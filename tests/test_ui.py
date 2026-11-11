"""Headless pygame input, preview, rendering and application lifecycle tests."""

from copy import deepcopy
from dataclasses import replace
from unittest.mock import patch

import pygame
import pytest

from engine.cards import load_card_config
from engine.game import BuildSession
from engine.directions import DIRECTIONS, OPPOSITE, neighbor_pos, rotate_doors
from engine.models import Tile, make_empty_board
from engine.resources import Resources
from tests.test_events import category_session
from ui.app import GameApp
from ui.screens import (
    BOARD_RECT, CARD_RECTS, RESTART_RECT, ROTATE_RECT, WINDOW_SIZE, GOLD, MUTED, TEAL,
    card_at_pixel, cell_at_pixel, cell_rect, placement_message,
)


@pytest.fixture
def screen(monkeypatch):
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    yield pygame.display.set_mode(WINDOW_SIZE)
    pygame.quit()


@pytest.fixture
def app(screen):
    return GameApp(BuildSession(seed=42))


def click(app, pos):
    app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))


def key(app, code):
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=code))


def select_legal(app):
    dealt_kinds = {card.kind for card in app.session.draw_result.cards}
    option = next(option for option in app.session.draw_result.legal_placements if option.kind in dealt_kinds)
    index = next(index for index, card in enumerate(app.session.draw_result.cards) if card.kind == option.kind)
    click(app, CARD_RECTS[index].center)
    for _ in range(option.rotation):
        key(app, pygame.K_r)
    return option


@pytest.mark.parametrize("pos", [(0, 0), (0, 6), (6, 0), (6, 6), (3, 4)])
def test_cell_coordinates_round_trip(pos):
    rect = cell_rect(pos)
    assert cell_at_pixel(rect.topleft) == pos
    assert cell_at_pixel(rect.center) == pos
    assert cell_at_pixel((rect.right - 1, rect.bottom - 1)) == pos


@pytest.mark.parametrize("point", [
    (BOARD_RECT.left - 1, BOARD_RECT.top), (BOARD_RECT.right, BOARD_RECT.top),
    (BOARD_RECT.left, BOARD_RECT.top - 1), (BOARD_RECT.left, BOARD_RECT.bottom),
])
def test_pixels_outside_board_are_not_cells(point):
    assert cell_at_pixel(point) is None


def test_card_hit_boxes_are_separate_from_map_and_toolbar():
    for index, rect in enumerate(CARD_RECTS):
        assert card_at_pixel(rect.center) == index
    assert card_at_pixel(BOARD_RECT.center) is None
    assert card_at_pixel(ROTATE_RECT.center) is None


def test_selection_rotation_and_rendering_preserve_hand_and_board(app, screen):
    session = app.session
    before = deepcopy(session.board), session.draw_result, session.rng.getstate()
    click(app, CARD_RECTS[0].center)
    original = session.selected_card
    key(app, pygame.K_r)
    assert session.selected_card == original.rotated()
    key(app, pygame.K_q)
    assert session.selected_card == original
    key(app, pygame.K_2)
    assert session.selected_index == 1
    key(app, pygame.K_1)
    click(app, ROTATE_RECT.center)
    app.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=cell_rect((3, 1)).center))
    app.draw(screen)
    assert (session.board, session.draw_result, session.rng.getstate()) == before


def test_build_click_places_current_card_and_refreshes_hand(app, screen):
    option = select_legal(app)
    card = app.session.selected_card
    click(app, cell_rect(option.pos).center)
    assert app.session.build_turn == 1
    assert app.session.player_pos == option.pos
    assert app.session.board[option.pos[0]][option.pos[1]].doors == card.doors
    assert app.session.selected_card is None
    app.draw(screen)


def test_no_selection_occupied_and_outside_clicks_are_safe(app):
    before = deepcopy(app.session.board), app.session.draw_result, app.session.rng.getstate()
    click(app, cell_rect((3, 1)).center)
    assert "Choose" in app.message
    key(app, pygame.K_1)
    click(app, cell_rect(app.session.player_pos).center)
    assert "already" in app.message
    click(app, (BOARD_RECT.right, BOARD_RECT.bottom))
    assert app.hovered_pos is None
    assert app.session.build_turn == 0
    assert (app.session.board, app.session.draw_result, app.session.rng.getstate()) == before


@pytest.mark.parametrize("action", ["button", "keyboard"])
def test_restart_resets_session_and_preview(app, action):
    initial = deepcopy(app.session.board), app.session.draw_result
    option = select_legal(app)
    click(app, cell_rect(option.pos).center)
    if action == "button":
        click(app, RESTART_RECT.center)
    else:
        key(app, pygame.K_n)
    assert (app.session.board, app.session.draw_result) == initial
    assert app.session.build_turn == 0
    assert app.session.selected_card is None and app.hovered_pos is None


def test_blocked_screen_renders_and_accepts_restart(screen):
    config = load_card_config()
    config = replace(config, room_types=tuple(room for room in config.room_types if room.kind == "dead_end"))
    app = GameApp(BuildSession(seed=0, config=config))
    for _ in range(3):
        option = select_legal(app)
        click(app, cell_rect(option.pos).center)
    assert app.session.blocked
    app.draw(screen)
    key(app, pygame.K_1)
    key(app, pygame.K_r)
    assert app.session.selected_card is None
    click(app, RESTART_RECT.center)
    assert not app.session.blocked
    app.draw(screen)


@pytest.mark.parametrize("reason,word", [
    ("edge_mismatch at direction=0 (new=True, neighbor=False)", "north"),
    ("door_faces_outside_board (direction=3)", "west"),
    ("no_reachable_source", "Connect"), ("cell_occupied", "already"),
])
def test_feedback_explains_placement_reason(reason, word):
    assert word in placement_message(reason)


@pytest.mark.parametrize("event", [pygame.event.Event(pygame.QUIT),
                                 pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)])
def test_quit_events_stop_the_app(app, event):
    app.handle_event(event)
    assert not app.running


def test_event_loop_renders_builds_and_exits(app, screen, monkeypatch):
    kinds = {card.kind for card in app.session.draw_result.cards}
    option = next(option for option in app.session.draw_result.legal_placements if option.kind in kinds)
    index = next(index for index, card in enumerate(app.session.draw_result.cards) if card.kind == option.kind)
    frames = iter([
        [pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=CARD_RECTS[index].center)],
        *[[pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r)] for _ in range(option.rotation)],
        [pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=cell_rect(option.pos).center)],
        [pygame.event.Event(pygame.QUIT)],
    ])
    monkeypatch.setattr(pygame.event, "get", lambda: next(frames, [pygame.event.Event(pygame.QUIT)]))
    app.run(screen)
    assert not app.running
    assert app.session.build_turn == 1 and app.session.player_pos == option.pos


def test_main_seed_argument_and_quit_cleanup(monkeypatch):
    import main

    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    monkeypatch.setattr(pygame.event, "get", lambda: [pygame.event.Event(pygame.QUIT)])
    sessions = []
    real_app = main.GameApp

    def capture_app(session):
        sessions.append(session)
        return real_app(session)

    monkeypatch.setattr(main, "GameApp", capture_app)
    main.main(["--seed", "123"])
    assert sessions[0].seed == 123
    assert not pygame.get_init()


def test_main_cleans_up_after_application_failure(monkeypatch):
    import main

    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")

    def fail(*args):
        raise RuntimeError("simulated application failure")

    monkeypatch.setattr(main.GameApp, "run", fail)
    with pytest.raises(RuntimeError, match="application failure"):
        main.main([])
    assert not pygame.get_init()


def test_success_feedback_remains_visible_under_stationary_pointer(app, screen):
    option = select_legal(app)
    click(app, cell_rect(option.pos).center)
    assert app.message.startswith("Built ")
    with patch.object(app.renderer, "wrapped_text", wraps=app.renderer.wrapped_text) as feedback:
        app.draw(screen)
    assert feedback.call_args.args[1] == app.message


@pytest.mark.parametrize("event_type", [pygame.WINDOWLEAVE, pygame.WINDOWFOCUSLOST])
def test_leaving_window_cancels_hover_without_changing_game(app, event_type):
    select_legal(app)
    app.hovered_pos = (3, 1)
    before = deepcopy(app.session.board), app.session.draw_result, app.session.rng.getstate(), app.session.selected_card
    app.handle_event(pygame.event.Event(event_type))
    assert app.hovered_pos is None
    assert (app.session.board, app.session.draw_result, app.session.rng.getstate(), app.session.selected_card) == before


def test_long_seed_label_stays_clear_of_restart_button(app, screen):
    seed = 10**100
    app.session = BuildSession(seed=seed)
    state = app.session.rng.getstate()
    with patch.object(app.renderer, "text", wraps=app.renderer.text) as texts:
        app.draw(screen)
    seed_call = next(call for call in texts.call_args_list if call.args[1].startswith("Seed "))
    label, pos = seed_call.args[1:3]
    assert label.endswith("...")
    assert pos[0] + app.renderer.font.size(label)[0] <= RESTART_RECT.left - 12
    assert app.session.seed == seed and app.session.rng.getstate() == state


def test_duplicate_build_clicks_commit_only_once(app):
    option = select_legal(app)
    target = cell_rect(option.pos).center
    click(app, target)
    after = deepcopy(app.session.board), app.session.draw_result, app.session.rng.getstate()
    for _ in range(25):
        click(app, target)
    assert app.session.build_turn == 1
    assert (app.session.board, app.session.draw_result, app.session.rng.getstate()) == after


def test_rapid_card_switching_does_not_advance_the_hand(app):
    before = deepcopy(app.session.board), app.session.draw_result, app.session.rng.getstate()
    for index in range(30):
        click(app, CARD_RECTS[index % 3].center)
        key(app, pygame.K_r)
        key(app, pygame.K_q)
    assert app.session.rotations == [0, 0, 0]
    assert app.session.build_turn == 0
    assert (app.session.board, app.session.draw_result, app.session.rng.getstate()) == before


def test_click_rechecks_engine_even_if_a_highlight_is_stale(app, screen, monkeypatch):
    select_legal(app)
    invalid = (0, 6)
    assert not app.session.preview(invalid)[0]
    monkeypatch.setattr(app.session, "legal_cells", lambda: {invalid})
    before = deepcopy(app.session.board), app.session.draw_result, app.session.rng.getstate()
    app.draw(screen)
    click(app, cell_rect(invalid).center)
    assert app.session.build_turn == 0
    assert (app.session.board, app.session.draw_result, app.session.rng.getstate()) == before


def test_quit_ignores_later_actions_in_the_same_event_batch(app, screen, monkeypatch):
    option = select_legal(app)
    before = deepcopy(app.session.board), app.session.draw_result, app.session.rng.getstate()
    events = [pygame.event.Event(pygame.QUIT),
              pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=cell_rect(option.pos).center)]
    monkeypatch.setattr(pygame.event, "get", lambda: events)
    app.run(screen)
    assert not app.running and app.session.build_turn == 0
    assert (app.session.board, app.session.draw_result, app.session.rng.getstate()) == before


def test_movement_into_empty_cells_and_right_click_do_not_change_game(app):
    select_legal(app)
    before = deepcopy(app.session.board), app.session.draw_result, app.session.rng.getstate(), app.session.player_pos
    for code in (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT,
                 pygame.K_w, pygame.K_a, pygame.K_s, pygame.K_d):
        key(app, code)
    app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=3, pos=BOARD_RECT.center))
    assert (app.session.board, app.session.draw_result, app.session.rng.getstate(), app.session.player_pos) == before


@pytest.mark.parametrize("doors", [
    (True, False, False, False), (True, False, True, False),
    (True, True, False, False), (True, True, True, False), (True, True, True, True),
])
@pytest.mark.parametrize("turns", [0, 1, 2, 3])
def test_rendered_door_edges_match_rotated_model(app, screen, doors, turns):
    rect = pygame.Rect(100, 100, 92, 92)
    rotated = rotate_doors(doors, turns)
    app.renderer.room(screen, rect, rotated)
    bounds = rect.inflate(-10, -10)
    points = (bounds.midtop, bounds.midright, bounds.midbottom, bounds.midleft)
    for side, point in enumerate(points):
        assert screen.get_at(point)[:3] == (TEAL if doors[(side - turns) % 4] else MUTED)


def test_player_marker_moves_to_new_room_immediately(app, screen):
    old_pos = app.session.player_pos
    option = select_legal(app)
    click(app, cell_rect(option.pos).center)
    app.draw(screen)
    assert screen.get_at(cell_rect(option.pos).center)[:3] == GOLD
    assert screen.get_at(cell_rect(old_pos).center)[:3] != GOLD


@pytest.mark.parametrize("code,direction", [
    (pygame.K_UP, 0), (pygame.K_w, 0), (pygame.K_RIGHT, 1), (pygame.K_d, 1),
    (pygame.K_DOWN, 2), (pygame.K_s, 2), (pygame.K_LEFT, 3), (pygame.K_a, 3),
])
def test_walking_keys_resolve_entry_and_update_the_player_marker(app, screen, code, direction):
    session = app.session = category_session("supply")
    session.board = make_empty_board()
    session.player_pos = (3, 3)
    session.board[3][3] = Tile("start", tuple(side == direction for side in DIRECTIONS))
    pos = neighbor_pos(3, 3, direction)
    session.board[pos[0]][pos[1]] = Tile("dead_end", tuple(side == OPPOSITE[direction] for side in DIRECTIONS),
                                       event_category="supply")
    before = session.draw_result, session.build_turn, session.rng.getstate()
    key(app, code)
    assert session.player_pos == pos
    assert session.resources.supplies == 3
    assert session.board[pos[0]][pos[1]].event_resolved
    assert (session.draw_result, session.build_turn, session.rng.getstate()) == before
    app.draw(screen)
    assert screen.get_at(cell_rect(pos).center)[:3] == GOLD


def test_clicking_existing_adjacent_room_walks_without_repeated_rewards(app, screen):
    app.session = category_session("supply")
    start = app.session.player_pos
    option = select_legal(app)
    click(app, cell_rect(option.pos).center)
    assert app.session.resources.supplies == 3
    key(app, pygame.K_1)
    key(app, pygame.K_r)
    before = app.session.draw_result, app.session.rotations[:], app.session.selected_index
    for _ in range(3):
        click(app, cell_rect(start).center)
        assert app.session.player_pos == start
        click(app, cell_rect(option.pos).center)
    assert app.session.resources.supplies == 3 and app.session.build_turn == 1
    assert (app.session.draw_result, app.session.rotations, app.session.selected_index) == before
    app.draw(screen)


def test_hud_shows_resources_event_message_and_actual_deltas(app, screen):
    app.session = category_session("danger")
    option = select_legal(app)
    click(app, cell_rect(option.pos).center)
    with patch.object(app.renderer, "text", wraps=app.renderer.text) as texts:
        app.draw(screen)
    labels = [call.args[1] for call in texts.call_args_list]
    assert "HP 5 / 6" in labels and "Supplies 2 / 5" in labels
    assert "You encountered a trap!" in labels and "HP -1" in labels
    assert any(label.startswith("LAST EVENT: Danger at ") for label in labels)
    key(app, pygame.K_n)
    with patch.object(app.renderer, "text", wraps=app.renderer.text) as texts:
        app.draw(screen)
    labels = [call.args[1] for call in texts.call_args_list]
    assert "HP 6 / 6" in labels and "Supplies 2 / 5" in labels
    assert not any(label.startswith("LAST EVENT:") for label in labels)


def test_zero_hp_hud_and_capped_rewards_render_safely(app, screen):
    app.session = category_session("danger", resources=Resources(1, 6, 2, 5))
    option = select_legal(app)
    click(app, cell_rect(option.pos).center)
    with patch.object(app.renderer, "text", wraps=app.renderer.text) as texts:
        app.draw(screen)
    assert "HP 0 / 6" in [call.args[1] for call in texts.call_args_list]
    assert app.running and app.session.hp_depleted
    app.session = category_session("supply", resources=Resources(6, 6, 5, 5))
    option = select_legal(app)
    click(app, cell_rect(option.pos).center)
    with patch.object(app.renderer, "text", wraps=app.renderer.text) as texts:
        app.draw(screen)
    labels = [call.args[1] for call in texts.call_args_list]
    assert "Supplies +1" not in labels
    assert any(label.startswith("No resource change") for label in labels)


def test_rendering_hover_feedback_never_resolves_an_unvisited_event(app, screen):
    session = app.session = category_session("supply")
    session.board[3][1] = Tile("dead_end", (False, False, False, True), event_category="supply")
    before = deepcopy(session.board), session.resources, session.current_event, session.rng.getstate()
    app.hovered_pos = (3, 1)
    for _ in range(3):
        app.draw(screen)
    assert (session.board, session.resources, session.current_event, session.rng.getstate()) == before


def test_new_hud_and_footer_labels_fit_the_existing_window(app, screen):
    app.session = category_session("supply")
    option = select_legal(app)
    click(app, cell_rect(option.pos).center)
    with patch.object(app.renderer, "text", wraps=app.renderer.text) as texts:
        app.draw(screen)
    for call in texts.call_args_list:
        message, pos = call.args[1:3]
        font = call.args[4] if len(call.args) > 4 else call.kwargs.get("font", app.renderer.font)
        assert 0 <= pos[0] and pos[0] + font.size(message)[0] <= WINDOW_SIZE[0]
        assert 0 <= pos[1] and pos[1] + font.get_linesize() <= WINDOW_SIZE[1]
