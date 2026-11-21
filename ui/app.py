"""Pygame input and application loop, separated from rules and drawing."""

import pygame

from engine.directions import N, E, S, W, neighbor_pos
from engine.game import BuildSession
from engine.messages import Message
from ui.screens import (
    RESTART_RECT, HELP_RECT, ROTATE_RECT, SEAL_RECT, CHISEL_RECT, END_RESTART_RECT,
    EVENT_FEEDBACK_MS, GameRenderer, ROOM_NAMES, WINDOW_SIZE, card_at_pixel, cell_at_pixel,
    cell_label, movement_message, placement_message, tool_message, LOBBY_RECT, ENTER_RECT,
    GUIDE_RECT, EXIT_RECT, GUIDE_CLOSE_RECT, GUIDE_PREV_RECT, GUIDE_NEXT_RECT, GUIDE_PAGES, CACHE_RECT,
    LANGUAGE_RECT,
)


MOVEMENT_KEYS = {pygame.K_UP: N, pygame.K_w: N, pygame.K_RIGHT: E, pygame.K_d: E,
                 pygame.K_DOWN: S, pygame.K_s: S, pygame.K_LEFT: W, pygame.K_a: W}


def display_viewport(size: tuple[int, int]) -> pygame.Rect:
    """Largest centered viewport that preserves the logical canvas aspect ratio."""
    width, height = size
    scale = min(width / WINDOW_SIZE[0], height / WINDOW_SIZE[1])
    viewport_size = (max(1, round(WINDOW_SIZE[0] * scale)),
                     max(1, round(WINDOW_SIZE[1] * scale)))
    return pygame.Rect((width - viewport_size[0]) // 2, (height - viewport_size[1]) // 2,
                       *viewport_size)


