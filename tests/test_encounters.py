from dataclasses import replace

import pygame
import pytest

from engine.endless import EndlessRun
from engine.models import Tile
from engine.mvp import MvpSession
from ui.app import GameApp
from engine.encounters import BLOCK_START_MS, BLOCK_END_MS, PERFECT_START_MS, PERFECT_END_MS
from ui.screens import BOARD_RECT, block_key_rect, cell_rect, choice_rects, event_close_rect, event_panel_rect
from ui.event_art import mist_texture
from tests.test_mvp import cross_config
from tests.test_mvp_ui import click, key, screen


def at_room(kind, *, guard_has_acted=False, **changes):
    game = MvpSession(159, cross_config("relic"), special_weights=((kind, 1),))
    game.guard_has_acted = guard_has_acted
    game.resources = replace(game.resources, **changes)
    assert game.select_card(0) and game.place((3, 1))[0]
    assert game.board[3][1].kind == "cross"
    assert game.board[3][1].event_icon == kind
    return game


def test_seeded_encounters_and_exclusive_landmarks():
    results = set()
    for seed in range(24):
        run = EndlessRun(MvpSession(seed))
        kinds = [tile.kind for row in run.session.board for tile in row if tile]
        assert [kind for kind in kinds if kind in ("bell", "spring")] == ["spring"]
        assert not {"monster", "fog", "casino"}.intersection(kinds)
        original = run.session.board
        run.session.status = "WON"
        assert run.advance()
        kinds = [tile.kind for row in run.session.board for tile in row if tile]
        landmark, = [kind for kind in kinds if kind in ("bell", "spring")]
        results.add(landmark)
        assert not {"monster", "fog", "casino"}.intersection(kinds)
        run.restart()
        assert run.session.board == original
    assert results == {"bell", "spring"}


def test_original_relic_reward_remains_a_once_only_special_event():
    game = at_room("relic", hp=2, supplies=1)
    assert (game.resources.hp, game.resources.supplies) == (3, 2)
    assert game.move((3, 0))[0] and game.move((3, 1))[0]
    assert (game.resources.hp, game.resources.supplies) == (3, 2)


def test_ring_on_revisit_and_carry_limit_across_floors(screen):
    run = EndlessRun(MvpSession(159))
    game = run.session
    game.board[3][1] = Tile("bell", (False, True, False, True))
    app = GameApp(game)
    key(app, pygame.K_RIGHT)
    key(app, pygame.K_LEFT)
    key(app, pygame.K_RIGHT)
    before = game.resources
    click(app, choice_rects(game.player_pos)[0].center)
    assert game.resources == replace(before, hp_max=before.hp_max + 1)
    assert not game.choose_encounter(0)
    game.status = "WON"
    assert run.advance() and run.session.resources == game.resources


@pytest.mark.parametrize(("option", "hp", "supplies"), [(0, 2, 0), (1, 1, 1)])
def test_casino_welcome_card_once_with_no_entry_cost(screen, option, hp, supplies):
    game = at_room("casino", hp=1, supplies=0)
    app = GameApp(game)
    app.draw(screen)
    if option == 0:
        key(app, pygame.K_j)
    else:
        click(app, choice_rects(game.player_pos)[1].center)
    assert (game.resources.hp, game.resources.supplies) == (hp, supplies)
    assert game.current_event.category == "casino"
    assert not game.choose_encounter(option)
    key(app, pygame.K_LEFT)
    key(app, pygame.K_RIGHT)
    assert game.encounter is None
    assert (game.resources.hp, game.resources.supplies) == (hp, supplies)


@pytest.mark.parametrize("option", [0, 1])
def test_casino_gift_at_capacity_reports_zero_actual_gain(option):
    game = at_room("casino", hp=5, hp_max=5, supplies=5, supplies_max=5)
    assert game.choose_encounter(option)
    assert (game.current_event.hp_delta, game.current_event.supplies_delta) == (0, 0)
    assert game.encounter is None


def test_monster_options_and_refused_payment(screen):
    game = at_room("monster", supplies=1)
    app = GameApp(game)
    key(app, pygame.K_LEFT)
    assert game.player_pos == (3, 1)
    click(app, choice_rects(game.player_pos)[0].center)
    assert game.resources.supplies == 0 and game.resources.hp == game.resources.hp_max
    key(app, pygame.K_LEFT)
    key(app, pygame.K_RIGHT)
    assert game.encounter is None
    game = at_room("monster", supplies=0, hp=1)
    assert not game.choose_encounter(0) and game.encounter == "monster"
    assert game.choose_encounter(1) and game.status == "LOST"


