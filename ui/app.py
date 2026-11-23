"""Pygame input and application loop, separated from rules and drawing."""

from dataclasses import dataclass, replace

import pygame

from engine.cards import Position
from engine.directions import N, E, S, W, neighbor_pos
from engine.game import BuildSession
from engine.navigation import route_to_build_site
from engine.tutorial import TutorialSession
from engine.messages import Message
from engine.tools import seal_card
from ui.screens import (
    RESTART_RECT, HELP_RECT, ROTATE_RECT, SEAL_RECT, CHISEL_RECT, MEDKIT_RECT, END_RESTART_RECT,
    EVENT_FEEDBACK_MS, GameRenderer, ROOM_NAMES, WINDOW_SIZE, card_at_pixel, cell_at_pixel,
    cell_label, movement_message, placement_message, tool_message, LOBBY_RECT, ENTER_RECT,
    GUIDE_RECT, EXIT_RECT, GUIDE_CLOSE_RECT, GUIDE_PREV_RECT, GUIDE_NEXT_RECT, GUIDE_PAGES,
    cache_button_rect, cache_prompt_rect,
    LANGUAGE_RECT, TUTORIAL_RECT, PLAN_GO_RECT, PLAN_CANCEL_RECT,
    TUTORIAL_SKIP_RECT, TUTORIAL_START_RECT, TUTORIAL_REPLAY_RECT,
)


MOVEMENT_KEYS = {pygame.K_UP: N, pygame.K_w: N, pygame.K_RIGHT: E, pygame.K_d: E,
                 pygame.K_DOWN: S, pygame.K_s: S, pygame.K_LEFT: W, pygame.K_a: W}
NAV_STEP_MS = 250


