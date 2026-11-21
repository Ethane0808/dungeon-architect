"""Launch the complete MVP with an optional reproducible seed."""

import argparse
from pathlib import Path
from random import randrange

import pygame

from engine.mvp import MvpSession
from ui.app import GameApp
from ui.screens import WINDOW_SIZE


def main(argv=None) -> None:
    """Importing this module never initializes pygame or opens a window."""
    parser = argparse.ArgumentParser(description="Dungeon Architect: activate the altars and reach the core")
    parser.add_argument("--seed", type=int, help="replay a map and card sequence (default: random)")
    parser.add_argument("--fullscreen", action="store_true", help="start in fullscreen mode (F11 toggles it)")
    args = parser.parse_args(argv)
    session = MvpSession(seed=randrange(1_000_000) if args.seed is None else args.seed)
    pygame.init()
    try:
        flags = pygame.FULLSCREEN if args.fullscreen else 0
        screen = pygame.display.set_mode((0, 0) if args.fullscreen else WINDOW_SIZE, flags)
        pygame.display.set_caption("Dungeon Architect")
        app = GameApp(session, fullscreen=args.fullscreen)
        preference = None
        try:
            preference = Path(pygame.system.get_pref_path("Dungeon Architect", "Dungeon Architect")) / "language.txt"
            if preference.read_text(encoding="utf-8").strip() == "zh-TW":
                app.renderer.toggle_language()
        except (OSError, UnicodeError, pygame.error):
            pass  # The game also runs without a writable preferences directory.
        initial_language = app.renderer.language
        app.open_lobby()
        app.run(screen)
        if preference and app.renderer.language != initial_language:
            try:
                preference.write_text(app.renderer.language, encoding="utf-8")
            except OSError:
                pass
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