class GameApp:
    def __init__(self, session: BuildSession, *, fullscreen: bool = False):
        self.session = session
        self.renderer = GameRenderer()
        self.running = True
        self.hovered_pos = None
        self.message = getattr(session, "objective_message", "Choose a room card, then explore an open exit.")
        self.seal_direction: int | None = None
        self.chisel_mode = False
        self.help_open = False
        self.help_page = 0
        self.in_lobby = False
        self.expedition_started = False
        self.fullscreen = fullscreen
        self.display_surface: pygame.Surface | None = None
        self.logical_surface = pygame.Surface(WINDOW_SIZE)
        self.event_feedback = None
        self.event_feedback_started_at = 0

    @property
    def is_mvp(self) -> bool:
        return hasattr(self.session, "level")

    @property
    def terminal(self) -> bool:
        return getattr(self.session, "status", "PLAYING") in ("WON", "LOST")

    def clear_tools(self) -> None:
        self.seal_direction = None
        self.chisel_mode = False

    def open_lobby(self) -> None:
        self.in_lobby = True
        self.hovered_pos = None
        self.event_feedback = None

    def enter_expedition(self) -> None:
        if self.terminal:
            self.restart()
        self.in_lobby = False
        self.expedition_started = True

    def select(self, index: int) -> None:
        if self.session.select_card(index):
            self.clear_tools()
            self.message = "Rotate the room or click a highlighted cell to build."

    def rotate(self, times: int = 1) -> None:
        if self.session.rotate_selected(times):
            self.clear_tools()
            self.message = "Green cells show where this rotation fits."

    def restart(self) -> None:
        self.session.restart()
        self.hovered_pos = None
        self.clear_tools()
        self.event_feedback = None
        self.message = "Layout restarted with the same seed. Choose a card."

    def capture_event_feedback(self, previous) -> None:
        notification = self.session.current_event
        if notification is not None and notification is not previous:
            self.event_feedback = notification
            self.event_feedback_started_at = pygame.time.get_ticks()

    def open_cache(self) -> None:
        previous = self.session.current_event
        if self.session.open_trapped_cache():
            self.capture_event_feedback(previous)
            self.message = "Chest emptied. Explore another room."

    def toggle_help(self) -> None:
        self.help_open = not self.help_open
        self.help_page = 0

    def turn_help_page(self, step: int) -> None:
        self.help_page = max(0, min(len(GUIDE_PAGES) - 1, self.help_page + step))

    def toggle_fullscreen(self) -> None:
        """Switch display modes without changing any game state."""
        self.fullscreen = not self.fullscreen
        flags = pygame.FULLSCREEN if self.fullscreen else 0
        size = (0, 0) if self.fullscreen else WINDOW_SIZE
        self.display_surface = pygame.display.set_mode(size, flags)

    def logical_pos(self, pos: tuple[int, int]) -> tuple[int, int] | None:
        """Translate a display-space pointer into the fixed logical UI canvas."""
        surface = self.display_surface or pygame.display.get_surface()
        if surface is None or surface.get_size() == WINDOW_SIZE:
            return pos
        viewport = display_viewport(surface.get_size())
        if not viewport.collidepoint(pos):
            return None
        return (min(WINDOW_SIZE[0] - 1, (pos[0] - viewport.left) * WINDOW_SIZE[0] // viewport.width),
                min(WINDOW_SIZE[1] - 1, (pos[1] - viewport.top) * WINDOW_SIZE[1] // viewport.height))

    def move(self, pos) -> None:
        activated_before = self.session.activated_altars if self.is_mvp else None
        event_before = self.session.current_event
        ok, reason = self.session.move(pos)
        if ok:
            self.clear_tools()
        self.message = (Message("Moved to {cell}. Backtracking is free.", cell=cell_label(pos))
                        if ok else movement_message(reason))
        if ok and self.is_mvp and (
            self.session.activated_altars != activated_before
            or (pos == self.session.level.core.pos and self.session.status == "WON")
        ):
            self.message = self.session.objective_message
        if ok:
            self.capture_event_feedback(event_before)

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
            self.message = Message("Seal the {side} door when building. Cost: {cost} Supplies. F cycles doors.", side=side, cost=cost)

    def toggle_chisel(self) -> None:
        if not self.is_mvp or self.terminal:
            return
        self.seal_direction = None
        self.chisel_mode = not self.chisel_mode
        cost = self.session.tools.emergency_chisel.cost_supplies
        self.message = (Message("Click an adjacent room across a shared wall. Chisel costs {cost} Supplies. C cancels.", cost=cost)
                        if self.chisel_mode else "Chisel cancelled. Walk or build normally.")

    def handle_event(self, event) -> None:
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type in (pygame.WINDOWLEAVE, pygame.WINDOWFOCUSLOST):
            self.hovered_pos = None
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_F2:
                self.renderer.toggle_language()
            elif event.key in (pygame.K_h, pygame.K_QUESTION):
                self.toggle_help()
            elif event.key == pygame.K_F11:
                self.toggle_fullscreen()
            elif self.help_open and event.key == pygame.K_ESCAPE:
                self.help_open = False
            elif self.help_open:
                if event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                    self.turn_help_page(1 if event.key == pygame.K_RIGHT else -1)
                return
            elif event.key == pygame.K_ESCAPE:
                self.running = False
            elif self.in_lobby:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self.enter_expedition()
            elif event.key == pygame.K_l:
                self.open_lobby()
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
            elif event.key == pygame.K_e:
                self.open_cache()
            elif event.key in MOVEMENT_KEYS:
                self.move(neighbor_pos(*self.session.player_pos, MOVEMENT_KEYS[event.key]))
        elif event.type == pygame.MOUSEMOTION and not self.in_lobby:
            pos = self.logical_pos(event.pos)
            self.hovered_pos = cell_at_pixel(pos) if pos is not None else None
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = self.logical_pos(event.pos)
            if pos is None:
                self.hovered_pos = None
                return
            if LANGUAGE_RECT.collidepoint(pos):
                self.renderer.toggle_language()
                return
            if self.help_open:
                if GUIDE_CLOSE_RECT.collidepoint(pos) or HELP_RECT.collidepoint(pos):
                    self.help_open = False
                elif GUIDE_PREV_RECT.collidepoint(pos):
                    self.turn_help_page(-1)
                elif GUIDE_NEXT_RECT.collidepoint(pos):
                    self.turn_help_page(1)
                return
            if self.in_lobby:
                if ENTER_RECT.collidepoint(pos):
                    self.enter_expedition()
                elif GUIDE_RECT.collidepoint(pos):
                    self.toggle_help()
                elif EXIT_RECT.collidepoint(pos):
                    self.running = False
                return
            self.hovered_pos = cell_at_pixel(pos)
            if HELP_RECT.collidepoint(pos):
                self.toggle_help()
            elif LOBBY_RECT.collidepoint(pos):
                self.open_lobby()
            elif RESTART_RECT.collidepoint(pos):
                self.restart()
            elif self.terminal:
                if END_RESTART_RECT.collidepoint(pos):
                    self.restart()
                return
            elif ROTATE_RECT.collidepoint(pos):
                self.rotate()
            elif self.is_mvp and SEAL_RECT.collidepoint(pos):
                self.cycle_seal()
            elif self.is_mvp and CHISEL_RECT.collidepoint(pos):
                self.toggle_chisel()
            elif self.session.trapped_cache and CACHE_RECT.collidepoint(pos):
                self.open_cache()
            else:
                index = card_at_pixel(pos)
                if index is not None:
                    self.select(index)
                    return
                cell = cell_at_pixel(pos)
                if cell is None:
                    return
                self.hovered_pos = cell
                if self.chisel_mode:
                    event_before = self.session.current_event
                    ok, reason = self.session.chisel(self.session.player_pos, cell)
                    if ok:
                        self.clear_tools()
                        self.capture_event_feedback(event_before)
                        self.message = Message("Opened matching doors toward {cell}. You can walk through.", cell=cell_label(cell))
                    else:
                        self.message = tool_message(reason)
                    return
                if self.session.board[cell[0]][cell[1]] is not None and cell != self.session.player_pos:
                    self.move(cell)
                    return
                card = self.session.selected_card
                event_before = self.session.current_event
                ok, reason = (self.session.place(cell) if self.seal_direction is None
                              else self.session.place_with_seal(cell, self.seal_direction))
                if ok:
                    self.clear_tools()
                    self.capture_event_feedback(event_before)
                    assert card is not None
                    name = ROOM_NAMES.get(card.kind, card.kind)
                    self.message = Message("Built {name} at {cell}. Choose your next card.", name=name, cell=cell_label(cell))
                else:
                    self.message = (tool_message(reason) if self.seal_direction is not None
                                    else placement_message(reason))

    def draw(self, surface) -> None:
        feedback_age = 0
        if self.event_feedback is not None:
            feedback_age = pygame.time.get_ticks() - self.event_feedback_started_at
            if feedback_age >= EVENT_FEEDBACK_MS:
                self.event_feedback = None
        target = surface if surface.get_size() == WINDOW_SIZE else self.logical_surface
        if self.in_lobby:
            self.renderer.lobby(target, self.session.seed, self.expedition_started, self.terminal)
            if self.help_open:
                self.renderer.help_overlay(target, self.help_page)
        else:
            self.renderer.draw(target, self.session, self.hovered_pos, self.message,
                               seal_direction=self.seal_direction, chisel_mode=self.chisel_mode,
                               help_open=self.help_open, help_page=self.help_page, event_feedback=self.event_feedback,
                               feedback_age=feedback_age)
        self.renderer.language_button(target)
        if target is not surface:
            viewport = display_viewport(surface.get_size())
            surface.fill((4, 8, 14))
            surface.blit(pygame.transform.smoothscale(target, viewport.size), viewport)

    def run(self, screen) -> None:
        self.display_surface = screen
        clock = pygame.time.Clock()
        while self.running:
            for event in pygame.event.get():
                self.handle_event(event)
                if not self.running:
                    break
            if self.running:
                self.draw(self.display_surface)
                pygame.display.flip()
                clock.tick(60)
