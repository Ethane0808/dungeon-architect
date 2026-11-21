"""MVP objective, tool selection and terminal screens through headless inputs."""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pygame
import pytest

from engine.cards import Card, load_card_config
from engine.level import LevelConfig, SpecialRoom
from engine.models import Tile
from engine.mvp import GameStatus, MvpSession
from engine.resources import Resources
from ui.app import GameApp
from ui.locales import ZH_TW, translate
from ui.screens import (BOARD_RECT, CACHE_RECT, CARD_RECTS, CHISEL_RECT, END_RESTART_RECT, SEAL_RECT,
                        GUIDE_NEXT_RECT, GUIDE_PREV_RECT, GUIDE_PAGES, LANGUAGE_RECT,
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
        click(app, CACHE_RECT.center)
    else:
        key(app, pygame.K_e)
    assert app.event_feedback == app.session.current_event
    assert "HP -1  |  Supplies +2" in labels(app, screen)
    assert app.session.resources == Resources(4, 5, 4, 5)


def click(app, pos):
    app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))


def labels(app, screen):
    with patch.object(app.renderer, "text", wraps=app.renderer.text) as texts:
        app.draw(screen)
    return [call.args[1] for call in texts.call_args_list]


def chain_level():
    return LevelConfig(
        SpecialRoom("start", (3, 0), (False, True, False, False)),
        (SpecialRoom("altar_a", (3, 1), (False, True, False, True)),
         SpecialRoom("altar_b", (3, 2), (False, True, False, True))),
        SpecialRoom("core", (3, 3), (False, False, False, True)),
    )


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
    assert app.event_feedback == app.session.current_event
    assert "Supplies -1  |  1 loop  (+1 supply)" in labels(app, screen)
    assert app.session.loops_closed == 1


def test_default_mvp_shows_fixed_objectives_tool_costs_and_core_lock(app, screen):
    shown = labels(app, screen)
    assert "A1" in shown and "A2" in shown and "C-" in shown
    assert "A1 G1" in shown and "A2 G7" in shown and "CORE G4" in shown and "LOCKED" in shown
    assert any("Seal 1S / 3 left" in line and "Chisel 2S / 2 left" in line for line in shown)
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
    expected = app.renderer.board_floor.subsurface(area).convert(screen)
    expected.blit(sprite, (0, 0))
    center = pygame.Rect(22, 22, 28, 28)
    actual = screen.subsurface(center.move(cell_rect(pos).topleft))
    assert pygame.image.tobytes(actual, "RGB") == pygame.image.tobytes(expected.subsurface(center), "RGB")


def test_both_altars_share_one_full_tile_design():
    room_dir = Path(__file__).resolve().parents[1] / "assets" / "rooms"
    for state in ("idle", "activated"):
        altar_a = pygame.image.load(room_dir / f"altar_a-{state}-sw-72.png")
        altar_b = pygame.image.load(room_dir / f"altar_b-{state}-nw-72.png")
        restored = pygame.transform.rotate(altar_b, 90)
        assert pygame.image.tobytes(altar_a, "RGBA") == pygame.image.tobytes(restored, "RGBA")
        assert altar_a.get_bounding_rect(min_alpha=12) == pygame.Rect(0, 0, 72, 72)


def test_locked_core_is_a_full_independent_room_and_differs_from_unlocked_core():
    room_dir = Path(__file__).resolve().parents[1] / "assets" / "rooms"
    locked = pygame.image.load(room_dir / "core-locked-nsw-72.png")
    unlocked = pygame.image.load(room_dir / "core-unlocked-nsw-72.png")
    assert locked.get_bounding_rect(min_alpha=12).height == 72
    assert unlocked.get_bounding_rect(min_alpha=12).height == 72
    assert pygame.image.tobytes(locked, "RGBA") != pygame.image.tobytes(unlocked, "RGBA")


def test_objective_checklist_updates_on_real_entry_and_shows_victory(screen):
    app = GameApp(MvpSession(seed=0, level=chain_level()))
    assert app.session.blocked  # No construction is needed; walking is still legal.
    key(app, pygame.K_RIGHT)
    shown = labels(app, screen)
    assert "A1 B4" in shown and "ACTIVE" in shown and "A2 C4" in shown and "LOCKED" in shown
    key(app, pygame.K_RIGHT)
    shown = labels(app, screen)
    assert shown.count("ACTIVE") == 2 and "OPEN" in shown
    # This custom horizontal fixture has no matching bespoke objective-room art.
    assert screen.get_at(cell_rect(app.session.level.core.pos).center)[:3] == GOLD
    key(app, pygame.K_RIGHT)
    assert app.session.status == GameStatus.WON
    assert "VICTORY" in labels(app, screen)


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


def test_revisiting_an_altar_shows_movement_instead_of_stale_activation(screen):
    app = GameApp(MvpSession(seed=0, level=chain_level()))
    key(app, pygame.K_RIGHT)
    key(app, pygame.K_RIGHT)
    assert "Altar B activated" in app.message
    before_resources = app.session.resources
    before_event = app.session.current_event
    before_activated = app.session.activated_altars
    key(app, pygame.K_LEFT)
    assert app.session.player_pos == (3, 1)
    assert app.message == "Moved to B4. Backtracking is free."
    assert app.session.resources == before_resources
    assert app.session.current_event == before_event
    assert app.session.activated_altars == before_activated