@dataclass(frozen=True)
class BuildPlan:
    target: Position
    entry: Position
    path: tuple[Position, ...]
    selected_index: int
    rotation: int
    seal_direction: int | None

    @property
    def steps(self) -> int:
        return len(self.path) - 1


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
        self.expedition_session = session
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
        self.pending_plan: BuildPlan | None = None
        self.auto_walking = False
        self.next_nav_step_ms = 0
        self.nav_pause_reason: str | None = None
        self.seen_tips: set[str] = set()
        self.context_tip: str | None = None
        self.tip_started_at = 0

    def show_tip(self, key: str, message: str) -> None:
        if isinstance(self.session, TutorialSession) or key in self.seen_tips:
            return
        self.seen_tips.add(key)
        self.context_tip = message
        self.tip_started_at = pygame.time.get_ticks()

    def _check_gameplay_tips(self, previous_hp: int, previous_guard, previous_loops: int) -> None:
        if not self.is_mvp or isinstance(self.session, TutorialSession):
            return
        if previous_guard is None and self.session.guard_pos is not None:
            self.show_tip("guard", "The guard moves whenever you move or build.")
        if self.session.loops_closed > previous_loops:
            self.show_tip("loop", "Loop completed! Bonus Supplies.")
        if self.session.resources.hp < previous_hp:
            self.show_tip("hp", "Use a Medkit to restore HP.")
        if self.session.trapped_cache:
            self.show_tip("chest", "Open the chest for Supplies at an HP cost.")
        if self.session.selected_card is not None and not self.session.planning_cells():
            self.show_tip("seal", "Seal an unwanted doorway to fit a room.")

    @property
    def is_mvp(self) -> bool:
        return hasattr(self.session, "level")

    @property
    def terminal(self) -> bool:
        return getattr(self.session, "status", "PLAYING") in ("WON", "LOST")

    def clear_tools(self) -> None:
        self.seal_direction = None
        self.chisel_mode = False

    def cancel_plan(self) -> None:
        if isinstance(self.session, TutorialSession) and self.session.lesson == 3:
            self.session.plan_created = False
        self.pending_plan = None
        self.auto_walking = False
        self.next_nav_step_ms = 0
        self.nav_pause_reason = None

    def _planned_card(self):
        card = self.session.selected_card
        if card is None:
            return None
        if self.seal_direction is None:
            return card
        try:
            return seal_card(card, self.seal_direction)
        except ValueError:
            return None

    def refresh_plan(self) -> bool:
        """Revalidate a UI-only plan and recompute its route from the live player."""
        plan = self.pending_plan
        if plan is None or self.terminal or not self.is_mvp:
            if plan is not None:
                self.cancel_plan()
            return False
        if (
            self.session.selected_index != plan.selected_index
            or self.session.rotations[plan.selected_index] != plan.rotation
            or self.seal_direction != plan.seal_direction
        ):
            self.cancel_plan()
            return False
        preview = (self.session.geometry_preview(plan.target) if plan.seal_direction is None
                   else self.session.geometry_preview_with_seal(plan.target, plan.seal_direction))
        card = self._planned_card()
        route = None if card is None or not preview[0] else route_to_build_site(
            self.session.board, self.session.player_pos, plan.target, card.doors)
        if route is None:
            self.cancel_plan()
            return False
        self.pending_plan = replace(plan, entry=route.entry, path=route.path)
        return True

    def set_plan(self, target: Position) -> bool:
        if not self.is_mvp or self.session.selected_index is None:
            return False
        preview = (self.session.geometry_preview(target) if self.seal_direction is None
                   else self.session.geometry_preview_with_seal(target, self.seal_direction))
        card = self._planned_card()
        route = None if card is None or not preview[0] else route_to_build_site(
            self.session.board, self.session.player_pos, target, card.doors)
        if route is None:
            self.message = placement_message(preview[1])
            return False
        index = self.session.selected_index
        self.pending_plan = BuildPlan(target, route.entry, route.path, index,
                                      self.session.rotations[index], self.seal_direction)
        if isinstance(self.session, TutorialSession):
            self.session.mark_plan(target)
        self.auto_walking = False
        self.nav_pause_reason = None
        self.message = Message("Planned {target}. Entrance {entry}, {steps} steps. Press G to walk.",
                               target=cell_label(target), entry=cell_label(route.entry), steps=route.steps)
        return True

    def start_or_pause_auto_walk(self) -> None:
        if self.pending_plan is None or not self.refresh_plan():
            return
        if self.auto_walking:
            self.auto_walking = False
            self.nav_pause_reason = "paused"
            self.message = "Automatic walking paused. Press G to resume."
            return
        if self.pending_plan.steps == 0:
            self.nav_pause_reason = "arrived"
            self.message = "Ready — press Enter to build."
            return
        self.auto_walking = True
        self.nav_pause_reason = None
        self.next_nav_step_ms = pygame.time.get_ticks()
        self.message = "Walking to the entrance. Each step advances the guard."

    def advance_auto_walk(self, now_ms: int) -> None:
        """Advance at most one normal MVP move when the navigation timer expires."""
        if not self.auto_walking or now_ms < self.next_nav_step_ms:
            return
        if not self.refresh_plan() or self.pending_plan is None:
            return
        plan = self.pending_plan
        if plan.steps == 0:
            self.auto_walking = False
            self.nav_pause_reason = "arrived"
            self.message = "Ready — press Enter to build."
            return
        next_pos = plan.path[1]
        if next_pos in (getattr(self.session, "guard_pos", None), getattr(self.session, "guard_next", None)):
            self.auto_walking = False
            self.nav_pause_reason = "guard"
            self.message = "Paused before the guard's threatened room. Move manually or press G to resume."
            return
        hp_before = self.session.resources.hp
        event_before = self.session.current_event
        altars_before = self.session.activated_altars
        status_before = self.session.status
        if not self.move(next_pos, automated=True):
            self.auto_walking = False
            self.nav_pause_reason = "route"
            return
        self.next_nav_step_ms = now_ms + NAV_STEP_MS
        changed = (
            self.session.resources.hp != hp_before
            or self.session.current_event is not event_before
            or self.session.activated_altars != altars_before
            or self.session.status != status_before
        )
        if self.terminal:
            self.cancel_plan()
        elif changed:
            self.auto_walking = False
            self.nav_pause_reason = "event"
            self.message = "Navigation paused after an event or objective change. Press G to resume."
        elif self.pending_plan is not None and self.pending_plan.steps == 0:
            self.auto_walking = False
            self.nav_pause_reason = "arrived"
            self.message = "Ready — press Enter to build."

    def confirm_plan(self) -> bool:
        if self.pending_plan is None or not self.refresh_plan() or self.pending_plan is None:
            return False
        plan = self.pending_plan
        if plan.steps:
            self.message = Message("Walk to entrance {entry} before building.", entry=cell_label(plan.entry))
            return False
        card = self.session.selected_card
        event_before = self.session.current_event
        ok, reason = (self.session.place(plan.target) if plan.seal_direction is None
                      else self.session.place_with_seal(plan.target, plan.seal_direction))
        if not ok:
            self.message = tool_message(reason) if plan.seal_direction is not None else placement_message(reason)
            self.refresh_plan()
            return False
        assert card is not None
        name = ROOM_NAMES.get(card.kind, card.kind)
        target = plan.target
        self.cancel_plan()
        self.clear_tools()
        self.capture_event_feedback(event_before)
        self.message = Message("Built {name} at {cell}. Choose your next card.", name=name, cell=cell_label(target))
        return True

    def open_lobby(self) -> None:
        self.cancel_plan()
        if isinstance(self.session, TutorialSession):
            self.session = self.expedition_session
            self.clear_tools()
        self.in_lobby = True
        self.hovered_pos = None
        self.event_feedback = None

    def enter_expedition(self) -> None:
        if self.terminal:
            self.restart()
        self.in_lobby = False
        self.expedition_started = True

    def start_tutorial(self):
        self.cancel_plan()
        if not isinstance(self.session, TutorialSession):
            self.expedition_session = self.session
        self.session = TutorialSession()
        self.restart()
        self.in_lobby = False

    def select(self, index: int) -> None:
        if self.session.select_card(index):
            self.cancel_plan()
            self.clear_tools()
            self.message = "Rotate the room or click a highlighted cell to build."
            if self.is_mvp:
                self._check_gameplay_tips(self.session.resources.hp, self.session.guard_pos, self.session.loops_closed)

    def rotate(self, times: int = 1) -> None:
        if self.session.rotate_selected(times):
            self.cancel_plan()
            self.clear_tools()
            self.message = "Green cells show where this rotation fits."

    def restart(self) -> None:
        self.cancel_plan()
        self.session.restart()
        if not isinstance(self.session, TutorialSession):
            self.seen_tips.clear()
            self.context_tip = None
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
        self.auto_walking = False
        previous = self.session.current_event
        if self.session.open_trapped_cache():
            self.capture_event_feedback(previous)
            self.message = "Chest emptied. Explore another room."

    def toggle_help(self) -> None:
        self.help_open = not self.help_open
        self.help_page = 0

    def use_medkit(self) -> None:
        self.auto_walking = False
        previous = self.session.current_event
        ok, reason = self.session.use_medkit()
        if ok:
            self.capture_event_feedback(previous)
            self.message = self.session.current_event.message
        else:
            self.message = "Health is already full." if reason == "full_health" else "A medkit needs 2 supplies."

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

    def move(self, pos, *, automated: bool = False) -> bool:
        if not automated:
            self.auto_walking = False
            if self.pending_plan is not None:
                self.nav_pause_reason = "manual"
        activated_before = self.session.activated_altars if self.is_mvp else None
        hp_before = self.session.resources.hp
        guard_before = self.session.guard_pos if self.is_mvp else None
        loops_before = self.session.loops_closed if self.is_mvp else 0
        event_before = self.session.current_event
        ok, reason = self.session.move(pos)
        if ok:
            if self.pending_plan is None:
                self.clear_tools()
            else:
                self.chisel_mode = False
        self.message = (Message("Moved to {cell}.", cell=cell_label(pos))
                        if ok else movement_message(reason))
        notice = self.session.current_event
        if ok and notice is not None and notice is not event_before and notice.category == "guard":
            self.message = notice.message
        if ok and self.is_mvp and (
            self.session.activated_altars != activated_before
            or (pos == self.session.level.core.pos and self.session.status == "WON")
        ):
            self.message = self.session.objective_message
        if ok:
            self.capture_event_feedback(event_before)
            self._check_gameplay_tips(hp_before, guard_before, loops_before)
            if self.terminal:
                self.cancel_plan()
            elif self.pending_plan is not None:
                self.refresh_plan()
        return ok

    def cycle_seal(self) -> None:
        if not self.is_mvp or self.terminal:
            return
        card = self.session.selected_card
        if card is None:
            self.message = "Choose a room card before sealing a door."
            return
        self.cancel_plan()
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
        self.cancel_plan()
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
                if self.pending_plan is not None:
                    self.cancel_plan()
                    self.message = "Construction plan cancelled."
                else:
                    self.running = False
            elif self.in_lobby:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self.enter_expedition()
                elif event.key == pygame.K_t:
                    self.start_tutorial()
            elif isinstance(self.session, TutorialSession) and self.session.lesson == 5:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self.open_lobby()
                    self.enter_expedition()
                elif event.key == pygame.K_t:
                    self.start_tutorial()
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
            elif event.key == pygame.K_g:
                self.start_or_pause_auto_walk()
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.pending_plan is not None:
                self.confirm_plan()
            elif self.is_mvp and event.key == pygame.K_m:
                self.use_medkit()
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
                elif TUTORIAL_RECT.collidepoint(pos):
                    self.start_tutorial()
                elif GUIDE_RECT.collidepoint(pos):
                    self.toggle_help()
                elif EXIT_RECT.collidepoint(pos):
                    self.running = False
                return
            if isinstance(self.session, TutorialSession):
                if self.session.lesson == 5:
                    if TUTORIAL_START_RECT.collidepoint(pos):
                        self.open_lobby()
                        self.enter_expedition()
                    elif TUTORIAL_REPLAY_RECT.collidepoint(pos):
                        self.start_tutorial()
                    return
                if TUTORIAL_SKIP_RECT.collidepoint(pos):
                    self.open_lobby()
                    self.enter_expedition()
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
            elif self.pending_plan is not None and PLAN_GO_RECT.collidepoint(pos):
                self.start_or_pause_auto_walk()
            elif self.pending_plan is not None and PLAN_CANCEL_RECT.collidepoint(pos):
                self.cancel_plan()
                self.message = "Construction plan cancelled."
            elif ROTATE_RECT.collidepoint(pos):
                self.rotate()
            elif self.is_mvp and SEAL_RECT.collidepoint(pos):
                self.cycle_seal()
            elif self.is_mvp and CHISEL_RECT.collidepoint(pos):
                self.toggle_chisel()
            elif self.is_mvp and MEDKIT_RECT.collidepoint(pos):
                self.use_medkit()
            elif self.session.trapped_cache and cache_button_rect(self.session.player_pos).collidepoint(pos):
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
                hp_before = self.session.resources.hp
                guard_before = self.session.guard_pos if self.is_mvp else None
                loops_before = self.session.loops_closed if self.is_mvp else 0
                if self.is_mvp:
                    local = (self.session.preview(cell) if self.seal_direction is None
                             else self.session.preview_with_seal(cell, self.seal_direction))
                    geometry = (self.session.geometry_preview(cell) if self.seal_direction is None
                                else self.session.geometry_preview_with_seal(cell, self.seal_direction))
                    if not local[0] and geometry[0]:
                        self.set_plan(cell)
                        return
                ok, reason = (self.session.place(cell) if self.seal_direction is None
                              else self.session.place_with_seal(cell, self.seal_direction))
                if ok:
                    self.cancel_plan()
                    self.clear_tools()
                    self.capture_event_feedback(event_before)
                    self._check_gameplay_tips(hp_before, guard_before, loops_before)
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
        if self.context_tip is not None and pygame.time.get_ticks() - self.tip_started_at >= 4000:
            self.context_tip = None
        target = surface if surface.get_size() == WINDOW_SIZE else self.logical_surface
        if self.in_lobby:
            self.renderer.lobby(target, self.session.seed, self.expedition_started, self.terminal)
            if self.help_open:
                self.renderer.help_overlay(target, self.help_page)
        else:
            self.renderer.draw(target, self.session, self.hovered_pos, self.message,
                               seal_direction=self.seal_direction, chisel_mode=self.chisel_mode,
                               help_open=self.help_open, help_page=self.help_page, event_feedback=self.event_feedback,
                               feedback_age=feedback_age, pending_plan=self.pending_plan,
                               auto_walking=self.auto_walking, nav_pause_reason=self.nav_pause_reason)
        self.renderer.language_button(target)
        if isinstance(self.session, TutorialSession) and not self.in_lobby and not self.help_open:
            self.renderer.tutorial(target, self.session)
        elif self.context_tip is not None and not self.in_lobby and not self.help_open:
            self.renderer.context_tip(target, self.context_tip)
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
                self.advance_auto_walk(pygame.time.get_ticks())
                self.draw(self.display_surface)
                pygame.display.flip()
                clock.tick(60)
