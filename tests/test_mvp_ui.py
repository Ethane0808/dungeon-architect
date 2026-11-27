"""MVP objective, tool selection and terminal screens through headless inputs."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import patch

import pygame
import pytest

from engine.cards import Card, load_card_config
from engine.demo import DEFAULT_DEMO_PATH
from engine.endless import EndlessRun
from engine.level import LevelConfig, SpecialRoom, load_level_config
from engine.models import Tile
from engine.mvp import GameStatus, MvpSession
from engine.resources import Resources
from tests.test_mvp import cross_config
from ui.app import GameApp, NAV_STEP_MS
from ui.locales import ZH_TW, translate
from ui.screens import (BOARD_RECT, cache_button_rect, cache_prompt_rect, CARD_RECTS, CHISEL_RECT, END_RESTART_RECT, SEAL_RECT,
                        GUIDE_NEXT_RECT, GUIDE_PREV_RECT, GUIDE_PAGES, LANGUAGE_RECT, MEDKIT_RECT,
                        WINDOW_SIZE, GOLD, cell_rect, tool_message)


@pytest.fixture
def screen(monkeypatch):
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    yield pygame.display.set_mode(WINDOW_SIZE)
    pygame.quit()


@pytest.fixture
def app(screen):
    return GameApp(MvpSession(seed=42))


def key(app, code):
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=code))


@pytest.mark.parametrize("use_mouse", [False, True])
def test_barbed_chest_shows_cost_and_accepts_keyboard_or_mouse(screen, use_mouse):
    app = GameApp(MvpSession(seed=0))
    key(app, pygame.K_1)
    click(app, cell_rect((2, 0)).center)
    assert "Pay 1 HP for 2 Supplies, or leave it here." in labels(app, screen)
    key(app, pygame.K_h)
    key(app, pygame.K_e)
    assert app.session.trapped_cache == 2
    key(app, pygame.K_h)
    if use_mouse:
        click(app, cache_button_rect(app.session.player_pos).center)
    else:
        key(app, pygame.K_e)
    assert app.event_feedback == app.session.current_event
    assert {"-1 HP", "+2 Supplies"} <= set(labels(app, screen))
    assert app.session.resources == Resources(4, 5, 4, 5)
    tile = app.session.board[2][0]
    assert tile.event_icon == "supply" and tile.trapped_cache == 0
    with patch.object(app.renderer, "supply_chest", wraps=app.renderer.supply_chest) as chest:
        app.draw(screen)
    assert chest.call_count == 1


def click(app, pos):
    app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))


def remote_plan_app(screen, *, distance=1):
    app = GameApp(MvpSession(seed=42))
    cross = Card("straight", (False, True, False, True), "neutral")
    for col in range(1, distance + 1):
        app.session.draw_result = replace(app.session.draw_result,
                                          status="ready",
                                          cards=(cross, *app.session.draw_result.cards[1:]))
        app.session.rotations[0] = 0
        assert app.session.select_card(0)
        assert app.session.place((3, col))[0]
    for col in range(distance - 1, -1, -1):
        assert app.session.move((3, col))[0]
    app.session.draw_result = replace(app.session.draw_result,
                                      status="ready",
                                      cards=(cross, *app.session.draw_result.cards[1:]))
    app.session.rotations[0] = 0
    app.select(0)
    target = (3, distance + 1)
    return app, target


def test_remote_click_sets_plan_without_building_or_consuming_rng(screen):
    app, target = remote_plan_app(screen)
    before = state(app.session)

    click(app, cell_rect(target).center)

    assert app.pending_plan is not None
    assert app.pending_plan.target == target and app.pending_plan.entry == (3, 1)
    assert app.pending_plan.path == ((3, 0), (3, 1))
    assert state(app.session) == before


def test_build_position_preview_matches_real_guard_follow_step(screen):
    level = replace(load_level_config(), guard_build_limit=1, rubble_count=0, spring_count=0)
    game = MvpSession(42, cross_config(), level=level)
    app = GameApp(game)
    key(app, pygame.K_1)
    click(app, cell_rect((3, 1)).center)
    key(app, pygame.K_1)
    landing = (3, 2)
    app.hovered_pos = landing
    before = state(game)
    with patch.object(app.renderer, "build_position_preview", wraps=app.renderer.build_position_preview) as preview:
        app.draw(screen)
        _, player, guard = preview.call_args.args
        assert (player, guard) == (landing, game.player_pos)
        app.hovered_pos = game.level.core.pos
        app.draw(screen)
        assert preview.call_count == 1
    assert state(game) == before
    click(app, cell_rect(landing).center)
    assert (game.player_pos, game.guard_pos) == (player, guard)


def test_auto_walk_calls_mvp_move_once_per_tick_and_arrival_needs_confirmation(screen):
    app, target = remote_plan_app(screen)
    click(app, cell_rect(target).center)
    hand = app.session.draw_result.cards
    turn = app.session.build_turn
    app.start_or_pause_auto_walk()
    now = app.next_nav_step_ms

    with patch.object(app.session, "move", wraps=app.session.move) as move:
        app.advance_auto_walk(now)
        app.advance_auto_walk(now)
        assert move.call_count == 1

    assert app.session.player_pos == (3, 1)
    assert app.pending_plan is not None and app.pending_plan.steps == 0
    assert app.session.board[target[0]][target[1]] is None
    assert app.session.draw_result.cards == hand and app.session.build_turn == turn
    key(app, pygame.K_RETURN)
    assert app.pending_plan is None and app.session.board[target[0]][target[1]] is not None
    assert app.session.build_turn == turn + 1


def test_clicking_planned_target_at_entrance_confirms_and_clears_plan(screen):
    app, target = remote_plan_app(screen)
    click(app, cell_rect(target).center)
    app.start_or_pause_auto_walk()
    app.advance_auto_walk(app.next_nav_step_ms)
    assert app.pending_plan is not None and app.pending_plan.steps == 0

    click(app, cell_rect(target).center)

    assert app.pending_plan is None
    assert app.session.player_pos == target and app.session.board[target[0]][target[1]] is not None


def test_auto_walk_throttles_steps_and_manual_move_pauses_but_keeps_plan(screen):
    app, target = remote_plan_app(screen, distance=2)
    click(app, cell_rect(target).center)
    app.start_or_pause_auto_walk()
    first = app.next_nav_step_ms
    app.advance_auto_walk(first)
    assert app.session.player_pos == (3, 1) and app.auto_walking
    app.advance_auto_walk(first + NAV_STEP_MS - 1)
    assert app.session.player_pos == (3, 1)
    key(app, pygame.K_RIGHT)
    assert app.session.player_pos == (3, 2)
    assert not app.auto_walking and app.pending_plan is not None
    assert app.pending_plan.steps == 0 and app.nav_pause_reason == "manual"


def test_auto_walk_guard_advances_and_unsafe_next_step_pauses(screen):
    app, target = remote_plan_app(screen, distance=2)
    app.session.board[2][0] = Tile("room", (False, False, True, False), event_resolved=True)
    app.session.guard_pos = (2, 0)
    app.session.guard_next = (3, 0)
    click(app, cell_rect(target).center)
    app.start_or_pause_auto_walk()
    app.advance_auto_walk(app.next_nav_step_ms)
    assert app.session.player_pos == (3, 1)
    assert app.session.guard_pos == (3, 0) and app.session.guard_next == (3, 1)

    # Recompute then make the next route cell explicitly unsafe.
    app.session.guard_next = (3, 2)
    app.advance_auto_walk(app.next_nav_step_ms)
    assert app.session.player_pos == (3, 1)
    assert not app.auto_walking and app.nav_pause_reason == "guard"


def test_navigation_stops_on_first_entry_event_and_preserves_plan(screen):
    app, target = remote_plan_app(screen, distance=2)
    room = app.session.board[3][1]
    app.session.board[3][1] = replace(room, event_category="danger", event_resolved=False,
                                      event_outcome=None, event_icon="")
    app.session.current_event = None
    click(app, cell_rect(target).center)
    app.start_or_pause_auto_walk()

    app.advance_auto_walk(app.next_nav_step_ms)

    assert app.session.player_pos == (3, 1)
    assert app.session.current_event is not None
    assert not app.auto_walking and app.nav_pause_reason == "event"
    assert app.pending_plan is not None


def test_navigation_stops_on_objective_and_terminal_state(screen):
    horizontal = (False, True, False, True)
    altar_level = LevelConfig(
        SpecialRoom("start", (3, 0), (True, True, True, False)),
        (SpecialRoom("altar_a", (3, 1), horizontal),
         SpecialRoom("altar_b", (6, 6), (True, False, False, True))),
        SpecialRoom("core", (0, 6), (False, False, True, True)),
    )
    app = GameApp(MvpSession(seed=42, level=altar_level))
    card = Card("straight", horizontal, "neutral")
    app.session.draw_result = replace(app.session.draw_result, status="ready",
                                      cards=(card, *app.session.draw_result.cards[1:]))
    app.session.rotations = [0] * len(app.session.draw_result.cards)
    app.session.guard_pos = app.session.guard_next = None
    app.select(0)
    click(app, cell_rect((3, 2)).center)
    app.start_or_pause_auto_walk()
    app.advance_auto_walk(app.next_nav_step_ms)
    assert "altar_a" in app.session.activated_altars
    assert app.pending_plan is not None and not app.auto_walking
    assert app.nav_pause_reason == "event"

    core_level = LevelConfig(
        SpecialRoom("start", (3, 0), (True, True, True, False)),
        (SpecialRoom("altar_a", (0, 6), (False, False, True, True)),
         SpecialRoom("altar_b", (6, 6), (True, False, False, True))),
        SpecialRoom("core", (3, 1), horizontal),
    )
    app = GameApp(MvpSession(seed=42, level=core_level))
    app.session.activated_altars = frozenset(room.kind for room in core_level.altars)
    app.session.board[3][1] = replace(app.session.board[3][1], special_state="unlocked")
    app.session.draw_result = replace(app.session.draw_result, status="ready",
                                      cards=(card, *app.session.draw_result.cards[1:]))
    app.session.rotations = [0] * len(app.session.draw_result.cards)
    app.select(0)
    click(app, cell_rect((3, 2)).center)
    app.start_or_pause_auto_walk()
    app.advance_auto_walk(app.next_nav_step_ms)
    assert app.session.status == GameStatus.WON
    assert app.pending_plan is None and not app.auto_walking


def test_selection_rotation_restart_cancel_pending_plan(screen):
    for action in ("selection", "rotation", "restart", "escape"):
        app, target = remote_plan_app(screen)
        click(app, cell_rect(target).center)
        assert app.pending_plan is not None
        if action == "selection":
            key(app, pygame.K_1)
        elif action == "rotation":
            key(app, pygame.K_r)
        elif action == "restart":
            key(app, pygame.K_n)
        else:
            key(app, pygame.K_ESCAPE)
            assert app.running
        assert app.pending_plan is None and not app.auto_walking


def test_hand_rotation_rng_unchanged_after_planning_and_walking(screen):
    app, target = remote_plan_app(screen)
    before = (app.session.draw_result.cards, app.session.rotations[:],
              app.session.rng.getstate(), app.session.build_turn)
    click(app, cell_rect(target).center)
    app.start_or_pause_auto_walk()
    app.advance_auto_walk(app.next_nav_step_ms)
    after = (app.session.draw_result.cards, app.session.rotations[:],
             app.session.rng.getstate(), app.session.build_turn)
    assert after == before


def test_build_plan_panel_and_route_render_without_state_changes(screen):
    app, target = remote_plan_app(screen)
    before = state(app.session)
    click(app, cell_rect(target).center)

    shown = labels(app, screen)

    assert {"Build plan", "Target C4", "Entrance B4", "Steps 1"} <= set(shown)
    assert state(app.session) == before


def test_chest_prompt_returns_on_revisit_and_handles_disabled_opening(screen):
    app = GameApp(MvpSession(seed=0))
    key(app, pygame.K_1)
    chest = (2, 0)
    click(app, cell_rect(chest).center)
    assert app.session.trapped_cache == 2
    with patch.object(app.renderer, "cache_prompt", wraps=app.renderer.cache_prompt) as prompt:
        app.draw(screen)
        assert prompt.call_count == 1
        click(app, cell_rect((3, 0)).center)
        app.draw(screen)
        assert prompt.call_count == 1
        click(app, cell_rect(chest).center)
        app.draw(screen)
        assert prompt.call_count == 2
    app.session.resources = Resources(1, 5, 2, 5)
    before = state(app.session)
    click(app, cache_button_rect(chest).center)
    assert state(app.session) == before
    assert "Need at least 2 HP" in labels(app, screen)
    app.session.resources = Resources(5, 5, 5, 5)
    before = state(app.session)
    key(app, pygame.K_e)
    assert state(app.session) == before
    assert "Supplies full" in labels(app, screen)


@pytest.mark.parametrize("pos", [(0, 0), (0, 6), (6, 0), (6, 6), (3, 3)])
def test_chest_prompt_stays_on_map_without_covering_adjacent_construction(pos):
    panel = cache_prompt_rect(pos)
    assert BOARD_RECT.contains(panel)
    assert not panel.colliderect(cell_rect(pos).inflate(2 * cell_rect(pos).width, 2 * cell_rect(pos).height))
    assert pygame.Rect((0, 0), WINDOW_SIZE).contains(panel)
    assert panel.contains(cache_button_rect(pos))


def test_build_click_beside_unopened_chest_is_not_intercepted(screen):
    app = GameApp(MvpSession(seed=42))
    row, col = app.session.player_pos
    app.session.board[row][col] = replace(app.session.board[row][col], trapped_cache=2)
    key(app, pygame.K_2)
    key(app, pygame.K_q)
    target = (3, 1)
    assert app.session.preview(target)[0]
    app.draw(screen)
    click(app, cell_rect(target).center)
    assert app.session.player_pos == target
    assert app.session.board[target[0]][target[1]] is not None
    assert app.session.board[row][col].trapped_cache == 2


def labels(app, screen):
    with patch.object(app.renderer, "text", wraps=app.renderer.text) as texts:
        app.draw(screen)
    return [call.args[1] for call in texts.call_args_list]


def test_health_warning_tracks_damage_healing_and_well_use(screen):
    app = GameApp(MvpSession(seed=104, resources=Resources(2, 5, 2, 5)))
    assert {"LOW HP", "Medkit [M] heals 1 HP"} <= set(labels(app, screen))
    key(app, pygame.K_1)
    key(app, pygame.K_r)
    click(app, cell_rect((3, 1)).center)
    assert "Medkit [M] or free well C4" in labels(app, screen)
    click(app, cell_rect((3, 2)).center)
    assert app.session.resources.hp == 3
    assert "LOW HP" not in labels(app, screen)
    app.session.resources = app.session.resources.apply(hp_delta=-2)
    assert {"1 HP LEFT", "Medkit [M] heals 1 HP"} <= set(labels(app, screen))
    key(app, pygame.K_h)
    assert "1 HP LEFT" not in labels(app, screen)
    key(app, pygame.K_h)
    app.session.status = GameStatus.LOST
    assert "1 HP LEFT" not in labels(app, screen)


def test_medkit_uses_supplies_without_advancing_the_turn(screen):
    game = MvpSession(resources=Resources(3, 5, 4, 5))
    app = GameApp(game)
    key(app, pygame.K_1)
    hand = game.draw_result, game.selected_index, game.build_turn, game.rng.getstate()
    key(app, pygame.K_m)
    assert (game.resources.hp, game.resources.supplies) == (4, 2)
    assert app.event_feedback.category == "medkit"
    click(app, MEDKIT_RECT.center)
    assert (game.resources.hp, game.resources.supplies) == (5, 0)
    assert {"+1 HP", "-2 Supplies"} <= set(labels(app, screen))
    assert (game.draw_result, game.selected_index, game.build_turn, game.rng.getstate()) == hand


def test_last_exit_warns_before_build_and_offers_restart_afterward(screen):
    app = GameApp(MvpSession(seed=18))
    for number, turns, pos in ((2, 2, (2, 0)), (2, 3, (3, 1)), (1, 0, (4, 0))):
        key(app, pygame.K_1 + number - 1)
        for _ in range(turns):
            key(app, pygame.K_r)
        app.hovered_pos = pos
        before = app.session.rng.getstate()
        assert ("This build will seal the last exit." in labels(app, screen)) == (pos == (4, 0))
        assert app.session.rng.getstate() == before
        click(app, cell_rect(pos).center)
        if pos != (4, 0):
            click(app, cell_rect(app.session.level.start.pos).center)
    assert "All exits are sealed. Press N to restart." in labels(app, screen)
    assert app.session.blocked and app.session.status == GameStatus.PLAYING
    key(app, pygame.K_DOWN)
    assert app.session.player_pos == (4, 0)
    key(app, pygame.K_UP)
    assert app.session.player_pos == (3, 0)
    key(app, pygame.K_n)
    assert not app.session.blocked and app.session.build_turn == 0


@pytest.mark.parametrize("hp,supplies,status,reason", [
    (5, 4, GameStatus.PLAYING, "full_health"),
    (2, 1, GameStatus.PLAYING, "insufficient_supplies"),
    (0, 4, GameStatus.LOST, "game_over"),
    (2, 4, GameStatus.WON, "game_over"),
])
def test_medkit_refusals_preserve_resources_and_event(hp, supplies, status, reason):
    game = MvpSession(resources=Resources(hp, 5, supplies, 5))
    game.status = status
    before = game.resources, game.current_event
    assert game.use_medkit() == (False, reason)
    assert (game.resources, game.current_event) == before


def chain_level():
    return LevelConfig(
        SpecialRoom("start", (3, 0), (False, True, False, False)),
        (SpecialRoom("altar_a", (3, 1), (False, True, False, True)),
         SpecialRoom("altar_b", (3, 2), (False, True, False, True))),
        SpecialRoom("core", (3, 3), (False, False, False, True)),
    )


def test_endless_three_floors_preserve_resources_and_replay_seeds(screen):
    expedition = MvpSession(seed=159, level=chain_level())
    app = GameApp(expedition)
    app.open_lobby()
    key(app, pygame.K_u)
    run = app.endless_run
    replica = EndlessRun(expedition)
    for floor in range(1, 4):
        session = app.session
        assert run.floor == floor and run.completed == floor - 1
        assert session.seed == replica.session.seed
        assert session.board == replica.session.board
        assert not session.activated_altars and not session.core_unlocked
        key(app, pygame.K_RETURN)
        assert app.session is session
        for _ in range(3):
            key(app, pygame.K_RIGHT)
            other = replica.session
            assert other.move((3, other.player_pos[1] + 1))[0]
        assert session.status == GameStatus.WON and run.completed == floor
        assert "Floor cleared" in labels(app, screen)
        resources = session.resources
        key(app, pygame.K_RETURN)
        assert replica.advance()
        assert app.session is not session and app.session.resources == resources
        assert app.session.current_event is None
    key(app, pygame.K_l)
    assert app.session is expedition and expedition.player_pos == expedition.level.start.pos
    key(app, pygame.K_u)
    assert run.floor == 4 and app.session is run.session
    key(app, pygame.K_x)
    assert app.terminal and "Run ended" in labels(app, screen)
    key(app, pygame.K_n)
    assert run.floor == 1 and run.completed == 0 and not app.terminal
    assert app.session.resources == expedition.initial_resources


def test_endless_defeat_cannot_advance():
    run = EndlessRun(MvpSession(seed=159, level=chain_level(), resources=Resources(1, 5, 2, 5)))
    session = run.session
    assert session.guard_pos is not None
    assert session.move(session.guard_pos)[0]
    assert session.status == GameStatus.LOST
    assert not run.advance()
    assert run.floor == 1 and run.completed == 0 and run.session is session


def state(session):
    return deepcopy((session.board, session.player_pos, session.resources, session.draw_result,
                     session.selected_index, session.rotations, session.build_turn, session.tool_uses,
                     session.activated_altars, session.current_event, session.status)), session.rng.getstate()


def test_guide_pages_work_in_hall_and_game_and_block_gameplay_input(app, screen):
    for lobby in (False, True):
        app.in_lobby = lobby
        before = state(app.session)
        key(app, pygame.K_h)
        assert GUIDE_PAGES[0][0] in labels(app, screen)
        click(app, GUIDE_NEXT_RECT.center)
        assert "BARBED CHEST" in labels(app, screen)
        key(app, pygame.K_RIGHT)
        key(app, pygame.K_RIGHT)
        assert "LOOP REWARD" in labels(app, screen)
        click(app, GUIDE_PREV_RECT.center)
        assert app.help_page == 1
        key(app, pygame.K_ESCAPE)
        assert not app.help_open and state(app.session) == before


def test_language_switch_preserves_game_and_translates_an_existing_event(app, screen):
    key(app, pygame.K_1)
    key(app, pygame.K_r)
    click(app, cell_rect((2, 0)).center)
    key(app, pygame.K_2)
    key(app, pygame.K_r)
    previous = state(app.session)
    notice = app.session.current_event
    click(app, LANGUAGE_RECT.center)
    assert app.renderer.t(notice.message) == ZH_TW[notice.message]
    assert pygame.display.get_caption()[0] == "地下城建築師"
    assert app.event_feedback is notice
    app.draw(screen)
    key(app, pygame.K_h)
    key(app, pygame.K_RIGHT)
    key(app, pygame.K_F2)
    assert app.renderer.language == "en" and app.help_page == 1
    assert state(app.session) == previous


def test_bundled_font_and_catalogue_cover_the_guide_and_events(app):
    for title, entries in GUIDE_PAGES:
        for english in [title, *(text for pair in entries for text in pair)]:
            assert translate(english, "zh-TW") != english
    config = app.session.event_config
    events = [event for _, event in config.outcomes]
    events.extend(event for _, variants in config.variants for event in variants)
    assert all(event.message in ZH_TW for event in events)
    font = app.renderer.chinese_fonts[2]
    chars = {c for text in ZH_TW.values() for c in text if ord(c) > 127}
    assert all(font.metrics(c)[0] is not None for c in chars)
    assert all(font.render(c, True, "white").get_bounding_rect().width > 0
               for c in chars if not c.isspace())


def test_connecting_and_visiting_a_well_through_game_controls(screen):
    app = GameApp(MvpSession(seed=104, resources=Resources(4, 5, 2, 5)))
    assert {"Vine spires", "Healing well"} <= set(labels(app, screen))
    key(app, pygame.K_1)
    key(app, pygame.K_r)
    click(app, cell_rect((3, 1)).center)
    assert not app.session.board[3][2].event_resolved
    key(app, pygame.K_F2)
    click(app, cell_rect((3, 2)).center)
    assert app.event_feedback.category == "spring" and app.session.resources.hp == 5
    assert app.renderer.t(app.event_feedback.message) == "你喝下了最後一口井水。"
    app.draw(screen)


def test_guide_example_previews_then_awards_a_loop_alongside_the_room_event(app, screen):
    for index, turns, pos in ((0, 1, (2, 0)), (1, -1, (3, 1)), (0, 2, (2, 1))):
        key(app, pygame.K_1 + index)
        for _ in range(abs(turns)):
            key(app, pygame.K_q if turns < 0 else pygame.K_r)
        app.hovered_pos = pos
        if pos == (2, 1):
            assert any("Closes 1 new loop" in line for line in labels(app, screen))
            assert app.session.loops_closed == 0
        click(app, cell_rect(pos).center)
        if pos == (2, 0):
            click(app, cell_rect(app.session.level.start.pos).center)
    assert app.event_feedback == app.session.current_event
    assert {"-1 Supplies", "1 loop  (+1 supply)"} <= set(labels(app, screen))
    assert app.session.loops_closed == 1


def test_default_mvp_shows_fixed_objectives_tool_costs_and_core_lock(app, screen):
    shown = labels(app, screen)
    assert "A1" in shown and "A2" in shown and "C-" in shown
    assert "A1 G1" in shown and "A2 G7" in shown and "CORE G4" in shown and "LOCKED" in shown
    assert {"Medkit [M]", "Seal [F]", "Chisel [C]", "Uses: 3/3", "Uses: 2/2"} <= set(shown)
    assert app.session.status == GameStatus.PLAYING


def test_paved_exits_reach_the_correct_edges_on_board_and_cards(app):
    for mask in range(16):
        doors = tuple(bool(mask & (1 << side)) for side in range(4))
        for tiles in (app.renderer.room_tiles, app.renderer.card_tiles):
            sprite = tiles[doors]
            w, h = sprite.get_size()
            edges = ((w // 2, 0), (w - 1, h // 2), (w // 2, h - 1), (0, h // 2))
            assert tuple(sprite.get_at(point).a > 200 for point in edges) == doors


@pytest.mark.parametrize("pos, asset", [
    ((0, 6), "altar_a-idle-sw"), ((6, 6), "altar_b-idle-nw"), ((3, 6), "core-locked-nsw"),
])
def test_special_rooms_show_their_initial_art(app, screen, pos, asset):
    app.draw(screen)
    sprite = pygame.image.load(Path(__file__).resolve().parents[1] / "assets" / "rooms" / f"{asset}-72.png")
    area = cell_rect(pos).move(-BOARD_RECT.x, -BOARD_RECT.y)
    sprite = pygame.transform.scale(sprite, area.size)
    if asset.startswith(("altar_", "core-")):
        name, directions = asset.rsplit("-", 1)
        sprite = app.renderer.room_tiles[name, tuple(side in directions for side in "nesw")]
    expected = app.renderer.board_floor.subsurface(area).convert(screen)
    expected.blit(sprite, (0, 0))
    center = pygame.Rect(22, 22, 28, 28)
    actual = screen.subsurface(center.move(cell_rect(pos).topleft))
    assert pygame.image.tobytes(actual, "RGB") == pygame.image.tobytes(expected.subsurface(center), "RGB")


def test_both_altars_share_one_full_tile_design(app):
    for state in ("idle", "activated"):
        altar_a = app.renderer.objects[f"altar_a-{state}"]
        altar_b = app.renderer.objects[f"altar_b-{state}"]
        assert pygame.image.tobytes(altar_a, "RGBA") == pygame.image.tobytes(altar_b, "RGBA")
        mirrored = pygame.transform.flip(altar_a, True, False)
        assert pygame.image.tobytes(altar_a, "RGBA") == pygame.image.tobytes(mirrored, "RGBA")
        assert altar_a.get_bounding_rect().width > 20


def test_locked_core_is_a_full_independent_room_and_differs_from_unlocked_core(app):
    locked = app.renderer.objects["core-locked"]
    unlocked = app.renderer.objects["core-unlocked"]
    assert locked.get_bounding_rect(min_alpha=12).height >= 40
    assert unlocked.get_bounding_rect(min_alpha=12).height >= 40
    assert max(locked.get_at((22, 22))[:3]) < 70
    red, green, blue, _ = unlocked.get_at((22, 22))
    assert green > red and green > blue and green > 200
    assert pygame.image.tobytes(locked, "RGBA") != pygame.image.tobytes(unlocked, "RGBA")


def test_build_preview_warns_before_connecting_to_sealed_portal(screen):
    level = replace(MvpSession().level, rubble_count=0, spring_count=0,
                    core=SpecialRoom("core", (3, 2), (False, True, False, True)))
    game = MvpSession(42, cross_config(), level=level)
    app = GameApp(game)
    key(app, pygame.K_1)
    app.hovered_pos = (3, 1)
    assert game.preview(app.hovered_pos)[0]
    assert any("Portal sealed" in line for line in labels(app, screen))
    assert game.place(app.hovered_pos)[0]
    assert game.move(level.core.pos) == (False, "room_locked")


def test_objective_checklist_updates_on_real_entry_and_shows_victory(screen):
    app = GameApp(MvpSession(seed=0, level=chain_level()))
    assert app.session.blocked  # No construction is needed; walking is still legal.
    key(app, pygame.K_RIGHT)
    shown = labels(app, screen)
    assert "A1 B4" in shown and "ACTIVE" in shown and "A2 C4" in shown and "LOCKED" in shown
    key(app, pygame.K_RIGHT)
    shown = labels(app, screen)
    assert shown.count("ACTIVE") == 2 and "OPEN" in shown
    # Custom doorway layouts retain the same unlocked core artwork.
    core_art = app.renderer.room_tiles["core-unlocked", app.session.level.core.doors]
    actual = screen.get_at(cell_rect(app.session.level.core.pos).center)
    expected = core_art.get_at((38, 38))
    assert all(abs(actual[index] - expected[index]) <= 6 for index in range(3))
    key(app, pygame.K_RIGHT)
    assert app.session.status == GameStatus.WON
    assert "VICTORY" in labels(app, screen)


def test_guard_panel_tracks_build_alarm_and_explains_wake_reason(screen):
    app = GameApp(MvpSession(seed=159))
    shown = labels(app, screen)
    assert {"Guard alert", "0/11", "Each build stirs the guard."} <= set(shown)
    actions = json.loads(DEFAULT_DEMO_PATH.read_text(encoding="utf-8"))["actions"]
    for action in actions[:8]:
        key(app, pygame.K_1 + action["card"] - 1)
        for _ in range(action["turns"]):
            key(app, pygame.K_r)
        click(app, cell_rect(tuple(action["pos"])).center)
    shown = labels(app, screen)
    assert app.session.guard_wake_reason == "altar" and not app.session.activated_altars
    assert {"Guard awake", "An altar echoes.", "Armored steps follow you."} <= set(shown)
    assert any(str(label).startswith("Next step:") for label in shown)


def test_seal_cycles_current_doors_and_rotation_or_selection_cancels(app):
    key(app, pygame.K_1)
    original = app.session.selected_card
    before = app.session.resources, app.session.rng.getstate(), app.session.draw_result
    doors = [side for side, present in enumerate(original.doors) if present]
    for direction in doors:
        key(app, pygame.K_f)
        assert app.seal_direction == direction
        assert app.session.selected_card == original
    key(app, pygame.K_f)
    assert app.seal_direction is None
    click(app, SEAL_RECT.center)
    assert app.seal_direction == doors[0]
    key(app, pygame.K_r)
    assert app.seal_direction is None
    key(app, pygame.K_f)
    key(app, pygame.K_2)
    assert app.seal_direction is None
    assert (app.session.resources, app.session.rng.getstate(), app.session.draw_result) == before


def test_chisel_button_and_key_toggle_without_spending_resources(app):
    before = state(app.session)
    click(app, CHISEL_RECT.center)
    assert app.chisel_mode and "2 Supplies" in app.message
    key(app, pygame.K_c)
    assert not app.chisel_mode
    key(app, pygame.K_f)  # No selected card, so no action or charge.
    assert app.seal_direction is None
    assert state(app.session) == before


def test_invalid_chisel_click_preserves_state_and_explains_target(app, screen):
    key(app, pygame.K_c)
    before = state(app.session)
    click(app, cell_rect((3, 1)).center)
    assert app.chisel_mode
    assert state(app.session) == before
    assert "existing" in app.message
    app.draw(screen)


def test_chisel_click_joins_existing_wall_pair_and_debits_once(app, screen):
    session = app.session
    session.board[3][1] = Tile("corner", (True, False, False, True))
    session.board[3][2] = Tile("dead_end", (True, False, False, False))
    session.player_pos = (3, 1)
    key(app, pygame.K_c)
    click(app, cell_rect((3, 2)).center)
    assert not app.chisel_mode
    assert session.board[3][1].doors[1] and session.board[3][2].doors[3]
    assert session.resources.supplies == 0
    assert session.tool_uses["emergency_chisel"] == 1
    assert session.player_pos == (3, 1)
    app.draw(screen)


def test_sealed_placement_through_click_charges_only_after_success(app, screen):
    session = app.session
    # Seal north on a north/east/west T; the resulting east/west room retains
    # its entry through the west door and is placed by the existing click flow.
    card = Card("t_junction", (True, True, False, True), "neutral")
    session.draw_result = replace(session.draw_result, cards=(card, *session.draw_result.cards[1:]))
    key(app, pygame.K_1)
    key(app, pygame.K_f)
    assert app.seal_direction == 0
    before = state(session)
    click(app, cell_rect(session.player_pos).center)
    assert state(session) == before and app.seal_direction == 0
    click(app, cell_rect((3, 1)).center)
    assert app.seal_direction is None
    assert session.player_pos == (3, 1)
    assert session.board[3][1].doors == (False, True, False, True)
    assert session.resources.supplies == 1
    assert session.tool_uses["door_seal"] == 1
    app.draw(screen)


@pytest.mark.parametrize("status", [GameStatus.WON, GameStatus.LOST])
def test_terminal_screens_block_gameplay_and_allow_restart(app, screen, status):
    app.session.status = status
    if status == GameStatus.LOST:
        app.session.resources = app.session.resources.apply(hp_delta=-100)
    before = state(app.session)
    for code in (pygame.K_1, pygame.K_r, pygame.K_f, pygame.K_c, pygame.K_RIGHT):
        key(app, code)
    for point in (CARD_RECTS[0].center, SEAL_RECT.center, CHISEL_RECT.center, cell_rect((3, 1)).center):
        click(app, point)
    assert state(app.session) == before
    assert ("VICTORY" if status == GameStatus.WON else "DEFEAT") in labels(app, screen)
    click(app, END_RESTART_RECT.center)
    assert app.session.status == GameStatus.PLAYING
    assert not app.terminal and app.seal_direction is None and not app.chisel_mode
    assert app.session.resources == app.session.initial_resources


def test_real_zero_hp_entry_renders_defeat_then_keyboard_restart(screen):
    config = load_card_config()
    config = replace(config, room_types=tuple(replace(room, event_weights=(("danger", 1),))
                                             for room in config.room_types))
    app = GameApp(MvpSession(seed=42, config=config, resources=Resources(1, 6, 2, 5)))
    session = app.session
    option = next(choice for choice in session.draw_result.legal_placements
                  if any(card.kind == choice.kind for card in session.draw_result.cards))
    index = next(index for index, card in enumerate(session.draw_result.cards) if card.kind == option.kind)
    key(app, pygame.K_1 + index)
    for _ in range(option.rotation):
        key(app, pygame.K_r)
    click(app, cell_rect(option.pos).center)
    assert session.status == GameStatus.LOST
    assert "DEFEAT" in labels(app, screen)
    key(app, pygame.K_n)
    assert session.status == GameStatus.PLAYING and session.resources.hp == 1


def test_mvp_text_fits_existing_window_and_rendering_does_not_change_state(app, screen):
    before = state(app.session)
    with patch.object(app.renderer, "text", wraps=app.renderer.text) as texts:
        app.draw(screen)
    for call in texts.call_args_list:
        message, pos = call.args[1:3]
        font = call.args[4] if len(call.args) > 4 else call.kwargs.get("font", app.renderer.font)
        assert pos[0] >= 0 and pos[0] + font.size(message)[0] <= WINDOW_SIZE[0]
        assert pos[1] >= 0 and pos[1] + font.get_linesize() <= WINDOW_SIZE[1]
    assert state(app.session) == before


def test_chinese_tool_usage_label_stays_inside_window(app, screen):
    app.renderer.toggle_language()
    with patch.object(app.renderer, "text", wraps=app.renderer.text) as texts:
        app.draw(screen)
    for rect in (MEDKIT_RECT, SEAL_RECT, CHISEL_RECT):
        call, = [c for c in texts.call_args_list if c.args[2] == (rect.x+42, rect.y+34)]
        label = app.renderer.t(call.args[1])
        assert "剩餘" in label
        assert rect.x+42 + app.renderer.small_font.size(label)[0] <= rect.right


def test_medkit_limit_and_hover_help(app, screen):
    rect = MEDKIT_RECT
    app.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=rect.center))
    assert "Medkit [M]  |  2 supplies" in labels(app, screen)
    game = app.session
    game.resources = Resources(1, 5, 8, 8)
    for _ in range(2):
        click(app, rect.center)
    before = game.resources
    assert game.use_medkit() == (False, "tool_limit_reached") and game.resources == before
    assert "Uses: 0/2" in labels(app, screen)
    game.restart()
    assert game.tool_uses["medkit"] == 0


@pytest.mark.parametrize("reason,fragment", [("tool_limit_reached", "remaining"),
                                           ("insufficient_supplies", "Supplies"),
                                           ("room_locked", "locked"), ("already_connected", "already")])
def test_tool_feedback_explains_rejections(reason, fragment):
    assert fragment in tool_message(reason)


@pytest.mark.parametrize("seed,index,expect_fit", [(3, 0, False), (42, 2, True)])
def test_sealed_card_label_matches_the_displayed_room_legality(app, screen, seed, index, expect_fit):
    app.session = MvpSession(seed=seed)
    assert app.session.draw_result.cards[index].kind == ("cross" if expect_fit else "dead_end")
    assert index in app.session.draw_result.legal_card_indices
    key(app, pygame.K_1 + index)
    key(app, pygame.K_f)
    assert app.seal_direction == 0
    assert bool(app.session.legal_cells_with_seal(app.seal_direction)) == expect_fit
    before = state(app.session)
    with patch.object(app.renderer, "text", wraps=app.renderer.text) as texts:
        app.draw(screen)
    selected_labels = [call.args[1] for call in texts.call_args_list
                       if CARD_RECTS[index].collidepoint(call.args[2])]
    assert ("Seal fits this rotation" if expect_fit else "No fit with this seal") in selected_labels
    assert "Fits in some rotation" not in selected_labels
    assert state(app.session) == before


def test_guard_contact_on_altar_revisit_shows_hit_instead_of_stale_activation(screen):
    app = GameApp(MvpSession(seed=0, level=chain_level()))
    key(app, pygame.K_RIGHT)
    key(app, pygame.K_RIGHT)
    assert "Altar B activated" in app.message
    before_resources = app.session.resources
    before_activated = app.session.activated_altars
    key(app, pygame.K_LEFT)
    assert app.session.player_pos == (3, 1)
    assert app.message == "The guard strikes and retreats."
    assert app.session.resources == before_resources.apply(hp_delta=-1)
    assert app.session.current_event.category == "guard"
    assert app.session.activated_altars == before_activated
