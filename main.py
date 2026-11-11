"""Launch the exploration sandbox with an optional reproducible seed."""

import argparse

import pygame

from engine.game import BuildSession
from ui.app import GameApp
from ui.screens import WINDOW_SIZE


def main(argv=None) -> None:
    """Importing this module never initializes pygame or opens a window."""
    parser = argparse.ArgumentParser(description="Dungeon Architect construction sandbox")
    parser.add_argument("--seed", type=int, default=42, help="reproducible card-draw seed (default: 42)")
    args = parser.parse_args(argv)
    session = BuildSession(seed=args.seed)
    pygame.init()
    try:
        screen = pygame.display.set_mode(WINDOW_SIZE)
        pygame.display.set_caption("Dungeon Architect")
        GameApp(session).run(screen)
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
