"""Room/map/card drawing, resource HUD and first-entry event feedback."""

import re
from pathlib import Path

import pygame

from engine.game import BuildSession
from engine.models import BOARD_SIZE
from engine.placement import frontier_cells, reachable_rooms


WINDOW_SIZE = (1100, 740)
CELL_SIZE = 72
BOARD_RECT = pygame.Rect(60, 124, CELL_SIZE * BOARD_SIZE, CELL_SIZE * BOARD_SIZE)
CARD_RECTS = tuple(pygame.Rect(626, 112 + index * 156, 442, 144) for index in range(3))
RESTART_RECT = pygame.Rect(922, 24, 146, 40)
HELP_RECT = pygame.Rect(800, 24, 110, 40)
ROTATE_RECT = pygame.Rect(626, 594, 170, 40)
EVENT_RECT = pygame.Rect(626, 646, 442, 62)
SEAL_RECT = pygame.Rect(806, 584, 126, 32)
CHISEL_RECT = pygame.Rect(942, 584, 126, 32)
END_RESTART_RECT = pygame.Rect(450, 422, 200, 44)

BACKGROUND = (12, 20, 38)
PANEL = (36, 51, 73)
LINE = (56, 76, 101)
TEXT = (216, 229, 239)
MUTED = (163, 186, 206)
TEAL = (76, 171, 183)
GOLD = (255, 230, 173)
RED = (229, 113, 119)
PURPLE = (161, 151, 225)
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


def tool_message(reason: str) -> str:
    return {
        "ok": "Valid tool action. Click to apply.",
        "insufficient_supplies": "Not enough Supplies for this tool.",
        "usage_limit": "This tool has no uses remaining.",
        "tool_exhausted": "This tool has no uses remaining.",
        "tool_limit_reached": "This tool has no uses remaining.",
        "invalid_direction": "Select a north, east, south or west door.",
        "not_a_door": "Door Seal needs an existing doorway.",
        "no_entrance": "Keep at least one matching entrance to the new room.",
        "room_locked": "A locked room cannot be opened with the chisel.",
        "locked_room": "A locked room cannot be opened with the chisel.",
        "not_adjacent": "Choose one adjacent existing room for the chisel.",
        "no_room": "The chisel joins two existing rooms across a shared wall.",
        "already_connected": "These rooms already have matching doors.",
        "invalid_position": "Choose a room inside the map.",
        "not_wall_pair": "The chisel needs a wall on both sides of the shared edge.",
        "walls_not_matching": "The chisel needs a wall on both sides of the shared edge.",
        "source_unreachable": "Walk to a connected source room before using the chisel.",
        "unreachable_source": "Walk to a connected source room before using the chisel.",
        "game_over": "This run has ended. Restart to play again.",
    }.get(reason, placement_message(reason))


