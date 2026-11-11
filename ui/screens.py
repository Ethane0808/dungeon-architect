"""Room/map/card drawing, resource HUD and first-entry event feedback."""

import re

import pygame

from engine.game import BuildSession
from engine.models import BOARD_SIZE


WINDOW_SIZE = (1100, 740)
CELL_SIZE = 72
BOARD_RECT = pygame.Rect(60, 124, CELL_SIZE * BOARD_SIZE, CELL_SIZE * BOARD_SIZE)
CARD_RECTS = tuple(pygame.Rect(626, 112 + index * 156, 442, 144) for index in range(3))
RESTART_RECT = pygame.Rect(922, 24, 146, 40)
ROTATE_RECT = pygame.Rect(626, 594, 170, 40)
EVENT_RECT = pygame.Rect(626, 646, 442, 62)

BACKGROUND = (14, 22, 32)
PANEL = (22, 33, 46)
CELL = (29, 43, 56)
LINE = (46, 66, 81)
TEXT = (229, 237, 239)
MUTED = (151, 174, 185)
TEAL = (72, 204, 171)
GOLD = (238, 190, 103)
RED = (229, 113, 119)
EVENT_COLORS = {"supply": TEAL, "danger": RED, "neutral": MUTED}
ROOM_NAMES = {"dead_end": "Dead end", "straight": "Straight", "corner": "Corner",
              "t_junction": "T junction", "cross": "Cross", "start": "Start"}


def cell_at_pixel(point: tuple[int, int]) -> tuple[int, int] | None:
    if not BOARD_RECT.collidepoint(point):
        return None
    return (point[1] - BOARD_RECT.top) // CELL_SIZE, (point[0] - BOARD_RECT.left) // CELL_SIZE


def cell_rect(pos: tuple[int, int]) -> pygame.Rect:
    row, col = pos
    return pygame.Rect(BOARD_RECT.left + col * CELL_SIZE, BOARD_RECT.top + row * CELL_SIZE,
                       CELL_SIZE, CELL_SIZE)


def card_at_pixel(point: tuple[int, int]) -> int | None:
    return next((index for index, rect in enumerate(CARD_RECTS) if rect.collidepoint(point)), None)


def cell_label(pos: tuple[int, int]) -> str:
    return f"{chr(ord('A') + pos[1])}{pos[0] + 1}"


def placement_message(reason: str) -> str:
    messages = {
        "ok": "Fits here. Click to build.",
        "no_card_selected": "Choose a room card first.",
        "no_normal_placement": "No normal room fits. Restart to try another layout.",
        "out_of_bounds": "Place rooms inside the map.",
        "cell_occupied": "That cell already contains a room.",
        "no_reachable_source": "Connect a door to an explored room's open exit.",
    }
    if reason in messages:
        return messages[reason]
    direction = re.search(r"direction=(\d)", reason)
    side = ("north", "east", "south", "west")[int(direction[1])] if direction else "adjacent"
    if reason.startswith("edge_mismatch"):
        return f"Door/wall mismatch on the {side} side."
    if reason.startswith("door_faces_outside_board"):
        return f"The {side} door would face outside the map."
    return "This room cannot be placed here."


def movement_message(reason: str) -> str:
    return {
        "ok": "Click to walk into this room. Backtracking is free.",
        "out_of_bounds": "Stay inside the map.",
        "not_adjacent": "Walk one room at a time using arrows or WASD.",
        "no_room": "Build a room before walking there.",
        "doors_not_connected": "Both rooms need matching doors to walk through.",
        "room_locked": "This room is locked.",
        "invalid_source": "Your current room cannot be traversed.",
    }.get(reason, "You cannot walk there.")


