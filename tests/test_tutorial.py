import pygame
from copy import deepcopy
from unittest.mock import patch

from engine.mvp import MvpSession
from engine.tutorial import TutorialSession
from tests.test_mvp_ui import screen, key, click
from ui.app import GameApp
from ui.locales import translate
from ui.screens import TUTORIAL_RECT, TUTORIAL_SKIP_RECT, TUTORIAL_START_RECT, TUTORIAL_REPLAY_RECT, cell_rect


def test_tutorial_controls_complete_and_preserve_expedition(screen):
    original = MvpSession(159)
    app = GameApp(original)
    original_snapshot = (deepcopy(original.board), original.player_pos, original.draw_result,
                         original.resources, original.build_turn, original.rng.getstate())
    app.open_lobby()
    click(app, TUTORIAL_RECT.center)
    game = app.session
    assert isinstance(game, TutorialSession)
    assert not game.place((3, 1))[0]
    key(app, pygame.K_1)
    assert game.lesson == 1
    assert not game.place((3, 2))[0]
    key(app, pygame.K_r)
    assert game.lesson == 1
    click(app, cell_rect((3, 1)).center)
    assert game.lesson == 2 and game.player_pos == (3, 1)
    assert game.current_event.category == "danger" and game.current_event.hp_delta == -1
    hp_after_trap = game.resources.hp
    key(app, pygame.K_LEFT)
    assert game.lesson == 3 and game.player_pos == (3, 0)
    key(app, pygame.K_1)
    key(app, pygame.K_r)
    click(app, cell_rect((3, 2)).center)
    assert game.plan_created and app.pending_plan is not None and game.player_pos == (3, 0)
    key(app, pygame.K_g)
    app.advance_auto_walk(app.next_nav_step_ms)
    assert game.player_pos == (3, 1) and game.lesson == 3
    assert game.resources.hp == hp_after_trap
    assert game.board[3][2] is None
    key(app, pygame.K_RETURN)
    assert game.lesson == 4 and game.player_pos == (3, 2)
    assert game.current_event.category == "supply" and game.current_event.supplies_delta == 1
    assert game.guard_pos is not None and game.guard_wake_reason == "altar"
    for code in (pygame.K_RIGHT, pygame.K_RIGHT, pygame.K_RIGHT):
        key(app, code)
    assert game.status == "WON" and game.lesson == 5
    assert game.guard_pos is not None
    app.draw(screen)
    click(app, TUTORIAL_REPLAY_RECT.center)
    assert isinstance(app.session, TutorialSession) and app.session.lesson == 0
    assert app.expedition_session is original
    key(app, pygame.K_n)
    assert app.session.lesson == 0 and app.session.status == "PLAYING"
    key(app, pygame.K_l)
    assert app.in_lobby and app.session is original
    assert (original.board, original.player_pos, original.draw_result, original.resources,
            original.build_turn, original.rng.getstate()) == original_snapshot
    key(app, pygame.K_t)
    assert isinstance(app.session, TutorialSession)
    click(app, TUTORIAL_SKIP_RECT.center)
    assert app.session is original and not app.in_lobby


def test_tutorial_invalid_actions_and_rotation_recovery(screen):
    app = GameApp(TutorialSession())
    game = app.session
    key(app, pygame.K_2)
    key(app, pygame.K_r)
    assert game.lesson == 0
    key(app, pygame.K_1)
    key(app, pygame.K_r)
    key(app, pygame.K_r)
    assert game.lesson == 1 and not game.preview(game.BUILD)[0]
    key(app, pygame.K_q)
    assert game.preview(game.BUILD)[0]
    click(app, cell_rect(game.BUILD).center)
    assert game.lesson == 2
    key(app, pygame.K_RIGHT)
    assert game.lesson == 2


def test_cancelled_tutorial_plan_can_be_created_again(screen):
    app = GameApp(TutorialSession())
    key(app, pygame.K_1)
    key(app, pygame.K_r)
    click(app, cell_rect(app.session.BUILD).center)
    key(app, pygame.K_LEFT)
    key(app, pygame.K_1)
    key(app, pygame.K_r)
    click(app, cell_rect(app.session.PLAN).center)
    key(app, pygame.K_ESCAPE)
    assert app.pending_plan is None and not app.session.plan_created
    assert "Press G" not in app.session.narration
    click(app, cell_rect(app.session.PLAN).center)
    key(app, pygame.K_g)
    app.advance_auto_walk(app.next_nav_step_ms)
    key(app, pygame.K_RETURN)
    assert app.session.lesson == 4


