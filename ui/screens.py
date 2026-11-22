"""Room/map/card drawing, resource HUD and first-entry event feedback."""

import re
from pathlib import Path

import pygame

from engine.game import BuildSession
from engine.messages import Message
from ui.locales import translate
from engine.models import BOARD_SIZE
from engine.placement import frontier_cells, loops_closed_by_room, reachable_rooms


WINDOW_SIZE = (1280, 740)
CELL_SIZE = 76
BOARD_RECT = pygame.Rect(240, 120, CELL_SIZE * BOARD_SIZE, CELL_SIZE * BOARD_SIZE)
CARD_RECTS = tuple(pygame.Rect(806, 112 + index * 156, 442, 144) for index in range(3))
RESTART_RECT = pygame.Rect(1102, 24, 146, 40)
HELP_RECT = pygame.Rect(980, 24, 110, 40)
ROTATE_RECT = pygame.Rect(806, 574, 170, 32)
MEDKIT_RECT = pygame.Rect(806, 610, 170, 32)
EVENT_RECT = pygame.Rect(806, 646, 442, 62)
CACHE_RECT = pygame.Rect(592, 667, 182, 34)
SEAL_RECT = pygame.Rect(986, 584, 126, 32)
CHISEL_RECT = pygame.Rect(1122, 584, 126, 32)
END_RESTART_RECT = pygame.Rect(540, 422, 200, 44)
HP_RECT = pygame.Rect(512, 22, 126, 42)
SUPPLIES_RECT = pygame.Rect(650, 22, 144, 42)
EVENT_FEEDBACK_MS = 2400
LOBBY_RECT = pygame.Rect(885, 24, 85, 40)
LANGUAGE_RECT = pygame.Rect(800, 24, 78, 40)
ENTER_RECT = pygame.Rect(704, 372, 294, 54)
GUIDE_RECT = pygame.Rect(704, 442, 294, 42)
EXIT_RECT = pygame.Rect(704, 496, 294, 42)
GUIDE_CLOSE_RECT = pygame.Rect(850, 612, 116, 36)
GUIDE_PREV_RECT = pygame.Rect(264, 612, 132, 36)
GUIDE_NEXT_RECT = pygame.Rect(408, 612, 132, 36)

GUIDE_PAGES = (
    ("First expedition", (
        ("1  BUILD", "Pick a card with 1 / 2 / 3. Rotate clockwise with R or back with Q. Click a green cell to build, enter the room and draw three new cards."),
        ("2  EXPLORE", "Use arrows, WASD or click an adjacent room to walk through matching doors. Walking is free and keeps your hand."),
        ("3  READ THE MAP", "Build from any reachable exit. Doors must meet doors, walls must meet walls, and doors must point inside the map."),
        ("4  USE TOOLS", "Rotate, seal a door or chisel a wall to make room. When hurt, press M to use a medkit: spend 2 supplies to recover 1 HP."),
    )),
    ("Rooms and survival", (
        ("ROOM CARDS", "Dead ends favor supplies. Straights are usually quiet. T junctions often hold danger or loot. Crossroads can hide relics."),
        ("FIRST ENTRY", "A room reveals its event only once. Rations give 1 or 2 supplies. Darts cost 1 HP, falling stone costs 2 HP, and thorns cost 1 supply."),
        ("BARBED CHEST", "Press E or click Open chest to trade 1 HP for up to 2 supplies. Leave it for later if your pack is full or you have only 1 HP."),
        ("ALTARS & CORE", "Walk into both altars in either order. The first gives 1 supply. Enter the unlocked core to win. Reaching zero HP ends the expedition."),
    )),
    ("Tools and loops", (
        ("DOOR SEAL", "Select a card and press F to cycle its open doors. Build to seal the marked door for 1 supply. You have three seals per expedition."),
        ("CHISEL", "Press C and click a built room across a shared wall next to you. Opening the door costs 2 supplies. You can chisel twice per expedition."),
        ("CLOSE A LOOP", "Join two exits that already have a route between them. Build a connecting room or chisel a shortcut to close the loop."),
        ("LOOP REWARD", "Each new independent loop gives 1 supply after the room event or tool cost, up to your pack limit. Walking the loop again earns nothing."),
    )),
)

BACKGROUND = (12, 12, 28)
PANEL = (33, 32, 56)
RECESS = (21, 23, 43)
LINE = (77, 75, 111)
STEEL = (125, 143, 188)
TEXT = (232, 231, 248)
MUTED = (177, 180, 207)
TEAL = (76, 171, 183)
GOLD = (255, 230, 173)
RED = (229, 113, 119)
PURPLE = (161, 151, 225)
BUILD_GREEN = (132, 213, 151)
VINE_SPIRES = (145, 160, 88)
SPRING = (99, 214, 228)
EVENT_COLORS = {"supply": TEAL, "danger": RED, "guard": RED, "neutral": MUTED, "relic": PURPLE, "spring": SPRING}
ROOM_TRAITS = {
    "dead_end": ("Treasure-prone", GOLD),
    "straight": ("Usually safe", TEAL),
    "corner": ("Balanced event", MUTED),
    "t_junction": ("Risk / reward", RED),
    "cross": ("Relic chance", PURPLE),
}
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


def loop_label(notification) -> str:
    count = notification.loops_closed
    amount = notification.loop_supplies
    gain = Message("+{amount} supply" if amount == 1 else "+{amount} supplies", amount=amount) if amount else "pack full"
    return Message("{count} loop  ({gain})" if count == 1 else "{count} loops  ({gain})", count=count, gain=gain)


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
        return Message("Door/wall mismatch on the {side} side.", side=side)
    if reason.startswith("door_faces_outside_board"):
        return Message("The {side} door would face outside the map.", side=side)
    return "This room cannot be placed here."