class GameRenderer:
    def __init__(self):
        self.title_font = pygame.font.Font(None, 34)
        self.heading_font = pygame.font.Font(None, 26)
        self.font = pygame.font.Font(None, 22)
        self.small_font = pygame.font.Font(None, 18)

    def text(self, surface, message, pos, color=TEXT, font=None):
        surface.blit((font or self.font).render(message, True, color), pos)

    def fit_text(self, message: str, width: int) -> str:
        """Shorten a display label without changing its underlying value."""
        if self.font.size(message)[0] <= width:
            return message
        suffix = "..."
        if self.font.size(suffix)[0] > width:
            return ""
        low, high = 0, len(message)
        while low < high:
            middle = (low + high + 1) // 2
            if self.font.size(message[:middle] + suffix)[0] <= width:
                low = middle
            else:
                high = middle - 1
        return message[:low] + suffix

    def wrapped_text(self, surface, message, rect, color=TEXT):
        lines = [""]
        for word in message.split():
            candidate = (lines[-1] + " " + word).strip()
            if self.font.size(candidate)[0] > rect.width and lines[-1]:
                lines.append(word)
            else:
                lines[-1] = candidate
        for index, line in enumerate(lines[:2]):
            self.text(surface, line, (rect.x, rect.y + index * 23), color)

    def button(self, surface, rect, label, enabled=True):
        pygame.draw.rect(surface, (36, 53, 65) if enabled else PANEL, rect, border_radius=8)
        pygame.draw.rect(surface, LINE, rect, width=1, border_radius=8)
        label_surface = self.font.render(label, True, TEXT if enabled else MUTED)
        surface.blit(label_surface, label_surface.get_rect(center=rect.center))

    def room(self, surface, rect, doors, color=TEAL):
        """Draw explicit walls and door gaps in the same N/E/S/W order as the engine."""
        bounds = rect.inflate(-10, -10)
        pygame.draw.rect(surface, (43, 60, 70), bounds, border_radius=5)
        cx, cy = bounds.center
        ends = ((cx, bounds.top), (bounds.right, cy), (cx, bounds.bottom), (bounds.left, cy))
        width = max(8, bounds.width // 6)
        for direction, has_door in enumerate(doors):
            if has_door:
                pygame.draw.line(surface, color, (cx, cy), ends[direction], width)
        center = pygame.Rect(0, 0, width + 8, width + 8)
        center.center = bounds.center
        pygame.draw.rect(surface, color, center, border_radius=4)
        edges = (
            ((bounds.left, bounds.top), (bounds.right, bounds.top)),
            ((bounds.right, bounds.top), (bounds.right, bounds.bottom)),
            ((bounds.left, bounds.bottom), (bounds.right, bounds.bottom)),
            ((bounds.left, bounds.top), (bounds.left, bounds.bottom)),
        )
        for side, (start, end) in enumerate(edges):
            if not doors[side]:
                pygame.draw.line(surface, MUTED, start, end, 2)
            elif side in (0, 2):
                pygame.draw.line(surface, MUTED, start, (cx - width // 2 - 2, start[1]), 2)
                pygame.draw.line(surface, MUTED, (cx + width // 2 + 2, start[1]), end, 2)
            else:
                pygame.draw.line(surface, MUTED, start, (start[0], cy - width // 2 - 2), 2)
                pygame.draw.line(surface, MUTED, (start[0], cy + width // 2 + 2), end, 2)

    def draw(self, surface, session: BuildSession, hovered_pos, message: str):
        surface.fill(BACKGROUND)
        self.text(surface, "DUNGEON ARCHITECT", (28, 22), font=self.title_font)
        self.text(surface, "Plan the rooms. Shape the path.", (30, 58), MUTED, self.small_font)
        resources = session.resources
        self.text(surface, f"HP {resources.hp} / {resources.hp_max}", (354, 26),
                  RED if session.hp_depleted else TEXT)
        limit = f" / {resources.supplies_max}" if resources.supplies_max is not None else ""
        self.text(surface, f"Supplies {resources.supplies}{limit}", (354, 53), GOLD)
        seed_label = self.fit_text(f"Seed {session.seed}", RESTART_RECT.left - 626 - 12)
        self.text(surface, seed_label, (626, 35), MUTED)
        self.button(surface, RESTART_RECT, "Restart  [N]")
        pygame.draw.rect(surface, PANEL, (28, 86, 566, 562), border_radius=12)
        rooms = sum(tile is not None for row in session.board for tile in row)
        self.text(surface, f"YOUR DUNGEON    {rooms} / 49 rooms", (48, 94), MUTED, self.small_font)
        self.text(surface, "YOUR ROOM CARDS", (626, 86), MUTED, self.small_font)
        legal = session.legal_cells()
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                pos = (row, col)
                rect = cell_rect(pos).inflate(-4, -4)
                fits = pos in legal
                pygame.draw.rect(surface, (28, 65, 62) if fits else CELL, rect, border_radius=7)
                pygame.draw.rect(surface, TEAL if fits else LINE, rect, width=1, border_radius=7)
                tile = session.board[row][col]
                if tile is not None:
                    self.room(surface, rect, tile.doors, (127, 166, 171) if tile.kind == "start" else TEAL)
                    if tile.kind == "start":
                        self.text(surface, "S", (rect.left + 7, rect.top + 5), GOLD, self.small_font)
                    elif tile.event_category:
                        pygame.draw.circle(surface, EVENT_COLORS.get(tile.event_category, MUTED),
                                           (rect.right - 9, rect.bottom - 9), 3)
                elif not fits:
                    pygame.draw.circle(surface, LINE, rect.center, 2)
        for index in range(BOARD_SIZE):
            self.text(surface, chr(ord('A') + index),
                      (BOARD_RECT.left + index * CELL_SIZE + 30, 108), MUTED, self.small_font)
            self.text(surface, str(index + 1), (42, BOARD_RECT.top + index * CELL_SIZE + 28),
                      MUTED, self.small_font)
        if hovered_pos is not None:
            occupied = session.board[hovered_pos[0]][hovered_pos[1]] is not None
            walking = occupied and hovered_pos != session.player_pos
            ok, reason = (session.movement_preview(hovered_pos) if walking else session.preview(hovered_pos))
            rect = cell_rect(hovered_pos).inflate(-4, -4)
            card = session.selected_card
            if card is not None and session.board[hovered_pos[0]][hovered_pos[1]] is None:
                self.room(surface, rect, card.doors, TEAL if ok else RED)
            border = (TEAL if ok else RED) if card is not None or walking else MUTED
            pygame.draw.rect(surface, border, rect, width=3, border_radius=7)
        else:
            reason = "no_normal_placement" if session.blocked else "no_card_selected"
        player_center = cell_rect(session.player_pos).center
        pygame.draw.circle(surface, BACKGROUND, player_center, 8)
        pygame.draw.circle(surface, GOLD, player_center, 5)

        for index, card in enumerate(session.draw_result.cards):
            rect = CARD_RECTS[index]
            selected = session.selected_index == index
            pygame.draw.rect(surface, PANEL, rect, border_radius=10)
            pygame.draw.rect(surface, GOLD if selected else LINE, rect, width=2, border_radius=10)
            shown = session.card_at(index)
            self.room(surface, pygame.Rect(rect.x + 12, rect.y + 26, 92, 92), shown.doors)
            self.text(surface, ROOM_NAMES.get(card.kind, card.kind.replace('_', ' ').title()),
                      (rect.x + 122, rect.y + 22), font=self.heading_font)
            category_color = EVENT_COLORS.get(card.event_category, MUTED)
            self.text(surface, card.event_category.title() + " preview", (rect.x + 122, rect.y + 53), category_color)
            playable = index in session.draw_result.legal_card_indices
            self.text(surface, "Fits in some rotation" if playable else "No fit on this map",
                      (rect.x + 122, rect.y + 81), TEAL if playable else MUTED, self.small_font)
            self.text(surface, f"Rotation {session.rotations[index] * 90} deg",
                      (rect.x + 122, rect.y + 108), MUTED, self.small_font)
            self.text(surface, str(index + 1), (rect.right - 25, rect.y + 15), GOLD if selected else MUTED)

        if session.blocked:
            rect = pygame.Rect(626, 112, 442, 456)
            pygame.draw.rect(surface, PANEL, rect, border_radius=10)
            pygame.draw.rect(surface, RED, rect, width=2, border_radius=10)
            self.text(surface, "No normal placement", (650, 270), RED, self.heading_font)
            self.wrapped_text(surface, "No room shape fits your open exits. You can still walk through built rooms or restart.",
                              pygame.Rect(650, 312, 390, 60), MUTED)

        self.button(surface, ROTATE_RECT, "Rotate  [R]", session.selected_card is not None)
        self.text(surface, "Q rotates counterclockwise", (810, 607), MUTED, self.small_font)
        pygame.draw.rect(surface, PANEL, EVENT_RECT, border_radius=8)
        notification = session.current_event
        if notification is not None:
            color = EVENT_COLORS.get(notification.category, MUTED)
            title = f"LAST EVENT: {notification.category.title()} at {cell_label(notification.pos)}"
            self.text(surface, title, (638, 651), color, self.small_font)
            self.text(surface, self.fit_text(notification.message, 418), (638, 669))
            deltas = []
            if notification.hp_delta:
                deltas.append(f"HP {notification.hp_delta:+d}")
            if notification.supplies_delta:
                deltas.append(f"Supplies {notification.supplies_delta:+d}")
            change = "  |  ".join(deltas) or "No resource change (unchanged or at a limit)"
            self.text(surface, change, (638, 691),
                      RED if notification.hp_delta < 0 or notification.supplies_delta < 0 else TEAL,
                      self.small_font)
        else:
            self.text(surface, "Enter a new room to discover its event.", (638, 663), MUTED)
        feedback = message
        if hovered_pos is not None and walking:
            feedback = movement_message(reason)
        elif hovered_pos is not None and session.selected_card is not None:
            feedback = placement_message(reason)
        if session.blocked and hovered_pos is None:
            feedback = placement_message("no_normal_placement")
        if session.hp_depleted:
            feedback = "HP depleted (0). Press N to restart."
        pygame.draw.rect(surface, PANEL, (28, 660, 566, 48), border_radius=8)
        self.wrapped_text(surface, feedback, pygame.Rect(40, 665, 540, 44), RED if session.blocked else TEXT)
        self.text(surface, "1 / 2 / 3 Select   R / Q Rotate   Click Build / Walk   Arrows / WASD Walk   N Restart   Esc Quit",
                  (30, 719), MUTED, self.small_font)
