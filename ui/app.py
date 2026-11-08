"""Pygame input and application loop, separated from rules and drawing."""

import pygame

from engine.game import BuildSession
from ui.screens import (
    RESTART_RECT, ROTATE_RECT, GameRenderer,
    ROOM_NAMES, card_at_pixel, cell_at_pixel, cell_label, placement_message,
)


class GameApp:
    def __init__(self, session: BuildSession):
        self.session = session
        self.renderer = GameRenderer()
        self.running = True
        self.hovered_pos = None
        self.message = "Choose a room card, then explore an open exit."

    def select(self, index: int) -> None:
        if self.session.select_card(index):
            self.message = "Rotate the room or click a highlighted cell to build."

    def rotate(self, times: int = 1) -> None:
        if self.session.rotate_selected(times):
            self.message = "Teal cells show where this rotation fits."

    def restart(self) -> None:
        self.session.restart()
        self.hovered_pos = None
        self.message = "Layout restarted with the same seed. Choose a card."

    def handle_event(self, event) -> None:
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type in (pygame.WINDOWLEAVE, pygame.WINDOWFOCUSLOST):
            self.hovered_pos = None
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.running = False
            elif event.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                self.select(event.key - pygame.K_1)
            elif event.key == pygame.K_r:
                self.rotate()
            elif event.key == pygame.K_q:
                self.rotate(-1)
            elif event.key == pygame.K_n:
                self.restart()
        elif event.type == pygame.MOUSEMOTION:
            self.hovered_pos = cell_at_pixel(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.hovered_pos = cell_at_pixel(event.pos)
            if RESTART_RECT.collidepoint(event.pos):
                self.restart()
            elif ROTATE_RECT.collidepoint(event.pos):
                self.rotate()
            else:
                index = card_at_pixel(event.pos)
                if index is not None:
                    self.select(index)
                    return
                pos = cell_at_pixel(event.pos)
                if pos is None:
                    return
                self.hovered_pos = pos
                card = self.session.selected_card
                ok, reason = self.session.place(pos)
                if ok:
                    assert card is not None
                    name = ROOM_NAMES.get(card.kind, card.kind)
                    self.message = f"Built {name} at {cell_label(pos)}. Choose your next card."
                else:
                    self.message = placement_message(reason)

    def draw(self, surface) -> None:
        self.renderer.draw(surface, self.session, self.hovered_pos, self.message)

    def run(self, screen) -> None:
        clock = pygame.time.Clock()
        while self.running:
            for event in pygame.event.get():
                self.handle_event(event)
                if not self.running:
                    break
            if self.running:
                self.draw(screen)
                pygame.display.flip()
                clock.tick(60)