def test_tutorial_event_odds_guard_hit_and_restart(screen):
    app = GameApp(TutorialSession())
    game = app.session
    assert game.config.room_types[0].event_weights == (("danger", 1),)
    key(app, pygame.K_1)
    key(app, pygame.K_r)
    click(app, cell_rect(game.BUILD).center)
    assert game.config.room_types[0].event_weights == (("supply", 1),)
    key(app, pygame.K_LEFT)
    key(app, pygame.K_1)
    key(app, pygame.K_r)
    click(app, cell_rect(game.PLAN).center)
    key(app, pygame.K_g)
    app.advance_auto_walk(app.next_nav_step_ms)
    key(app, pygame.K_RETURN)
    hp = game.resources.hp
    key(app, pygame.K_LEFT)
    assert game.resources.hp == hp - 1
    assert "guard hit" in game.narration
    for _ in range(20):
        if game.status == "LOST":
            break
        key(app, pygame.K_LEFT if game.player_pos == game.BUILD else pygame.K_RIGHT)
    assert game.status == "LOST"
    with patch.object(app.renderer, "text", wraps=app.renderer.text) as rendered:
        app.draw(screen)
    assert "DEFEAT" in [call.args[1] for call in rendered.call_args_list]
    key(app, pygame.K_n)
    assert game.lesson == 0 and game.guard_pos is None
    assert game.config.room_types[0].event_weights == (("danger", 1),)


def test_tutorial_text_translated_and_completion_buttons_fit(screen):
    app = GameApp(TutorialSession())
    for text in ("Choose a room card.", "Plan anywhere. Build from nearby.",
                 "You're ready to build your dungeon!", "Start Adventure  [Enter]", "Skip Tutorial"):
        assert translate(text, "zh-TW") != text
    app.renderer.language = "zh-TW"
    app.draw(screen)
    assert TUTORIAL_START_RECT.right < screen.get_width()


def test_tutorial_landmarks_use_game_art_with_tutorial_doorways(screen):
    renderer = GameApp(TutorialSession()).renderer
    horizontal = (False, True, False, True)
    core_door = (False, False, False, True)
    for name, source_doors, doors in (
        ("altar_a-idle", (False, False, True, True), horizontal),
        ("altar_a-activated", (False, False, True, True), horizontal),
        ("altar_b-idle", (True, False, False, True), horizontal),
        ("altar_b-activated", (True, False, False, True), horizontal),
        ("core-locked", (True, False, True, True), core_door),
        ("core-unlocked", (True, False, True, True), core_door),
    ):
        actual = renderer.room_tiles[name, doors]
        source = renderer.room_tiles[name, source_doors]
        corridor = renderer.room_tiles[doors]
        assert actual.get_at((38, 38)) == source.get_at((38, 38))
        for edge in ((38, 2), (73, 38), (38, 73), (2, 38)):
            assert actual.get_at(edge) == corridor.get_at(edge)


def test_tutorial_chinese_instructions_and_hints_are_not_truncated(screen):
    app = GameApp(TutorialSession())
    app.renderer.toggle_language()
    for lesson in range(5):
        app.session.lesson = lesson
        with patch.object(app.renderer, "text", wraps=app.renderer.text) as rendered:
            app.renderer.tutorial(screen, app.session)
        lines = [call.args[1] for call in rendered.call_args_list]
        assert not any("..." in line for line in lines)


def test_context_tips_appear_once_and_expire_without_changing_game(screen):
    app = GameApp(MvpSession(159))
    before = (deepcopy(app.session.board), app.session.rng.getstate(), app.session.resources)
    with patch.object(pygame.time, "get_ticks", return_value=1000):
        app.show_tip("guard", "The guard moves whenever you move or build.")
        assert app.context_tip is not None
        app.show_tip("guard", "Different message")
        assert app.context_tip == "The guard moves whenever you move or build."
    with patch.object(pygame.time, "get_ticks", return_value=5001):
        app.draw(screen)
    assert app.context_tip is None
    assert (app.session.board, app.session.rng.getstate(), app.session.resources) == before
    app.restart()
    assert not app.seen_tips


def test_completion_start_adventure_uses_existing_run(screen):
    original = MvpSession(159)
    app = GameApp(original)
    app.start_tutorial()
    app.session.lesson = 5
    app.session.status = "WON"
    click(app, TUTORIAL_START_RECT.center)
    assert app.session is original and not app.in_lobby