@pytest.mark.parametrize(("delay", "hp", "loot"), [
    (BLOCK_START_MS-1, 1, 0), (BLOCK_START_MS, 2, 0), (PERFECT_START_MS-1, 2, 0),
    (PERFECT_START_MS, 2, 2), (PERFECT_END_MS-1, 2, 2), (PERFECT_END_MS, 2, 0),
    (BLOCK_END_MS-1, 2, 0), (BLOCK_END_MS, 1, 0),
])
def test_monster_block_once_by_keyboard_or_mouse(screen, monkeypatch, delay, hp, loot):
    now = 500
    monkeypatch.setattr(pygame.time, "get_ticks", lambda: now)
    game = at_room("monster", hp=2, supplies=0)
    app = GameApp(game)
    key(app, pygame.K_k)
    app.draw(screen)
    assert game.encounter == "monster" and game.resources.hp == 2
    key(app, pygame.K_k)
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE, repeat=True))
    assert game.encounter == "monster"
    now += delay
    if delay == BLOCK_END_MS:
        app.update_dodge()
    elif delay == PERFECT_START_MS:
        key(app, pygame.K_SPACE)
    else:
        click(app, block_key_rect(game.player_pos).midright - pygame.Vector2(8, 0))
    assert game.encounter is None and game.resources.hp == hp
    app.update_dodge()
    key(app, pygame.K_k)
    assert game.resources.hp == hp and game.resources.supplies == loot
    assert game.current_event.supplies_delta == loot
    assert game.move((3, 0))[0] and game.move((3, 1))[0]
    assert game.encounter is None and game.resources.supplies == loot


def test_perfect_parry_loot_respects_capacity():
    game = at_room("monster", supplies=4, supplies_max=5)
    assert game.choose_encounter(1, block_elapsed_ms=PERFECT_START_MS)
    assert game.current_event.supplies_delta == 1 and game.resources.supplies == 5


def test_board_popup_close_preserves_encounter_and_room_controls(screen):
    game = at_room("casino", hp=2)
    app = GameApp(game)
    app.capture_event_feedback(None)
    app.draw(screen)
    assert app.show_event_panel
    click(app, event_close_rect(game.player_pos).center)
    assert not app.show_event_panel and game.encounter == "casino"
    key(app, pygame.K_j)
    assert app.show_event_panel and game.resources.hp == 3
    key(app, pygame.K_LEFT)
    key(app, pygame.K_RIGHT)
    assert not app.show_event_panel
    for row in range(7):
        for col in range(7):
            rect = event_panel_rect((row, col))
            assert BOARD_RECT.contains(rect) and not rect.colliderect(cell_rect((row, col)))


def test_fog_only_eligible_after_first_guard_action():
    game = MvpSession(159, cross_config("relic"), special_weights=(("fog", 1),))
    game.level = replace(game.level, guard_build_limit=1)
    game.restart()
    assert game.select_card(0) and game.place((3, 1))[0]
    assert game.guard_pos is not None and not game.guard_has_acted
    assert game.board[3][1].event_icon == "relic" and game.fog_turns == 0
    assert game.select_card(0) and game.place((3, 2))[0]
    assert game.guard_has_acted and game.board[3][2].event_icon == "relic"
    assert game.fog_turns == 0
    assert game.select_card(0) and game.place((2, 2))[0]
    assert game.board[2][2].event_icon == "fog" and game.fog_turns == 4
    game.restart()
    assert not game.guard_has_acted and game.fog_turns == 0


def test_fog_visibility_and_four_successful_builds(screen, monkeypatch):
    game = at_room("fog", guard_has_acted=True)
    # Later rooms award the ordinary relic so they cannot start a fresh fog event.
    game.special_weights = ()
    app = GameApp(game)
    assert game.player_pos == (3, 1)
    assert game.visible((3, 3)) and game.visible((2, 2))
    assert not game.visible((3, 4)) and not game.visible((2, 3))
    key(app, pygame.K_1)
    key(app, pygame.K_r)
    click(app, cell_rect((3, 4)).center)
    rect = cell_rect((3, 4))
    atlas = mist_texture()
    for tick in (0, 900):
        monkeypatch.setattr(pygame.time, "get_ticks", lambda: tick)
        app.draw(screen)
        x = (4 * rect.width + tick // 90) % (atlas.get_width() // 2)
        y = (3 * rect.height + tick // 220) % (atlas.get_height() // 2)
        expected = atlas.subsurface((x, y, rect.width, rect.height))
        assert pygame.image.tobytes(screen.subsurface(rect), "RGB") == pygame.image.tobytes(expected, "RGB")
    assert game.fog_turns == 4 and app.pending_plan is None
    for pos in ((3, 0), (3, 1), (3, 0), (3, 1)):
        assert game.move(pos)[0]
        assert game.fog_turns == 4
    assert not game.place(game.player_pos)[0] and game.fog_turns == 4
    for remaining, pos in zip((3, 2, 1, 0), ((3, 2), (2, 2), (2, 3), (1, 3))):
        assert game.select_card(0) and game.place(pos)[0]
        assert game.fog_turns == remaining
        assert game.visible((6, 6)) == (remaining == 0)
