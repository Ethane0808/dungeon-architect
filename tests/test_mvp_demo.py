"""Recorded public-API win, deterministic replay and input-driven UI completion."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pygame

from engine.demo import DEFAULT_DEMO_PATH, replay_demo
from engine.mvp import GameStatus, MvpSession
from tests.test_mvp import game_snapshot
from ui.app import GameApp
from ui.screens import WINDOW_SIZE, cell_rect


def test_recorded_default_seed_completes_every_objective_and_preserves_strict_edges():
    session, steps = replay_demo()
    assert session.seed == 159 and session.status == GameStatus.WON
    assert session.build_turn == 11 and len(steps) == 18
    assert session.activated_altars == {altar.kind for altar in session.level.altars}
    assert session.core_unlocked and session.player_pos == session.level.core.pos
    assert session.resources.hp == 5 and session.resources.supplies == 5
    assert session.tool_uses == {"door_seal": 0, "emergency_chisel": 0}
    for row in range(7):
        for col in range(7):
            tile = session.board[row][col]
            if tile is None:
                continue
            for side, (dr, dc) in enumerate(((-1, 0), (0, 1), (1, 0), (0, -1))):
                r, c = row + dr, col + dc
                if not (0 <= r < 7 and 0 <= c < 7):
                    assert not tile.doors[side]
                elif session.board[r][c] is not None:
                    assert tile.doors[side] == session.board[r][c].doors[(side + 2) % 4]


def test_recorded_win_and_restart_are_deterministic():
    left, left_steps = replay_demo()
    right, right_steps = replay_demo()
    assert game_snapshot(left) == game_snapshot(right)
    assert left_steps == right_steps
    left.restart()
    assert game_snapshot(left) == game_snapshot(MvpSession(seed=159))


def test_demo_command_is_headless_and_reports_real_game_result():
    script = "import sys; sys.modules['pygame'] = None; from engine.demo import main; main()"
    result = subprocess.run([sys.executable, "-B", "-c", script],
                            cwd=Path(__file__).resolve().parents[1], env=os.environ.copy(),
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert "WON: 11 builds; HP 5/6; Supplies 5/5; altars 2/2" in result.stdout


def test_recorded_default_win_works_through_pygame_inputs(monkeypatch):
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    try:
        screen = pygame.display.set_mode(WINDOW_SIZE)
        app = GameApp(MvpSession(seed=159))
        actions = json.loads(DEFAULT_DEMO_PATH.read_text(encoding="utf-8"))["actions"]
        for action in actions:
            if action["action"] == "build":
                app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_1 + action["card"] - 1))
                for _ in range(action["turns"]):
                    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r))
            point = cell_rect(tuple(action["pos"])).center
            app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=point))
            before = game_snapshot(app.session)
            app.draw(screen)
            assert game_snapshot(app.session) == before
        assert app.session.status == GameStatus.WON
        assert app.terminal and app.session.build_turn == 11
        app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_n))
        assert app.session.status == GameStatus.PLAYING and not app.terminal
        assert app.session.resources == app.session.initial_resources
    finally:
        pygame.quit()