class GameRenderer:
    def __init__(self):
        self.title_font = pygame.font.Font(None, 34)
        self.heading_font = pygame.font.Font(None, 26)
        self.font = pygame.font.Font(None, 22)
        self.small_font = pygame.font.Font(None, 18)
        room_dir = Path(__file__).resolve().parents[1] / "assets" / "rooms"
        pavement = pygame.image.load(room_dir.parent / "board" / "ruin-pavement.png")
        self.board_floor = pygame.transform.smoothscale(pavement, BOARD_RECT.size)
        # Engrave the grid into the continuous paving so cracks cross cell boundaries.
        seams = pygame.Surface(BOARD_RECT.size, pygame.SRCALPHA)
        for offset in range(0, BOARD_RECT.width, CELL_SIZE):
            pygame.draw.line(seams, (9, 15, 18, 155), (offset, 0), (offset, BOARD_RECT.height))
            pygame.draw.line(seams, (9, 15, 18, 155), (0, offset), (BOARD_RECT.width, offset))
        self.board_floor.blit(seams, (0, 0))
        self.legal_tint = pygame.Surface((CELL_SIZE - 4, CELL_SIZE - 4), pygame.SRCALPHA)
        self.legal_tint.fill((*TEAL, 45))
        self.room_tiles = {}
        self.card_tiles = {}
        self.objects = {path.stem: pygame.image.load(path)
                        for path in (room_dir.parent / "objects").glob("*.png")}
        for path in room_dir.glob("*-72.png"):
            name, directions, _ = path.stem.rsplit("-", 2)
            doors = tuple(side in directions for side in "nesw")
            sprite = pygame.image.load(path)
            if name == "sealed" or (name in ROOM_NAMES and name != "start"):
                self.room_tiles[doors] = sprite
                self.card_tiles[doors] = pygame.transform.smoothscale(sprite, (92, 92))
            else:
                self.room_tiles[name, doors] = sprite

    def tile_art(self, surface, rect, doors, color=TEAL, *, special=None, card=False):
        tiles = self.card_tiles if card else self.room_tiles
        sprite = tiles.get(doors if special is None else (special, doors))
        if sprite is None:
            # Keep a schematic for custom layouts without corresponding artwork.
            self.room(surface, rect, doors, color)
        else:
            surface.blit(sprite, sprite.get_rect(center=rect.center))

    def text(self, surface, message, pos, color=TEXT, font=None):
        surface.blit((font or self.font).render(message, True, color), pos)

    def fit_text(self, message: str, width: int, font=None) -> str:
        """Shorten a display label without changing its underlying value."""
        font = font or self.font
        if font.size(message)[0] <= width:
            return message
        suffix = "..."
        if font.size(suffix)[0] > width:
            return ""
        low, high = 0, len(message)
        while low < high:
            middle = (low + high + 1) // 2
            if font.size(message[:middle] + suffix)[0] <= width:
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

    def button(self, surface, rect, label, enabled=True, icon=None):
        pygame.draw.rect(surface, (43, 62, 85) if enabled else PANEL, rect, border_radius=8)
        pygame.draw.rect(surface, LINE, rect, width=1, border_radius=8)
        label_surface = self.font.render(label, True, TEXT if enabled else MUTED)
        label_rect = label_surface.get_rect(center=rect.center)
        if icon is not None:
            group_width = icon.get_width() + 5 + label_rect.width
            left = rect.centerx - group_width // 2
            surface.blit(icon, icon.get_rect(midleft=(left, rect.centery)))
            label_rect.left = left + icon.get_width() + 5
        surface.blit(label_surface, label_rect)

    def status_chip(self, surface, rect, label, value, color):
        pygame.draw.rect(surface, (25, 38, 57), rect, border_radius=8)
        pygame.draw.rect(surface, LINE, rect, width=1, border_radius=8)
        pygame.draw.circle(surface, color, (rect.left + 15, rect.centery), 5)
        self.text(surface, label, (rect.left + 27, rect.top + 7), MUTED, self.small_font)
        value_surface = self.heading_font.render(value, True, TEXT)
        self.text(surface, value, (rect.right - 10 - value_surface.get_width(), rect.top + 11),
                  TEXT, self.heading_font)

    def objective_chip(self, surface, rect, label, state, color):
        fill = tuple(max(0, component - 12) for component in PANEL)
        pygame.draw.rect(surface, fill, rect, border_radius=7)
        pygame.draw.rect(surface, color, rect, width=1, border_radius=7)
        pygame.draw.circle(surface, color, (rect.left + 10, rect.centery), 3)
        self.text(surface, label, (rect.left + 18, rect.top + 3), TEXT, self.small_font)
        state_surface = self.small_font.render(state, True, color)
        self.text(surface, state, (rect.right - 7 - state_surface.get_width(), rect.top + 3),
                  color, self.small_font)

    def help_overlay(self, surface):
        shade = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)
        shade.fill((4, 9, 18, 220))
        surface.blit(shade, (0, 0))
        panel = pygame.Rect(130, 78, 840, 584)
        pygame.draw.rect(surface, (20, 31, 48), panel, border_radius=14)
        pygame.draw.rect(surface, TEAL, panel, width=2, border_radius=14)
        self.text(surface, "FIELD GUIDE", (174, 112), GOLD, self.title_font)
        self.text(surface, "Activate both altars, then enter the opened core.",
                  (174, 153), TEXT)
        sections = (
            ("1  BUILD", "Choose card 1 / 2 / 3. Rotate with R or Q. Click a teal cell."),
            ("2  EXPLORE", "Use arrows, WASD, or click an adjacent connected room. Backtracking is free."),
            ("3  READ THE MAP", "Silver paths connect through open edges. A bright outline marks a valid action."),
            ("4  USE TOOLS", "Seal [F] closes one door before building. Chisel [C] opens a shared wall."),
        )
        for index, (heading, description) in enumerate(sections):
            top = 204 + index * 78
            badge = pygame.Rect(174, top, 142, 46)
            pygame.draw.rect(surface, (34, 51, 72), badge, border_radius=8)
            pygame.draw.rect(surface, LINE, badge, width=1, border_radius=8)
            self.text(surface, heading, (badge.left + 14, badge.top + 13), GOLD, self.small_font)
            self.wrapped_text(surface, description, pygame.Rect(342, top + 3, 550, 48), MUTED)
        pygame.draw.line(surface, LINE, (174, 526), (926, 526))
        legend = ((TEAL, "Legal build / active core"), (GOLD, "You / selected action"),
                  (PURPLE, "Inactive altar"), (RED, "Danger / blocked"))
        for index, (color, label) in enumerate(legend):
            left = 178 + (index % 2) * 374
            top = 550 + (index // 2) * 34
            pygame.draw.circle(surface, color, (left, top + 8), 5)
            self.text(surface, label, (left + 14, top), MUTED, self.small_font)
        self.text(surface, "Press H, ? or click Help to close", (350, 624), TEXT, self.small_font)

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

    def draw(self, surface, session: BuildSession, hovered_pos, message: str, *,
             seal_direction: int | None = None, chisel_mode: bool = False,
             help_open: bool = False):
        mvp = hasattr(session, "level")
        terminal = getattr(session, "status", "PLAYING") in ("WON", "LOST")
        if terminal:
            hovered_pos = None
            seal_direction = None
            chisel_mode = False
        surface.fill(BACKGROUND)
        self.text(surface, "DUNGEON ARCHITECT", (28, 22), font=self.title_font)
        self.text(surface, "Plan the rooms. Shape the path.", (30, 58), MUTED, self.small_font)
        resources = session.resources
        self.status_chip(surface, pygame.Rect(332, 22, 126, 42), "HP",
                         f"{resources.hp}/{resources.hp_max}", RED if session.hp_depleted else TEAL)
        limit = f" / {resources.supplies_max}" if resources.supplies_max is not None else ""
        self.status_chip(surface, pygame.Rect(470, 22, 144, 42), "SUPPLIES",
                         f"{resources.supplies}{limit.replace(' ', '')}", GOLD)
        seed_label = self.fit_text(f"Seed {session.seed}", HELP_RECT.left - 626 - 12)
        self.text(surface, seed_label, (626, 35), MUTED)
        self.button(surface, HELP_RECT, "Help  [H]")
        self.button(surface, RESTART_RECT, "Restart  [N]")
        pygame.draw.rect(surface, PANEL, (28, 86, 566, 562), border_radius=12)
        rooms = sum(tile is not None for row in session.board for tile in row)
        self.text(surface, f"MAP  |  {rooms} / 49 ROOMS", (48, 94), MUTED, self.small_font)
        self.text(surface, "1  CHOOSE A ROOM", (626, 86), MUTED, self.small_font)
        legal = (session.legal_cells_with_seal(seal_direction) if seal_direction is not None
                 else session.legal_cells())
        frontier = frontier_cells(session.board, reachable_rooms(session.board, session.player_pos)) if mvp else set()
        altar_positions = {altar.pos: index + 1 for index, altar in enumerate(session.level.altars)} if mvp else {}
        surface.blit(self.board_floor, BOARD_RECT)
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                pos = (row, col)
                rect = cell_rect(pos).inflate(-4, -4)
                fits = pos in legal
                tile = session.board[row][col]
                if tile is not None:
                    color = (127, 166, 171) if tile.kind == "start" else TEAL
                    special = "start" if tile.kind == "start" else None
                    if pos in altar_positions:
                        color = GOLD if tile.kind in session.activated_altars else PURPLE
                        state = "activated" if tile.kind in session.activated_altars else "idle"
                        altar = tile.kind if tile.kind in ("altar_a", "altar_b") else "altar_a"
                        special = f"{altar}-{state}"
                    elif mvp and pos == session.level.core.pos:
                        color = GOLD if session.core_unlocked else RED
                        special = "core-unlocked" if session.core_unlocked else "core-locked"
                    self.tile_art(surface, rect, tile.doors, color, special=special)
                    if tile.kind == "start":
                        self.text(surface, "S", (rect.left + 7, rect.top + 5), GOLD, self.small_font)
                    elif pos in altar_positions:
                        self.text(surface, f"A{altar_positions[pos]}", (rect.left + 7, rect.top + 5), color, self.small_font)
                    elif mvp and pos == session.level.core.pos:
                        self.text(surface, "C+" if session.core_unlocked else "C-",
                                  (rect.left + 7, rect.top + 5), color, self.small_font)
                    elif tile.event_category in ("supply", "danger"):
                        icon = self.objects[tile.event_category]
                        center = (rect.centerx + 11, rect.centery + 5) if pos == session.player_pos else rect.center
                        surface.blit(icon, icon.get_rect(center=center))
                    elif tile.event_category and tile.event_category != "neutral":
                        pygame.draw.circle(surface, MUTED, (rect.right - 9, rect.bottom - 9), 3)
                elif fits:
                    surface.blit(self.legal_tint, rect)
                    pygame.draw.rect(surface, TEAL, rect, width=1)
                elif pos in frontier:
                    pygame.draw.circle(surface, TEAL, rect.center, 3)
                if chisel_mode and tile is not None and session.chisel_preview(session.player_pos, pos)[0]:
                    pygame.draw.rect(surface, GOLD, rect, width=2, border_radius=7)
        for index in range(BOARD_SIZE):
            self.text(surface, chr(ord('A') + index),
                      (BOARD_RECT.left + index * CELL_SIZE + 30, 108), MUTED, self.small_font)
            self.text(surface, str(index + 1), (42, BOARD_RECT.top + index * CELL_SIZE + 28),
                      MUTED, self.small_font)
        if mvp:
            for index, altar in enumerate(session.level.altars[:2]):
                active = altar.kind in session.activated_altars
                self.objective_chip(surface, pygame.Rect(48 + index * 120, 628, 112, 20),
                                    f"A{index + 1} {cell_label(altar.pos)}",
                                    "ACTIVE" if active else "IDLE", GOLD if active else PURPLE)
            self.objective_chip(surface, pygame.Rect(288, 628, 176, 20),
                                f"CORE {cell_label(session.level.core.pos)}",
                                "OPEN" if session.core_unlocked else "LOCKED",
                                TEAL if session.core_unlocked else RED)
        if hovered_pos is not None:
            occupied = session.board[hovered_pos[0]][hovered_pos[1]] is not None
            walking = occupied and hovered_pos != session.player_pos
            if chisel_mode:
                ok, reason = session.chisel_preview(session.player_pos, hovered_pos)
            elif walking:
                ok, reason = session.movement_preview(hovered_pos)
            elif seal_direction is not None:
                ok, reason = session.preview_with_seal(hovered_pos, seal_direction)
            else:
                ok, reason = session.preview(hovered_pos)
            rect = cell_rect(hovered_pos).inflate(-4, -4)
            card = session.selected_card
            if card is not None and not chisel_mode and session.board[hovered_pos[0]][hovered_pos[1]] is None:
                doors = tuple(False if side == seal_direction else value for side, value in enumerate(card.doors))
                self.tile_art(surface, rect, doors, TEAL if ok else RED)
            border = (TEAL if ok else RED) if card is not None or walking or chisel_mode else MUTED
            pygame.draw.rect(surface, border, rect, width=3, border_radius=7)
        else:
            reason = "no_normal_placement" if session.blocked else "no_card_selected"
        player_center = cell_rect(session.player_pos).center
        explorer = self.objects["explorer"]
        surface.blit(explorer, explorer.get_rect(center=player_center))

        for index, card in enumerate(session.draw_result.cards):
            rect = CARD_RECTS[index]
            selected = session.selected_index == index
            pygame.draw.rect(surface, PANEL, rect, border_radius=10)
            pygame.draw.rect(surface, GOLD if selected else LINE, rect, width=2, border_radius=10)
            shown = session.card_at(index)
            shown_doors = (tuple(False if side == seal_direction else value for side, value in enumerate(shown.doors))
                           if selected else shown.doors)
            self.tile_art(surface, pygame.Rect(rect.x + 12, rect.y + 26, 92, 92), shown_doors, card=True)
            self.text(surface, ROOM_NAMES.get(card.kind, card.kind.replace('_', ' ').title()),
                      (rect.x + 122, rect.y + 22), font=self.heading_font)
            category_color = EVENT_COLORS.get(card.event_category, MUTED)
            self.text(surface, card.event_category.title() + " preview", (rect.x + 122, rect.y + 53), category_color)
            if selected and seal_direction is not None:
                playable = bool(legal)
                fit_message = "Seal fits this rotation" if playable else "No fit with this seal"
            else:
                playable = index in session.draw_result.legal_card_indices
                fit_message = "Fits in some rotation" if playable else "No fit on this map"
            self.text(surface, fit_message,
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

        self.button(surface, ROTATE_RECT, "Rotate  [R]", session.selected_card is not None and not terminal)
        if mvp:
            seal_label = "Seal [F]" if seal_direction is None else f"Seal {'NESW'[seal_direction]} [F]"
            self.button(surface, SEAL_RECT, seal_label, session.selected_card is not None and not terminal,
                        self.objects["seal"])
            self.button(surface, CHISEL_RECT, "Chisel [C]", not terminal, self.objects["chisel"])
            if seal_direction is not None:
                pygame.draw.rect(surface, GOLD, SEAL_RECT, width=2, border_radius=8)
            if chisel_mode:
                pygame.draw.rect(surface, GOLD, CHISEL_RECT, width=2, border_radius=8)
            seal = session.tools.door_seal
            chisel = session.tools.emergency_chisel
            remaining_seal = seal.max_uses_per_game - session.tool_uses["door_seal"]
            remaining_chisel = chisel.max_uses_per_game - session.tool_uses["emergency_chisel"]
            self.text(surface, f"Seal {seal.cost_supplies}S / {remaining_seal} left   Chisel {chisel.cost_supplies}S / {remaining_chisel} left",
                      (806, 620), MUTED, self.small_font)
        else:
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
        if hovered_pos is not None and chisel_mode:
            feedback = tool_message(reason)
        elif hovered_pos is not None and walking:
            feedback = movement_message(reason)
        elif hovered_pos is not None and session.selected_card is not None:
            feedback = tool_message(reason) if seal_direction is not None else placement_message(reason)
        if session.blocked and hovered_pos is None and not chisel_mode:
            feedback = ("No normal room fits. You can walk, use a tool or restart." if mvp
                        else placement_message("no_normal_placement"))
        if session.hp_depleted and not mvp:
            feedback = "HP depleted (0). Press N to restart."
        pygame.draw.rect(surface, PANEL, (28, 660, 566, 48), border_radius=8)
        self.wrapped_text(surface, feedback, pygame.Rect(40, 665, 540, 44), RED if session.blocked else TEXT)
        footer = ("1/2/3 Select  R/Q Rotate  Click Build/Walk  Arrows/WASD Walk  F Seal  C Chisel  H Help  N Restart  Esc Quit"
                  if mvp else "1 / 2 / 3 Select   R / Q Rotate   Click Build / Walk   Arrows / WASD Walk   N Restart   Esc Quit")
        self.text(surface, footer,
                  (30, 719), MUTED, self.small_font)
        if terminal:
            shade = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)
            shade.fill((5, 11, 17, 205))
            surface.blit(shade, (0, 0))
            panel = pygame.Rect(170, 220, 760, 300)
            pygame.draw.rect(surface, PANEL, panel, border_radius=14)
            won = session.status == "WON"
            color = GOLD if won else RED
            pygame.draw.rect(surface, color, panel, width=2, border_radius=14)
            self.text(surface, "VICTORY" if won else "DEFEAT", (220, 252), color, self.title_font)
            explanation = ("All altars are active. You reached the unlocked core."
                           if won else "Your HP reached zero. Try a different route or use your tools earlier.")
            self.wrapped_text(surface, explanation, pygame.Rect(220, 312, 660, 60))
            self.text(surface, f"Rooms built: {session.build_turn}   HP: {resources.hp}   Supplies: {resources.supplies}",
                      (220, 382), MUTED)
            self.button(surface, END_RESTART_RECT, "Restart  [N]")
            self.text(surface, "Esc closes the game", (468, 482), MUTED, self.small_font)
        if help_open:
            self.help_overlay(surface)
