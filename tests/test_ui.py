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
from engine.events import EventNotification
from ui.event_art import event_effect
from tests.test_events import category_session
from ui.app import GameApp, display_viewport
from ui.screens import (
    BOARD_RECT, CARD_RECTS, EVENT_FEEDBACK_MS, HELP_RECT, HP_RECT, RESTART_RECT, ROOM_TRAITS,
    ROTATE_RECT, SUPPLIES_RECT, WINDOW_SIZE, MUTED, TEAL, card_at_pixel, cell_at_pixel,
    cell_rect, placement_message, ENTER_RECT, GUIDE_RECT, GUIDE_CLOSE_RECT,
    persistent_event_marker,
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


def labels(app, screen):
    with patch.object(app.renderer, "text", wraps=app.renderer.text) as texts:
        app.draw(screen)
    return [call.args[1] for call in texts.call_args_list]


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


def test_help_button_and_keyboard_toggle_overlay_without_changing_game(app, screen):
    before = deepcopy((app.session.board, app.session.draw_result, app.session.player_pos))
    click(app, HELP_RECT.center)
    assert app.help_open
    shown = labels(app, screen)
    assert "FIELD GUIDE" in shown and "1  BUILD" in shown and "4  USE TOOLS" in shown
    click(app, CARD_RECTS[0].center)
    assert app.session.selected_index is None
    assert deepcopy((app.session.board, app.session.draw_result, app.session.player_pos)) == before
    key(app, pygame.K_h)
    assert not app.help_open
    key(app, pygame.K_h)
    key(app, pygame.K_ESCAPE)
    assert not app.help_open and app.running


def test_f11_toggles_fullscreen_without_changing_game(app, screen):
    before = deepcopy((app.session.board, app.session.draw_result, app.session.player_pos))
    fullscreen_surface = pygame.Surface((1920, 1080))
    window_surface = pygame.Surface(WINDOW_SIZE)
    app.display_surface = screen
    with patch.object(pygame.display, "set_mode",
                      side_effect=(fullscreen_surface, window_surface)) as set_mode:
        key(app, pygame.K_F11)
        assert app.fullscreen and app.display_surface is fullscreen_surface
        set_mode.assert_called_with((0, 0), pygame.FULLSCREEN)
        key(app, pygame.K_F11)
        assert not app.fullscreen and app.display_surface is window_surface
        assert set_mode.call_args_list[-1].args == (WINDOW_SIZE, 0)
    assert deepcopy((app.session.board, app.session.draw_result, app.session.player_pos)) == before


def test_lobby_scaled_clicks_guide_and_resume(app):
    app.open_lobby()
    app.display_surface = pygame.Surface((1920, 1080))
    view = display_viewport(app.display_surface.get_size())

    def click_control(rect):
        click(app, (view.x + rect.centerx * view.w // WINDOW_SIZE[0],
                    view.y + rect.centery * view.h // WINDOW_SIZE[1]))

    click_control(GUIDE_RECT)
    assert app.help_open
    click_control(ENTER_RECT)
    assert app.in_lobby and app.help_open
    click_control(GUIDE_CLOSE_RECT)
    click_control(ENTER_RECT)
    assert not app.in_lobby
    key(app, pygame.K_1)
    key(app, pygame.K_l)
    key(app, pygame.K_n)
    key(app, pygame.K_2)
    key(app, pygame.K_RETURN)
    assert not app.in_lobby and app.session.selected_index == 0


def test_scaled_display_preserves_aspect_ratio_and_maps_pointer(app):
    app.display_surface = pygame.Surface((1920, 1080))
    viewport = display_viewport(app.display_surface.get_size())
    assert abs(viewport.centerx - 960) <= 1 and abs(viewport.centery - 540) <= 1
    assert viewport.width / viewport.height == pytest.approx(WINDOW_SIZE[0] / WINDOW_SIZE[1], rel=0.001)

    logical = HELP_RECT.center
    display_pos = (viewport.left + logical[0] * viewport.width // WINDOW_SIZE[0],
                   viewport.top + logical[1] * viewport.height // WINDOW_SIZE[1])
    click(app, display_pos)
    assert app.help_open
    click(app, (0, 0))
    assert app.help_open  # Letterbox clicks do nothing.


def test_scaled_draw_fills_only_centered_viewport(app):
    display = pygame.Surface((1920, 1080))
    app.draw(display)
    viewport = display_viewport(display.get_size())
    assert display.get_at((0, 0))[:3] == (4, 8, 14)
    assert display.get_at(viewport.center)[:3] != (4, 8, 14)


def test_card_hit_boxes_are_separate_from_map_and_toolbar():
    for index, rect in enumerate(CARD_RECTS):
        assert card_at_pixel(rect.center) == index
    assert card_at_pixel(BOARD_RECT.center) is None
    assert card_at_pixel(ROTATE_RECT.center) is None


def test_cards_show_room_tendencies_without_revealing_hidden_event(app, screen):
    shown = labels(app, screen)
    for card in app.session.draw_result.cards:
        assert ROOM_TRAITS[card.kind][0] in shown
        assert card.event_category.title() + " preview" not in shown


def test_resource_hud_uses_heart_and_chest_icons(app, screen):
    app.draw(screen)
    for name in ("health", "supply"):
        source = app.renderer.objects[name].get_bounding_rect()
        visible = app.renderer.status_icons[name].get_bounding_rect()
        assert visible.width == 22
        assert abs(visible.height - visible.width * source.height / source.width) <= 1
    chip_fill = (25, 38, 57)
    assert screen.get_at((HP_RECT.left + 15, HP_RECT.centery))[:3] != chip_fill
    assert screen.get_at((SUPPLIES_RECT.left + 15, SUPPLIES_RECT.centery))[:3] != chip_fill


def test_event_feedback_shows_actual_resource_icons_and_expires(app, screen, monkeypatch):
    now = 1_000
    monkeypatch.setattr(pygame.time, "get_ticks", lambda: now)
    app.session = category_session("relic", resources=Resources(4, 6, 2, 5))
    option = select_legal(app)
    click(app, cell_rect(option.pos).center)
    assert app.event_feedback.category == "relic"
    with patch.object(app.renderer, "text", wraps=app.renderer.text) as texts:
        app.draw(screen)
    shown = [call.args[1] for call in texts.call_args_list]
    assert "+1 HP" in shown and "+1 Supplies" in shown

    now += EVENT_FEEDBACK_MS
    app.draw(screen)
    assert app.event_feedback is None


@pytest.mark.parametrize(("category", "cache", "persistent"), [
    ("neutral", 0, False), ("supply", 0, False), ("danger", 0, False), ("danger", 2, True),
])
def test_basic_events_only_open_a_dismissible_panel_for_an_interaction(app, screen, category, cache, persistent):
    notice = EventNotification(app.session.player_pos, category, "Test event", 0, 0, trapped_cache=cache)
    app.session.current_event = notice
    app.capture_event_feedback(None)
    assert app.event_feedback is notice
    assert app.show_event_panel == persistent
    with patch.object(app.renderer, "event_panel", wraps=app.renderer.event_panel) as panel:
        app.draw(screen)
    assert panel.call_count == 1
    assert ("age_ms" in panel.call_args.kwargs) != persistent


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
    modes = []
    real_app = main.GameApp

    def capture_app(session, *, fullscreen=False):
        sessions.append(session)
        modes.append(fullscreen)
        return real_app(session, fullscreen=fullscreen)

    monkeypatch.setattr(main, "GameApp", capture_app)
    main.main(["--seed", "123"])
    assert sessions[0].seed == 123
    assert modes == [False]
    assert not pygame.get_init()


def test_main_can_start_fullscreen(monkeypatch):
    import main

    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    monkeypatch.setattr(pygame.event, "get", lambda: [pygame.event.Event(pygame.QUIT)])
    modes = []
    real_app = main.GameApp

    def capture_app(session, *, fullscreen=False):
        modes.append(fullscreen)
        return real_app(session, fullscreen=fullscreen)

    monkeypatch.setattr(main, "GameApp", capture_app)
    main.main(["--fullscreen"])
    assert modes == [True]
    assert not pygame.get_init()


def test_main_remembers_language_on_next_launch(monkeypatch, tmp_path):
    import main

    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    monkeypatch.setattr(pygame.system, "get_pref_path", lambda *args: str(tmp_path))
    started_in = []

    def visit_hall(app, screen):
        assert app.in_lobby
        started_in.append(app.renderer.language)
        app.draw(screen)
        key(app, pygame.K_F2)

    monkeypatch.setattr(GameApp, "run", visit_hall)
    main.main([])
    main.main([])
    assert started_in == ["en", "zh-TW"]
    assert (tmp_path / "language.txt").read_text(encoding="utf-8") == "en"


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
    assert any(call.args[1] == app.message for call in feedback.call_args_list)


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


def explorer_color(app):
    sprite = app.renderer.objects["explorer"]
    ink = sprite.get_at(sprite.get_rect().center)
    assert ink.a >= 250
    return pytest.approx(ink[:3], abs=255 - ink.a)


def test_player_marker_moves_to_new_room_immediately(app, screen):
    old_pos = app.session.player_pos
    option = select_legal(app)
    click(app, cell_rect(option.pos).center)
    app.draw(screen)
    assert screen.get_at(cell_rect(option.pos).center)[:3] == explorer_color(app)
    assert screen.get_at(cell_rect(old_pos).center)[:3] != explorer_color(app)


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
    assert screen.get_at(cell_rect(pos).center)[:3] == explorer_color(app)


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
    assert "HP" in labels and "4/5" in labels and "SUPPLIES" in labels and "2/5" in labels
    assert "A dart slips through a cracked mural." in labels and "-1 HP" in labels
    assert not any(label.startswith("LAST EVENT:") for label in labels)
    key(app, pygame.K_n)
    with patch.object(app.renderer, "text", wraps=app.renderer.text) as texts:
        app.draw(screen)
    labels = [call.args[1] for call in texts.call_args_list]
    assert "HP" in labels and "5/5" in labels and "SUPPLIES" in labels and "2/5" in labels
    assert not any(label.startswith("LAST EVENT:") for label in labels)


def test_zero_hp_hud_and_capped_rewards_render_safely(app, screen):
    app.session = category_session("danger", resources=Resources(1, 6, 2, 5))
    option = select_legal(app)
    click(app, cell_rect(option.pos).center)
    with patch.object(app.renderer, "text", wraps=app.renderer.text) as texts:
        app.draw(screen)
    labels = [call.args[1] for call in texts.call_args_list]
    assert "HP" in labels and "0/6" in labels
    assert app.running and app.session.hp_depleted
    app.session = category_session("supply", resources=Resources(6, 6, 5, 5))
    option = select_legal(app)
    click(app, cell_rect(option.pos).center)
    with patch.object(app.renderer, "text", wraps=app.renderer.text) as texts:
        app.draw(screen)
    labels = [call.args[1] for call in texts.call_args_list]
    assert "Supplies +1" not in labels
    assert "Supplies full" in labels


@pytest.mark.parametrize("supplies", [2, 5])
def test_supply_chest_opens_once_and_restart_clears_animation(app, screen, monkeypatch, supplies):
    monkeypatch.setattr(pygame.time, "get_ticks", lambda: 1000)
    session = app.session = category_session("supply", resources=Resources(5, 5, supplies, 5))
    start = session.player_pos
    option = select_legal(app)
    click(app, cell_rect(option.pos).center)
    assert session.resources.supplies == min(5, supplies + 1)
    assert session.board[option.pos[0]][option.pos[1]].event_resolved
    before = deepcopy(session.board), session.resources, session.rng.getstate(), session.build_turn
    frames = []
    for elapsed in (0, 275, 600):
        monkeypatch.setattr(pygame.time, "get_ticks", lambda: 1000 + elapsed)
        app.draw(screen)
        rect = cell_rect(option.pos)
        chest_rect = pygame.Rect(rect.centerx + 7, rect.centery - 2, 24, 24)
        frames.append(pygame.image.tobytes(screen.subsurface(chest_rect), "RGB"))
    assert len(set(frames)) == 3
    assert (session.board, session.resources, session.rng.getstate(), session.build_turn) == before
    if supplies == 5:
        assert "Supplies full" in labels(app, screen)
    click(app, cell_rect(start).center)
    click(app, cell_rect(option.pos).center)
    assert app.event_feedback_started_at == 1000
    assert session.resources == before[1]
    key(app, pygame.K_n)
    assert app.event_feedback is None and session.build_turn == 0
    assert session.board[option.pos[0]][option.pos[1]] is None
    # Restart during the next opening also cannot finish awarding the old reward.
    option = select_legal(app)
    click(app, cell_rect(option.pos).center)
    key(app, pygame.K_n)
    app.draw(screen)
    assert session.resources.supplies == supplies and app.event_feedback is None


@pytest.mark.parametrize("category,icon", [
    ("danger", "dart"), ("danger", "falling-stone"), ("danger", "thorn"),
    ("danger", "barbed-cache"), ("supply", "supply"), ("relic", "relic"),
    ("spring", ""), ("medkit", ""), ("altar", ""), ("guard", ""),
    ("bell", ""), ("monster", ""), ("fog", ""), ("casino", ""), ("construction", ""),
])
def test_event_effects_animate_then_expire_without_changing_event(app, category, icon):
    notice = EventNotification((3, 3), category, "Event", 0, 0, icon=icon)
    before = deepcopy(notice)
    frames = []
    canvas = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)
    for age in (100, 500, 1100):
        canvas.fill((0, 0, 0, 0))
        event_effect(canvas, cell_rect(notice.pos), notice, age, app.renderer.room_events)
        frames.append(pygame.image.tobytes(canvas, "RGBA"))
    assert frames[0] != frames[1]
    first = pygame.image.frombytes(frames[0], WINDOW_SIZE, "RGBA")
    assert first.get_bounding_rect().width >= 90
    assert canvas.get_bounding_rect().size == (0, 0)
    assert notice == before


def test_quiet_event_has_text_feedback_but_no_map_effect(app):
    notice = EventNotification((3, 3), "neutral", "Dust settles.", 0, 0, icon="neutral")
    canvas = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)

    event_effect(canvas, cell_rect(notice.pos), notice, 100, app.renderer.room_events)

    assert canvas.get_bounding_rect().size == (0, 0)


@pytest.mark.parametrize("tile,expected", [
    (Tile("room", (True,) * 4, event_category="danger", event_resolved=True, event_icon="dart"), None),
    (Tile("room", (True,) * 4, event_category="danger", event_resolved=True, event_icon="falling-stone"), None),
    (Tile("room", (True,) * 4, event_category="danger", event_resolved=True, event_icon="thorn"), None),
    (Tile("room", (True,) * 4, event_category="danger", event_resolved=True,
          event_icon="barbed-cache", trapped_cache=2), "barbed-cache"),
    (Tile("room", (True,) * 4, event_category="neutral", event_resolved=True), None),
    (Tile("room", (True,) * 4, event_category="relic", event_resolved=True, event_icon="relic"), "relic"),
])
def test_only_live_or_lasting_event_objects_keep_map_markers(tile, expected):
    assert persistent_event_marker(tile) == expected


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
