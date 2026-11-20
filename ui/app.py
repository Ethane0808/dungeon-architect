"""Pygame input and application loop, separated from rules and drawing."""

import pygame

from engine.directions import N, E, S, W, neighbor_pos
from engine.game import BuildSession
from ui.screens import (
    RESTART_RECT, HELP_RECT, ROTATE_RECT, SEAL_RECT, CHISEL_RECT, END_RESTART_RECT, GameRenderer,
    ROOM_NAMES, card_at_pixel, cell_at_pixel, cell_label, movement_message, placement_message, tool_message,
)


MOVEMENT_KEYS = {pygame.K_UP: N, pygame.K_w: N, pygame.K_RIGHT: E, pygame.K_d: E,
                 pygame.K_DOWN: S, pygame.K_s: S, pygame.K_LEFT: W, pygame.K_a: W}


class GameApp:
    def __init__(self, session: BuildSession):
        self.session = session
        self.renderer = GameRenderer()
        self.running = True
        self.hovered_pos = None
        self.message = getattr(session, "objective_message", "Choose a room card, then explore an open exit.")
        self.seal_direction: int | None = None
        self.chisel_mode = False
        self.help_open = False

    @property
    def is_mvp(self) -> bool:
        return hasattr(self.session, "level")

    @property
    def terminal(self) -> bool:
        return getattr(self.session, "status", "PLAYING") in ("WON", "LOST")

    def clear_tools(self) -> None:
        self.seal_direction = None
        self.chisel_mode = False

    def select(self, index: int) -> None:
        if self.session.select_card(index):
            self.clear_tools()
            self.message = "Rotate the room or click a highlighted cell to build."

    def rotate(self, times: int = 1) -> None:
        if self.session.rotate_selected(times):
            self.clear_tools()
            self.message = "Teal cells show where this rotation fits."

    def restart(self) -> None:
        self.session.restart()
        self.hovered_pos = None
        self.clear_tools()
        self.message = "Layout restarted with the same seed. Choose a card."

    def move(self, pos) -> None:
        activated_before = self.session.activated_altars if self.is_mvp else None
        ok, reason = self.session.move(pos)
        if ok:
            self.clear_tools()
        self.message = (f"Moved to {cell_label(pos)}. Backtracking is free."
                        if ok else movement_message(reason))
        if ok and self.is_mvp and (
            self.session.activated_altars != activated_before
            or (pos == self.session.level.core.pos and self.session.status == "WON")
        ):
            self.message = self.session.objective_message

    def cycle_seal(self) -> None:
        if not self.is_mvp or self.terminal:
            return
        card = self.session.selected_card
        if card is None:
            self.message = "Choose a room card before sealing a door."
            return
        self.chisel_mode = False
        choices = [side for side, door in enumerate(card.doors) if door] + [None]
        current = choices.index(self.seal_direction) if self.seal_direction in choices else len(choices) - 1
        self.seal_direction = choices[(current + 1) % len(choices)]
        if self.seal_direction is None:
            self.message = "Door Seal cancelled. Ordinary construction selected."
        else:
            side = ("north", "east", "south", "west")[self.seal_direction]
            cost = self.session.tools.door_seal.cost_supplies
            self.message = f"Seal the {side} door when building. Cost: {cost} Supplies. F cycles doors."

    def toggle_chisel(self) -> None:
        if not self.is_mvp or self.terminal:
            return
        self.seal_direction = None
        self.chisel_mode = not self.chisel_mode
        cost = self.session.tools.emergency_chisel.cost_supplies
        self.message = (f"Click an adjacent room across a shared wall. Chisel costs {cost} Supplies. C cancels."
                        if self.chisel_mode else "Chisel cancelled. Walk or build normally.")

    def handle_event(self, event) -> None:
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type in (pygame.WINDOWLEAVE, pygame.WINDOWFOCUSLOST):
            self.hovered_pos = None
        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_h, pygame.K_QUESTION):
                self.help_open = not self.help_open
            elif self.help_open and event.key == pygame.K_ESCAPE:
                self.help_open = False
            elif self.help_open:
                return
            elif event.key == pygame.K_ESCAPE:
                self.running = False
            elif event.key == pygame.K_n:
                self.restart()
            elif self.terminal:
                return
            elif event.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                self.select(event.key - pygame.K_1)
            elif event.key == pygame.K_r:
                self.rotate()
            elif event.key == pygame.K_q:
                self.rotate(-1)
            elif event.key == pygame.K_f:
                self.cycle_seal()
            elif event.key == pygame.K_c:
                self.toggle_chisel()
            elif event.key in MOVEMENT_KEYS:
                self.move(neighbor_pos(*self.session.player_pos, MOVEMENT_KEYS[event.key]))
        elif event.type == pygame.MOUSEMOTION:
            self.hovered_pos = cell_at_pixel(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.hovered_pos = cell_at_pixel(event.pos)
            if HELP_RECT.collidepoint(event.pos):
                self.help_open = not self.help_open
            elif self.help_open:
                return
            elif RESTART_RECT.collidepoint(event.pos):
                self.restart()
            elif self.terminal:
                if END_RESTART_RECT.collidepoint(event.pos):
                    self.restart()
                return
            elif ROTATE_RECT.collidepoint(event.pos):
                self.rotate()
            elif self.is_mvp and SEAL_RECT.collidepoint(event.pos):
                self.cycle_seal()
            elif self.is_mvp and CHISEL_RECT.collidepoint(event.pos):
                self.toggle_chisel()
            else:
                index = card_at_pixel(event.pos)
                if index is not None:
                    self.select(index)
                    return
                pos = cell_at_pixel(event.pos)
                if pos is None:
                    return
                self.hovered_pos = pos
                if self.chisel_mode:
                    ok, reason = self.session.chisel(self.session.player_pos, pos)
                    if ok:
                        self.clear_tools()
                        self.message = f"Opened matching doors toward {cell_label(pos)}. You can walk through."
                    else:
                        self.message = tool_message(reason)
                    return
                if self.session.board[pos[0]][pos[1]] is not None and pos != self.session.player_pos:
                    self.move(pos)
                    return
                card = self.session.selected_card
                ok, reason = (self.session.place(pos) if self.seal_direction is None
                              else self.session.place_with_seal(pos, self.seal_direction))
                if ok:
                    self.clear_tools()
                    assert card is not None
                    name = ROOM_NAMES.get(card.kind, card.kind)
                    self.message = f"Built {name} at {cell_label(pos)}. Choose your next card."
                else:
                    self.message = (tool_message(reason) if self.seal_direction is not None
                                    else placement_message(reason))

    def draw(self, surface) -> None:
        self.renderer.draw(surface, self.session, self.hovered_pos, self.message,
                           seal_direction=self.seal_direction, chisel_mode=self.chisel_mode,
                           help_open=self.help_open)

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