def movement_message(reason: str) -> str:
    return {
        "rubble": "Vine spires block this cell. Build around them.",
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
        "rubble": "Vine spires block this cell. Build around them.",
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


def stone_frame(surface, rect, fill=PANEL, edge=LINE, cut=6):
    """Inset slab with clipped corners and a single light-catching bevel."""
    r = pygame.Rect(rect)
    l, t, b = r.left, r.top, r.bottom - 1
    right = r.right - 1
    points = [(l + cut, t), (right - cut, t), (right, t + cut), (right, b - cut),
              (right - cut, b), (l + cut, b), (l, b - cut), (l, t + cut)]
    pygame.draw.polygon(surface, fill, points)
    pygame.draw.polygon(surface, edge, points, 1)
    pygame.draw.line(surface, STEEL if edge == LINE else edge, (l + cut, t), (right - cut, t))


class GameRenderer:
    def __init__(self):
        serif = pygame.font.match_font("cinzel,constantia,georgia,dejavuserif")
        self.title_font = pygame.font.Font(serif, 34)
        self.heading_font = pygame.font.Font(None, 26)
        self.font = pygame.font.Font(None, 22)
        self.small_font = pygame.font.Font(None, 18)
        self.language = "en"
        self.english_fonts = self.title_font, self.heading_font, self.font, self.small_font
        font_file = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "DungeonTC-Regular.ttf"
        self.chinese_fonts = tuple(pygame.font.Font(font_file, size) for size in (30, 20, 16, 13))
        room_dir = Path(__file__).resolve().parents[1] / "assets" / "rooms"
        pavement = pygame.image.load(room_dir.parent / "board" / "ruin-pavement.png")
        self.board_floor = pygame.transform.smoothscale(pavement, BOARD_RECT.size)
        self.backdrop = pygame.Surface(WINDOW_SIZE)
        self.backdrop.fill(BACKGROUND)
        masonry = pavement.copy()
        masonry.set_alpha(42)
        for x in range(0, WINDOW_SIZE[0], masonry.get_width()):
            for y in range(0, WINDOW_SIZE[1], masonry.get_height()):
                self.backdrop.blit(masonry, (x, y))
        # A pointed portal and suspended amethyst form the title's seal.
        arch = [(29, 61), (29, 34), (35, 23), (50, 10), (65, 23), (71, 34), (71, 61)]
        pygame.draw.polygon(self.backdrop, RECESS, arch)
        pygame.draw.lines(self.backdrop, STEEL, True, arch, 2)
        pygame.draw.lines(self.backdrop, LINE, False, [(35, 60), (35, 35), (50, 18), (65, 35), (65, 60)])
        pygame.draw.line(self.backdrop, LINE, (50, 18), (50, 33))
        pygame.draw.polygon(self.backdrop, PURPLE, [(50, 30), (57, 42), (50, 54), (43, 42)])
        pygame.draw.polygon(self.backdrop, (97, 84, 155), [(50, 30), (57, 42), (50, 54)])
        face = pygame.font.SysFont("consolas,dejavusansmono", 21, bold=True)
        title = face.render("Dungeon Architect", False, TEXT)
        self.english_title = pygame.transform.scale_by(title, 2)
        self.chinese_title = self.chinese_fonts[0].render("地下城建築師", True, TEXT)
        pygame.draw.line(self.backdrop, LINE, (28, 76), (1248, 76))
        pygame.draw.line(self.backdrop, PURPLE, (28, 76), (72, 76))
        # Engrave the grid into the continuous paving so cracks cross cell boundaries.
        seams = pygame.Surface(BOARD_RECT.size, pygame.SRCALPHA)
        for offset in range(0, BOARD_RECT.width, CELL_SIZE):
            pygame.draw.line(seams, (9, 15, 18, 155), (offset, 0), (offset, BOARD_RECT.height))
            pygame.draw.line(seams, (9, 15, 18, 155), (0, offset), (BOARD_RECT.width, offset))
        self.board_floor.blit(seams, (0, 0))
        self.legal_tint = pygame.Surface((CELL_SIZE - 4, CELL_SIZE - 4), pygame.SRCALPHA)
        self.legal_tint.fill((*BUILD_GREEN, 65))
        self.unknown_mark = self.heading_font.render("?", True, (68, 70, 89))
        self.room_tiles = {}
        self.card_tiles = {}
        self.objects = {path.stem: pygame.image.load(path)
                        for path in (room_dir.parent / "objects").glob("*.png")}
        # Give the obstacle a full-cell stone base and size the visible silhouette to the grid.
        self.vine_tile = self.board_floor.subsurface((0, 0, CELL_SIZE, CELL_SIZE)).copy()
        self.vine_tile.fill((188, 203, 178), special_flags=pygame.BLEND_RGB_MULT)
        spires = self.objects["vine-spires"]
        silhouette = spires.subsurface(spires.get_bounding_rect(min_alpha=64))
        self.vine_tile.blit(pygame.transform.smoothscale(silhouette, self.vine_tile.get_size()), (0, 0))
        self.status_icons = {}
        for name in ("health", "supply"):
            sprite = self.objects[name]
            bounds = sprite.get_bounding_rect()
            size = bounds.fit(pygame.Rect(0, 0, 22, 22)).size
            self.status_icons[name] = pygame.transform.smoothscale(sprite.subsurface(bounds), size)
        for path in room_dir.glob("*-72.png"):
            name, directions, _ = path.stem.rsplit("-", 2)
            doors = tuple(side in directions for side in "nesw")
            sprite = pygame.image.load(path)
            if name == "sealed" or (name in ROOM_NAMES and name != "start"):
                # Expand the central masonry equally on both axes. Crop at the
                # original tile boundary so adjoining exits still meet exactly.
                expanded = pygame.transform.scale_by(sprite, 1.5)
                crop = sprite.get_rect(center=expanded.get_rect().center)
                road = expanded.subsurface(crop).copy()
                self.room_tiles[doors] = road
                self.card_tiles[doors] = pygame.transform.smoothscale(road, (92, 92))
            else:
                self.room_tiles[name, doors] = sprite
        # The landmark stays at native size, with the same wide approaches
        # as its adjacent ordinary rooms visible beneath its perimeter.
        for key, landmark in list(self.room_tiles.items()):
            if len(key) == 2:
                approach = self.room_tiles[key[1]].copy()
                approach.fill((0, 0, 0, 0), approach.get_rect().inflate(-24, -24))
                approach.blit(landmark, (0, 0))
                self.room_tiles[key] = approach
        self.room_tiles = {key: pygame.transform.scale(sprite, (CELL_SIZE, CELL_SIZE))
                           for key, sprite in self.room_tiles.items()}
        self.lobby_backdrop = self.backdrop.copy()
        hall = self.lobby_backdrop
        stone_frame(hall, (138, 134, 1004, 474), RECESS, cut=18)
        # A carved gate on a raised plinth, lit by the two altar stones.
        for inset, fill in ((0, LINE), (9, PANEL), (20, STEEL), (23, BACKGROUND)):
            left, right = 222 + inset, 538 - inset
            top = 173 + inset
            pygame.draw.polygon(hall, fill, [(left, 490), (left, top + 108),
                                (380, top), (right, top + 108), (right, 490)])
        gate = self.objects["core-locked"]
        gate = pygame.transform.scale(gate, (140, 180))
        hall.blit(gate, gate.get_rect(midbottom=(380, 482)))
        for step in range(4):
            stone_frame(hall, (220 - step * 10, 487 + step * 13, 320 + step * 20, 14), cut=3)
        for x in (222, 538):
            lamp = pygame.transform.scale2x(self.objects["altar_a-activated"])
            hall.blit(lamp, lamp.get_rect(midbottom=(x, 488)))
        pygame.draw.line(hall, LINE, (640, 187), (640, 553))

    def toggle_language(self):
        self.language = "zh-TW" if self.language == "en" else "en"
        fonts = self.chinese_fonts if self.language == "zh-TW" else self.english_fonts
        self.title_font, self.heading_font, self.font, self.small_font = fonts
        pygame.display.set_caption(self.t("Dungeon Architect"))

    def t(self, message):
        return translate(message, self.language)

    def language_button(self, surface):
        stone_frame(surface, LANGUAGE_RECT, PANEL, PURPLE)
        label = "繁中 F2" if self.language == "en" else "EN  F2"
        text = self.chinese_fonts[2].render(label, True, TEXT)
        surface.blit(text, text.get_rect(center=LANGUAGE_RECT.center))

    def draw_title(self, surface):
        title = self.english_title if self.language == "en" else self.chinese_title
        surface.blit(title, title.get_rect(midleft=(84, 40)))

    def lobby(self, surface, seed, started, terminal):
        surface.blit(self.lobby_backdrop, (0, 0))
        self.draw_title(surface)
        self.text(surface, "Expedition Hall", (704, 205), TEXT, self.title_font)
        self.wrapped_text(surface, "Activate the altars and enter the sealed core.",
                          pygame.Rect(704, 269, 310, 60), MUTED)
        self.text(surface, self.fit_text(Message("Seed {seed}", seed=seed), ENTER_RECT.width),
                  (ENTER_RECT.x, 336), PURPLE)
        action = "New expedition" if terminal else "Resume expedition" if started else "Enter the ruins"
        self.button(surface, ENTER_RECT, Message("{action}   [Enter]", action=action))
        self.button(surface, GUIDE_RECT, "Field guide   [H]")
        self.button(surface, EXIT_RECT, "Quit   [Esc]")

    def tile_art(self, surface, rect, doors, color=TEAL, *, special=None, card=False):
        tiles = self.card_tiles if card else self.room_tiles
        sprite = tiles.get(doors if special is None else (special, doors))
        if sprite is None:
            # Keep a schematic for custom layouts without corresponding artwork.
            self.room(surface, rect, doors, color)
        else:
            surface.blit(sprite, sprite.get_rect(center=rect.center))

    def terrain_art(self, surface, rect, tile):
        x, y = rect.center
        if tile.kind == "rubble":
            surface.blit(self.vine_tile, self.vine_tile.get_rect(center=rect.center))
        else:
            self.tile_art(surface, rect, tile.doors)
            basin = pygame.Rect(x - 16, y - 11, 32, 22)
            pygame.draw.ellipse(surface, STEEL, basin)
            pygame.draw.ellipse(surface, RECESS, basin.inflate(-4, -4))
            if not tile.event_resolved:
                pygame.draw.ellipse(surface, TEAL, basin.inflate(-8, -9))
                pygame.draw.arc(surface, SPRING, basin.inflate(-13, -13), 0, 3, 2)

    def card_event_odds(self, surface, rect, weights):
        """Show the room template's distribution, shared by every card of its kind."""
        names = {"supply": "Supplies", "danger": "Trap", "neutral": "Quiet", "relic": "Relic"}
        maximum = max(weight for _, weight in weights)
        chances = {name: weight / maximum for name, weight in weights if weight > 0}
        total = sum(chances.values())
        order = [name for name in names if name in chances]
        order.extend(name for name in chances if name not in names)
        if len(order) > 4:
            entries = [(name, chances[name]) for name in order[:3]]
            entries.append((None, sum(chances[name] for name in order[3:])))
        else:
            entries = [(name, chances[name]) for name in order]
        for index, (name, weight) in enumerate(entries):
            x = rect.left + 122 + (index % 2) * 152
            y = rect.top + 70 + (index // 2) * 22
            color = EVENT_COLORS.get(name, MUTED)
            if name in ("supply", "danger"):
                icon = self.objects[name]
                surface.blit(icon, icon.get_rect(center=(x + 8, y)))
            elif name == "relic":
                pygame.draw.polygon(surface, PURPLE, [(x + 8, y - 7), (x + 14, y),
                                                     (x + 8, y + 7), (x + 2, y)])
                pygame.draw.line(surface, TEXT, (x + 8, y - 4), (x + 5, y))
            else:
                pygame.draw.line(surface, color, (x + 3, y), (x + 13, y), 2)
            label = names.get(name, name or "Other")
            self.text(surface, self.fit_text(label, 72, self.small_font), (x + 22, y - 7), TEXT, self.small_font)
            percent = weight / total * 100
            odds = "<1%" if percent < 1 else f"{percent:.0f}%"
            self.text(surface, odds, (x + 138 - self.small_font.size(odds)[0], y - 7), color, self.small_font)

    def text(self, surface, message, pos, color=TEXT, font=None):
        surface.blit((font or self.font).render(self.t(message), True, color), pos)

    def fit_text(self, message: str, width: int, font=None) -> str:
        """Shorten a display label without changing its underlying value."""
        font = font or self.font
        message = self.t(message)
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
        message = self.t(message)
        # Keep Latin words/shortcuts together and allow breaks between Chinese characters.
        tokens = re.findall(r"[A-Za-z0-9_]+|\s+|.", message)
        lines = [""]
        for word in tokens:
            candidate = lines[-1] + word
            if self.font.size(candidate)[0] > rect.width and lines[-1]:
                lines.append(word.lstrip())
            else:
                lines[-1] = candidate
        for index, line in enumerate(lines[:max(1, (rect.height + 3) // 23)]):
            self.text(surface, line.rstrip(), (rect.x, rect.y + index * 23), color)

    def button(self, surface, rect, label, enabled=True, icon=None):
        stone_frame(surface, rect, (46, 44, 74) if enabled else RECESS)
        label_surface = self.font.render(self.t(label), True, TEXT if enabled else MUTED)
        label_rect = label_surface.get_rect(center=rect.center)
        if icon is not None:
            group_width = icon.get_width() + 5 + label_rect.width
            left = rect.centerx - group_width // 2
            surface.blit(icon, icon.get_rect(midleft=(left, rect.centery)))
            label_rect.left = left + icon.get_width() + 5
        surface.blit(label_surface, label_rect)

    def status_chip(self, surface, rect, label, value, color, icon=None):
        stone_frame(surface, rect, RECESS)
        if icon is None:
            pygame.draw.circle(surface, color, (rect.left + 15, rect.centery), 5)
        else:
            surface.blit(icon, icon.get_rect(center=(rect.left + 15, rect.centery)))
        self.text(surface, label, (rect.left + 31, rect.top + 7), MUTED, self.small_font)
        value_surface = self.heading_font.render(value, True, TEXT)
        self.text(surface, value, (rect.right - 10 - value_surface.get_width(), rect.top + 11),
                  TEXT, self.heading_font)

    def objective_chip(self, surface, rect, label, state, color):
        fill = tuple(max(0, component - 12) for component in PANEL)
        pygame.draw.rect(surface, fill, rect, border_radius=7)
        pygame.draw.rect(surface, color, rect, width=1, border_radius=7)
        pygame.draw.circle(surface, color, (rect.left + 10, rect.centery), 3)
        self.text(surface, label, (rect.left + 18, rect.top + 3), TEXT, self.small_font)
        state_surface = self.small_font.render(self.t(state), True, color)
        self.text(surface, state, (rect.right - 7 - state_surface.get_width(), rect.top + 3),
                  color, self.small_font)

    def low_health_warning(self, surface, session):
        critical = session.resources.hp == 1
        accent = (255, 117, 122) if critical else (245, 185, 102)
        period = 1200 if critical else 2000
        phase = pygame.time.get_ticks() % period / period
        pulse = 1 - abs(2 * phase - 1)
        border = pygame.Color(RECESS).lerp(accent, 0.45 + 0.55 * pulse)
        pygame.draw.rect(surface, border, HP_RECT.inflate(4, 4), 3, border_radius=7)

        well = next(((r, c) for r, row in enumerate(session.board) for c, tile in enumerate(row)
                     if tile and tile.kind == "spring" and not tile.event_resolved), None)
        hint = Message("Well {cell} heals 1 HP", cell=cell_label(well)) if well else "Watch for traps"
        if well is None and hasattr(session, "medkit_preview") and session.medkit_preview()[0]:
            hint = "Medkit [M] heals 1 HP"
        panel = pygame.Rect(945, 80, 303, 28)
        stone_frame(surface, panel, (47, 30, 39), accent)
        self.text(surface, "1 HP LEFT" if critical else "LOW HP", (955, 85), accent, self.small_font)
        self.text(surface, hint, (1048, 85), TEXT, self.small_font)

    def event_toast(self, surface, notification, age_ms):
        """Draw transient event flash, source marker and actual resource changes."""
        color = EVENT_COLORS.get(notification.category, MUTED)
        flash = max(0, 42 - age_ms * 42 // 500) if age_ms < 500 else 0
        if flash:
            glow_width = 2 + flash // 14
            pygame.draw.rect(surface, color, BOARD_RECT.inflate(4, 4),
                             width=glow_width, border_radius=12)

        source = cell_rect(notification.pos).inflate(-4, -4)
        pulse = 2 + (age_ms // 110) % 3
        pygame.draw.rect(surface, color, source.inflate(pulse, pulse), width=3, border_radius=8)

        fade_start = 1750
        alpha = 255 if age_ms <= fade_start else max(
            0, 255 * (EVENT_FEEDBACK_MS - age_ms) // (EVENT_FEEDBACK_MS - fade_start)
        )
        rise = 0 if age_ms <= fade_start else (age_ms - fade_start) // 45
        toast = pygame.Surface((420, 82), pygame.SRCALPHA)
        stone_frame(toast, toast.get_rect(), (*PANEL, 246), color)

        category = notification.category.replace("_", " ").upper()
        self.text(toast, category, (18, 11), color, self.small_font)
        self.text(toast, self.fit_text(notification.message, 380), (18, 31), TEXT, self.font)
        left = 18
        for name, delta, unit in (("health", notification.hp_delta, "HP"),
                                  ("supply", notification.supplies_delta, "Supplies")):
            if delta:
                icon = self.status_icons[name]
                icon_rect = icon.get_rect(midleft=(left, 67))
                toast.blit(icon, icon_rect)
                label = self.t(Message("{delta:+d} {unit}", delta=delta, unit=unit))
                area = pygame.Rect((0, 0), self.small_font.size(label))
                area.midleft = (icon_rect.right + 5, 67)
                self.text(toast, label, area.topleft, TEAL if delta > 0 else RED, self.small_font)
                left = area.right + 16
        if notification.loops_closed:
            self.text(toast, loop_label(notification), (left, 58), GOLD, self.small_font)
        elif not notification.hp_delta and not notification.supplies_delta:
            self.text(toast, "No resource change", (18, 58), MUTED, self.small_font)
        toast.set_alpha(alpha)
        surface.blit(toast, (BOARD_RECT.centerx - toast.get_width() // 2, 142 - rise))

    def help_overlay(self, surface, page=0):
        shade = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)
        shade.fill((4, 9, 18, 220))
        surface.blit(shade, (0, 0))
        panel = pygame.Rect(220, 78, 840, 584)
        stone_frame(surface, panel, RECESS, PURPLE, cut=16)
        title, sections = GUIDE_PAGES[page]
        pygame.draw.line(surface, LINE, (264, 185), (1016, 185))
        self.text(surface, "FIELD GUIDE", (264, 101), TEXT, self.title_font)
        self.text(surface, title, (264, 153), GOLD, self.heading_font)
        self.text(surface, f"{page + 1} / {len(GUIDE_PAGES)}", (950, 153), MUTED)
        for index, (heading, description) in enumerate(sections):
            top = 204 + index * 78
            badge = pygame.Rect(264, top, 142, 46)
            stone_frame(surface, badge)
            self.text(surface, heading, (badge.left + 14, badge.top + 13), PURPLE, self.small_font)
            self.wrapped_text(surface, description, pygame.Rect(432, top + 3, 584, 66), TEXT)
        pygame.draw.line(surface, LINE, (264, 522), (1016, 522))
        if page == 0:
            legend = ((BUILD_GREEN, "Legal build"), (GOLD, "You / selected action"),
                      (PURPLE, "Inactive altar"), (RED, "Danger / blocked"))
            for index, (color, label) in enumerate(legend):
                x = 271 + index * 189
                pygame.draw.circle(surface, color, (x, 545), 5)
                self.text(surface, label, (x + 12, 538), MUTED, self.small_font)
            self.wrapped_text(surface, "The first altar wakes the guard. Every 2 builds it follows its arrow. Leave the marked cell before building. Contact costs 1 HP and returns the guard to Start.",
                              pygame.Rect(264, 560, 750, 60), MUTED)
        elif page == 1:
            self.wrapped_text(surface, "Vine spires block building and travel. Connect a path to a blue well and walk in to heal 1 HP once. At full health the well still runs dry.",
                              pygame.Rect(264, 548, 730, 50), MUTED)
        else:
            corners = [(282, 541), (326, 541), (326, 581), (282, 581)]
            pygame.draw.lines(surface, STEEL, False, corners, 3)
            pygame.draw.line(surface, GOLD, corners[-1], corners[0], 3)
            for point in corners:
                node = pygame.Rect(point[0] - 6, point[1] - 6, 12, 12)
                pygame.draw.rect(surface, PANEL, node)
                pygame.draw.rect(surface, STEEL, node, 1)
            self.wrapped_text(surface, "Close the gold side of this U. Try seed 42: build A3 (card 1, R), B4 (card 2, Q), then B3 (card 1, R twice).",
                              pygame.Rect(359, 541, 650, 54), MUTED)
        self.button(surface, GUIDE_PREV_RECT, "<  Previous", page > 0)
        self.button(surface, GUIDE_NEXT_RECT, "Next  >", page + 1 < len(GUIDE_PAGES))
        self.text(surface, "Left / Right to turn pages", (560, 623), MUTED, self.small_font)
        self.button(surface, GUIDE_CLOSE_RECT, "Close  [H]")

    def room(self, surface, rect, doors, color=TEAL):
        """Draw explicit walls and door gaps in the same N/E/S/W order as the engine."""
        bounds = rect.inflate(-10, -10)
        pygame.draw.rect(surface, (43, 60, 70), bounds, border_radius=5)
        cx, cy = bounds.center
        ends = ((cx, bounds.top), (bounds.right, cy), (cx, bounds.bottom), (bounds.left, cy))
        width = max(12, bounds.width // 3)
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
             help_open: bool = False, help_page: int = 0, event_feedback=None, feedback_age: int = 0):
        mvp = hasattr(session, "level")
        terminal = getattr(session, "status", "PLAYING") in ("WON", "LOST")
        if terminal:
            hovered_pos = None
            seal_direction = None
            chisel_mode = False
        surface.blit(self.backdrop, (0, 0))
        self.draw_title(surface)
        resources = session.resources
        self.status_chip(surface, HP_RECT, "HP", f"{resources.hp}/{resources.hp_max}",
                         RED if session.hp_depleted else TEAL, self.status_icons["health"])
        limit = f" / {resources.supplies_max}" if resources.supplies_max is not None else ""
        self.status_chip(surface, SUPPLIES_RECT, "SUPPLIES",
                         f"{resources.supplies}{limit.replace(' ', '')}", GOLD,
                         self.status_icons["supply"])
        self.button(surface, HELP_RECT, "Help  [H]")
        self.button(surface, LOBBY_RECT, "Hall [L]")
        self.button(surface, RESTART_RECT, "Restart  [N]")
        stone_frame(surface, (214, 84, 571, 572), RECESS, cut=8)
        pygame.draw.rect(surface, LINE, BOARD_RECT.inflate(4, 4), width=1)
        rooms = sum(tile is not None and tile.kind != "rubble" for row in session.board for tile in row)
        self.text(surface, Message("MAP  |  {rooms} / 49 ROOMS", rooms=rooms), (238, 90), MUTED, self.small_font)
        seed_label = self.fit_text(Message("Seed {seed}", seed=session.seed), 180, self.small_font)
        if mvp and session.guard_pos is not None and not terminal:
            self.text(surface, Message("Guard moves in {n} builds", n=session.guard_moves_on - session.build_turn),
                      (385, 90), GOLD, self.small_font)
        self.text(surface, seed_label, (582, 90), MUTED, self.small_font)
        self.text(surface, "CHOOSE A ROOM", (806, 86), PURPLE, self.small_font)
        if 0 < resources.hp <= 2 and not terminal and not help_open:
            self.low_health_warning(surface, session)
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
                    if tile.kind in ("rubble", "spring"):
                        self.terrain_art(surface, rect, tile)
                    else:
                        self.tile_art(surface, rect, tile.doors, color, special=special)
                    if tile.kind == "start":
                        self.text(surface, "S", (rect.left + 7, rect.top + 5), GOLD, self.small_font)
                    elif pos in altar_positions:
                        self.text(surface, f"A{altar_positions[pos]}", (rect.left + 7, rect.top + 5), color, self.small_font)
                    elif mvp and pos == session.level.core.pos:
                        self.text(surface, "C+" if session.core_unlocked else "C-",
                                  (rect.left + 7, rect.top + 5), color, self.small_font)
                    elif tile.event_category in ("supply", "danger"):
                        icon = self.objects["supply" if tile.trapped_cache else tile.event_category]
                        center = (rect.centerx + 11, rect.centery + 5) if pos == session.player_pos else rect.center
                        surface.blit(icon, icon.get_rect(center=center))
                    elif tile.event_category and tile.event_category != "neutral":
                        pygame.draw.circle(surface, MUTED, (rect.right - 9, rect.bottom - 9), 3)
                elif fits:
                    surface.blit(self.legal_tint, rect)
                    pygame.draw.rect(surface, BUILD_GREEN, rect, width=2)
                elif pos in frontier:
                    pygame.draw.circle(surface, TEAL, rect.center, 3)
                else:
                    surface.blit(self.unknown_mark, self.unknown_mark.get_rect(center=rect.center))
                if chisel_mode and tile is not None and session.chisel_preview(session.player_pos, pos)[0]:
                    pygame.draw.rect(surface, GOLD, rect, width=2, border_radius=7)
        for index in range(BOARD_SIZE):
            self.text(surface, chr(ord('A') + index),
                      (cell_rect((0, index)).centerx - 5, BOARD_RECT.top - 15), MUTED, self.small_font)
            self.text(surface, str(index + 1), (BOARD_RECT.left - 18, BOARD_RECT.top + index * CELL_SIZE + 28),
                      MUTED, self.small_font)
        stone_frame(surface, (20, 86, 181, 210), RECESS)
        self.text(surface, "Objectives", (33, 102), TEXT, self.heading_font)
        if mvp:
            for index, altar in enumerate(session.level.altars[:2]):
                active = altar.kind in session.activated_altars
                self.objective_chip(surface, pygame.Rect(33, 148 + index * 41, 155, 28),
                                    Message("A{index} {cell}", index=index + 1, cell=cell_label(altar.pos)),
                                    "ACTIVE" if active else "IDLE", GOLD if active else PURPLE)
            self.objective_chip(surface, pygame.Rect(33, 230, 155, 28),
                                Message("CORE {cell}", cell=cell_label(session.level.core.pos)),
                                "OPEN" if session.core_unlocked else "LOCKED",
                                TEAL if session.core_unlocked else RED)
            self.text(surface, Message("Loops closed   {count}", count=session.loops_closed), (37, 268), GOLD, self.small_font)
        else:
            self.text(surface, "Explore the ruins", (33, 148), MUTED)
        stone_frame(surface, (20, 307, 181, 177), RECESS)
        self.text(surface, "Map key", (33, 321), TEXT, self.heading_font)
        legend = [("Built room", STEEL), ("Can build", BUILD_GREEN), ("Unexplored", MUTED), ("Landmark", PURPLE)]
        if mvp:
            legend.extend((("Vine spires", VINE_SPIRES), ("Healing well", SPRING)))
        for index, (label, color) in enumerate(legend):
            y = 351 + index * 21
            pygame.draw.rect(surface, color, (34, y, 13, 13), width=1 if index in (1, 2) else 0)
            self.text(surface, label, (58, y), TEXT, self.small_font)
        stone_frame(surface, (20, 496, 181, 212), RECESS)
        self.text(surface, "Map overview", (33, 510), TEXT, self.heading_font)
        for row, tiles in enumerate(session.board):
            for col, tile in enumerate(tiles):
                box = pygame.Rect(44 + col * 19, 551 + row * 19, 17, 17)
                pos = (row, col)
                color = STEEL if tile else LINE
                if pos == session.player_pos:
                    color = GOLD
                elif pos in altar_positions or (mvp and pos == session.level.core.pos):
                    color = PURPLE
                elif tile and tile.kind == "rubble":
                    color = VINE_SPIRES
                elif tile and tile.kind == "spring" and not tile.event_resolved:
                    color = SPRING
                elif pos in legal:
                    color = BUILD_GREEN
                pygame.draw.rect(surface, color, box, width=0 if tile else 1)
                if tile:
                    for door, tip in zip(tile.doors, (box.midtop, box.midright, box.midbottom, box.midleft)):
                        if door:
                            pygame.draw.line(surface, RECESS, box.center, tip, 2)
        new_loops = 0
        if hovered_pos is not None:
            occupied = session.board[hovered_pos[0]][hovered_pos[1]] is not None
            walking = occupied and hovered_pos != session.player_pos
            if chisel_mode:
                ok, reason = session.chisel_preview(session.player_pos, hovered_pos)
                if ok:
                    new_loops = int(hovered_pos in reachable_rooms(session.board, session.player_pos))
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
                if ok and mvp:
                    new_loops = loops_closed_by_room(session.board, hovered_pos, doors)
            border = (BUILD_GREEN if ok else RED) if card is not None or walking or chisel_mode else MUTED
            pygame.draw.rect(surface, border, rect, width=3, border_radius=7)
        else:
            reason = "no_normal_placement" if session.blocked else "no_card_selected"
        if mvp and session.guard_pos is not None and not terminal:
            guard = cell_rect(session.guard_pos)
            if session.guard_next is not None:
                target = cell_rect(session.guard_next)
                pygame.draw.rect(surface, GOLD, target.inflate(-8, -8), width=2, border_radius=6)
                direction = (pygame.Vector2(target.center) - guard.center).normalize()
                side = direction.rotate(90)
                tip = pygame.Vector2(target.center) - direction * 16
                pygame.draw.line(surface, GOLD, tip - direction * 24, tip, 4)
                pygame.draw.polygon(surface, GOLD, [tip, tip - direction * 10 + side * 6,
                                                     tip - direction * 10 - side * 6])
            x, y = guard.right - 17, guard.top + 16
            helmet = [(x-9,y-7), (x,y-11), (x+9,y-7), (x+8,y+4), (x,y+11), (x-8,y+4)]
            pygame.draw.polygon(surface, RED, helmet)
            pygame.draw.polygon(surface, RECESS, helmet, 2)
            pygame.draw.line(surface, RECESS, (x-5,y-1), (x+5,y-1), 3)
        player_center = cell_rect(session.player_pos).center
        explorer = self.objects["explorer"]
        surface.blit(explorer, explorer.get_rect(center=player_center))

        event_weights = {room.kind: room.event_weights for room in session.config.room_types}
        for index, card in enumerate(session.draw_result.cards):
            rect = CARD_RECTS[index]
            selected = session.selected_index == index
            stone_frame(surface, rect, (45, 39, 67) if selected else PANEL,
                        GOLD if selected else LINE, cut=10)
            stone_frame(surface, (rect.x + 9, rect.y + 23, 98, 98), RECESS, cut=10)
            shown = session.card_at(index)
            shown_doors = (tuple(False if side == seal_direction else value for side, value in enumerate(shown.doors))
                           if selected else shown.doors)
            self.tile_art(surface, pygame.Rect(rect.x + 12, rect.y + 26, 92, 92), shown_doors, card=True)
            self.text(surface, ROOM_NAMES.get(card.kind, card.kind.replace('_', ' ').title()),
                      (rect.x + 122, rect.y + 12), font=self.heading_font)
            trait, trait_color = ROOM_TRAITS.get(card.kind, ("Unknown event", MUTED))
            self.text(surface, trait, (rect.x + 122, rect.y + 38), trait_color, self.small_font)
            self.card_event_odds(surface, rect, event_weights[card.kind])
            pygame.draw.line(surface, LINE, (rect.x + 122, rect.y + 107), (rect.right - 16, rect.y + 107))
            if selected and seal_direction is not None:
                playable = bool(legal)
                fit_message = "Seal fits this rotation" if playable else "No fit with this seal"
            else:
                playable = index in session.draw_result.legal_card_indices
                fit_message = "Fits in some rotation" if playable else "No fit on this map"
            self.text(surface, fit_message,
                      (rect.x + 122, rect.y + 117), TEAL if playable else MUTED, self.small_font)
            self.text(surface, Message("Rotation {angle} deg", angle=session.rotations[index] * 90),
                      (rect.right - 112, rect.y + 117), MUTED, self.small_font)
            self.text(surface, str(index + 1), (rect.right - 25, rect.y + 15), GOLD if selected else MUTED)

        if session.blocked:
            rect = pygame.Rect(806, 112, 442, 456)
            stone_frame(surface, rect, RECESS, RED, cut=10)
            self.text(surface, "No normal placement", (830, 270), RED, self.heading_font)
            self.wrapped_text(surface, "No room shape fits your open exits. You can still walk through built rooms or restart.",
                              pygame.Rect(830, 312, 390, 60), MUTED)

        self.button(surface, ROTATE_RECT, "Rotate  [R]", session.selected_card is not None and not terminal)
        if mvp:
            self.button(surface, MEDKIT_RECT, "Medkit [M]  2 supplies", session.medkit_preview()[0])
            seal_label = "Seal [F]" if seal_direction is None else Message("Seal {side} [F]", side="NESW"[seal_direction])
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
            self.text(surface, Message("Seal {s}S / {ns} left   Chisel {c}S / {nc} left",
                                       s=seal.cost_supplies, ns=remaining_seal, c=chisel.cost_supplies, nc=remaining_chisel),
                      (986, 620), MUTED, self.small_font)
        else:
            self.text(surface, "Q rotates counterclockwise", (990, 607), MUTED, self.small_font)
        stone_frame(surface, EVENT_RECT, RECESS)
        notification = session.current_event
        if notification is not None:
            color = EVENT_COLORS.get(notification.category, MUTED)
            title = Message("LAST EVENT: {category} at {cell}", category=notification.category.title(), cell=cell_label(notification.pos))
            self.text(surface, title, (818, 651), color, self.small_font)
            self.text(surface, self.fit_text(notification.message, 418), (818, 669))
            deltas = []
            if notification.hp_delta:
                deltas.append(self.t(Message("HP {amount:+d}", amount=notification.hp_delta)))
            if notification.supplies_delta:
                deltas.append(self.t(Message("Supplies {amount:+d}", amount=notification.supplies_delta)))
            if notification.loops_closed:
                deltas.append(self.t(loop_label(notification)))
            change = "  |  ".join(deltas) or "No resource change (unchanged or at a limit)"
            self.text(surface, change, (818, 691),
                      RED if notification.hp_delta < 0 or notification.supplies_delta < 0 else TEAL,
                      self.small_font)
        else:
            self.text(surface, "Enter a new room to discover its event.", (818, 663), MUTED)
        feedback = message
        if hovered_pos is not None and chisel_mode:
            feedback = tool_message(reason)
        elif hovered_pos is not None and walking:
            feedback = movement_message(reason)
        elif hovered_pos is not None and session.selected_card is not None:
            feedback = tool_message(reason) if seal_direction is not None else placement_message(reason)
        if new_loops:
            feedback = Message("{action} Closes {n} new loop." if new_loops == 1 else "{action} Closes {n} new loops.",
                               action=feedback, n=new_loops)
        if hovered_pos is not None:
            hovered_tile = session.board[hovered_pos[0]][hovered_pos[1]]
            if hovered_tile and hovered_tile.kind == "rubble":
                feedback = movement_message("rubble")
            elif hovered_tile and hovered_tile.kind == "spring" and not chisel_mode:
                feedback = ("The well is dry. The room is still passable." if hovered_tile.event_resolved
                            else "Healing well. Connect a path and enter to recover 1 HP once.")
        if session.blocked and hovered_pos is None and not chisel_mode:
            feedback = ("No normal room fits. You can walk, use a tool or restart." if mvp
                        else placement_message("no_normal_placement"))
        if session.hp_depleted and not mvp:
            feedback = "HP depleted (0). Press N to restart."
        stone_frame(surface, (218, 660, 565, 48), RECESS)
        if session.trapped_cache and not terminal:
            gain = session.cache_gain
            enabled = session.resources.hp > 1 and gain > 0
            self.text(surface, "Barbed chest", (230, 664), GOLD)
            detail = Message("Pay 1 HP for {gain} Supplies, or leave it here.", gain=gain)
            if session.resources.hp <= 1:
                detail = "Opening costs 1 HP. Return with at least 2 HP."
            elif not gain:
                detail = "Your pack is full. You can return later."
            self.text(surface, detail, (230, 687), MUTED, self.small_font)
            self.button(surface, CACHE_RECT, "Open chest  [E]", enabled)
        else:
            self.wrapped_text(surface, feedback, pygame.Rect(230, 665, 540, 44), RED if session.blocked else TEXT)
        footer = ("1/2/3 Select  R/Q Rotate  Click Build/Walk  Arrows/WASD Walk  F Seal  C Chisel  H Help  F11 Fullscreen  N Restart  Esc Quit"
                  if mvp else "1/2/3 Select  R/Q Rotate  Click Build/Walk  Arrows/WASD Walk  F11 Fullscreen  N Restart  Esc Quit")
        self.text(surface, footer,
                  (30, 719), MUTED, self.small_font)
        if event_feedback is not None and not terminal:
            self.event_toast(surface, event_feedback, feedback_age)
        if terminal:
            shade = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)
            shade.fill((5, 11, 17, 205))
            surface.blit(shade, (0, 0))
            panel = pygame.Rect(260, 220, 760, 300)
            won = session.status == "WON"
            color = GOLD if won else RED
            stone_frame(surface, panel, RECESS, color, cut=16)
            pygame.draw.line(surface, LINE, (310, 299), (970, 299))
            self.text(surface, "VICTORY" if won else "DEFEAT", (310, 252), color, self.title_font)
            explanation = ("All altars are active. You reached the unlocked core."
                           if won else "Your HP reached zero. Try a different route or use your tools earlier.")
            self.wrapped_text(surface, explanation, pygame.Rect(310, 312, 660, 60))
            self.text(surface, Message("Rooms built: {rooms}   HP: {hp}   Supplies: {supplies}",
                                       rooms=session.build_turn, hp=resources.hp, supplies=resources.supplies),
                      (310, 382), MUTED)
            self.button(surface, END_RESTART_RECT, "Restart  [N]")
            self.text(surface, "Esc closes the game", (558, 482), MUTED, self.small_font)
        if help_open:
            self.help_overlay(surface, help_page)
