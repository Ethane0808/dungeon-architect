"""Room/map/card drawing, resource HUD and first-entry event feedback."""

import re
from pathlib import Path

import pygame

from engine.game import BuildSession
from engine.encounters import BLOCK_START_MS, BLOCK_END_MS, PERFECT_START_MS, PERFECT_END_MS, ROOM_NAMES as ENCOUNTERS
from engine.tutorial import TutorialSession
from engine.messages import Message
from engine.directions import DIRECTIONS, OPPOSITE, neighbor_pos
from ui.locales import translate
from ui.event_art import chest_frames, event_effect, event_sprites, fit_sprites, mist_texture, portal_effect, traveler_art, vine_spires_art
from engine.models import BOARD_SIZE
from engine.placement import frontier_cells, loops_closed_by_room, reachable_rooms


WINDOW_SIZE = (1280, 740)
CELL_SIZE = 76
BOARD_RECT = pygame.Rect(240, 120, CELL_SIZE * BOARD_SIZE, CELL_SIZE * BOARD_SIZE)
CARD_RECTS = tuple(pygame.Rect(806, 112 + index * 156, 442, 144) for index in range(3))
RESTART_RECT = pygame.Rect(1102, 24, 146, 40)
HELP_RECT = pygame.Rect(980, 24, 110, 40)
ROTATE_RECT = pygame.Rect(806, 574, 170, 32)
MEDKIT_RECT = pygame.Rect(806, 646, 142, 62)
SEAL_RECT = pygame.Rect(956, 646, 142, 62)
CHISEL_RECT = pygame.Rect(1106, 646, 142, 62)
TOOL_SLOTS = (
    ("medkit", MEDKIT_RECT, "Medkit [M]", "When hurt, click or press M to heal 1 HP."),
    ("door_seal", SEAL_RECT, "Seal [F]", "Select a card. Cycle doors with F, then build."),
    ("emergency_chisel", CHISEL_RECT, "Chisel [C]", "Press C, then click a room across a shared wall."),
)
PLAN_GO_RECT = pygame.Rect(33, 474, 70, 30)
PLAN_CANCEL_RECT = pygame.Rect(111, 474, 76, 30)
END_RESTART_RECT = pygame.Rect(540, 422, 200, 44)
HP_RECT = pygame.Rect(512, 22, 126, 42)
SUPPLIES_RECT = pygame.Rect(650, 22, 144, 42)
EVENT_FEEDBACK_MS = 2400
CHEST_OPEN_MS = 550
LOBBY_RECT = pygame.Rect(885, 24, 85, 40)
LANGUAGE_RECT = pygame.Rect(800, 24, 78, 40)
ENTER_RECT = pygame.Rect(704, 372, 294, 54)
GUIDE_RECT = pygame.Rect(704, 442, 294, 42)
EXIT_RECT = pygame.Rect(704, 496, 294, 42)
TUTORIAL_RECT = pygame.Rect(704, 550, 294, 42)
ENDLESS_RECT = pygame.Rect(704, 604, 294, 42)
TUTORIAL_SKIP_RECT = pygame.Rect(37, 348, 148, 26)
TUTORIAL_START_RECT = pygame.Rect(467, 416, 346, 48)
TUTORIAL_REPLAY_RECT = pygame.Rect(467, 478, 346, 44)
GUIDE_CLOSE_RECT = pygame.Rect(850, 612, 116, 36)
GUIDE_PREV_RECT = pygame.Rect(264, 612, 132, 36)
GUIDE_NEXT_RECT = pygame.Rect(408, 612, 132, 36)

GUIDE_PAGES = (
    ("Building and Navigation", (
        ("1  BUILD", "Pick and rotate a card. Green cells are beside you: click to build. Cyan dashed cells fit elsewhere: click to plan, then confirm with Enter at the entrance."),
        ("2  EXPLORE", "Use arrows, WASD or click an adjacent room to walk. With a plan, press G to walk one room at a time; every step advances the guard."),
        ("3  READ THE MAP", "A plan shows its blueprint, shortest route, entrance and distance. G pauses or resumes. Esc cancels the plan before it quits the game."),
        ("4  USE TOOLS", "Rotate, seal a door or chisel a wall to make room. When hurt, press M to use a medkit: spend 2 supplies to recover 1 HP."),
    )),
    ("Exploration and Survival", (
        ("ROOM CARDS", "Straights are usually quiet. T junctions often hold danger. Dead ends and crossroads can reveal special events."),
        ("FIRST ENTRY", "A room reveals its event only once. Rations give 1 or 2 supplies. Healing herbs restore 1 HP. Darts cost 1 HP, falling stone costs 2 HP, and thorns cost 1 supply."),
        ("BARBED CHEST", "Press E or click Open chest to trade 1 HP for up to 2 supplies. Leave it for later if your pack is full or you have only 1 HP."),
        ("ALTARS & CORE", "Walk into both altars in either order. The first gives 1 supply. Enter the unlocked core to win. Reaching zero HP ends the expedition."),
    )),
    ("Advanced Tools and Strategy", (
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
TEAL = (56, 210, 232)
GOLD = (255, 210, 91)
RED = (255, 99, 108)
PURPLE = (187, 139, 255)
BUILD_GREEN = (103, 235, 116)
VINE_SPIRES = (145, 160, 88)
SPRING = (99, 214, 228)
EVENT_COLORS = {"supply": TEAL, "danger": RED, "guard": RED, "neutral": MUTED, "relic": PURPLE,
                "spring": SPRING, "medkit": TEAL, "bell": GOLD, "fog": (169, 198, 219),
                "monster": RED, "casino": GOLD, "altar": PURPLE, "construction": STEEL}
ROOM_TRAITS = {
    "dead_end": ("Treasure-prone", GOLD),
    "straight": ("Usually safe", TEAL),
    "corner": ("Balanced event", MUTED),
    "t_junction": ("Risk / reward", RED),
    "cross": ("Special event chance", PURPLE),
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


def needs_event_panel(notice):
    return notice.category not in {"neutral", "supply", "danger"} or bool(notice.trapped_cache)


def event_panel_rect(pos):
    cell = cell_rect(pos)
    panel = pygame.Rect(0, 0, 400, 120)
    panel.centerx = cell.centerx
    if cell.centery < BOARD_RECT.centery:
        panel.bottom = BOARD_RECT.bottom - 4
    else:
        panel.top = BOARD_RECT.top + 4
    return panel.clamp(BOARD_RECT.inflate(-8, -8))


def event_close_rect(pos):
    panel = event_panel_rect(pos)
    return pygame.Rect(panel.right - 68, panel.top + 5, 60, 25)


def cache_prompt_rect(pos):
    return event_panel_rect(pos)


def choice_rects(pos):
    panel = event_panel_rect(pos)
    return tuple(pygame.Rect(panel.x + 8 + 194*i, panel.bottom - 35, 190, 29) for i in range(2))


def block_key_rect(pos):
    panel = event_panel_rect(pos)
    return pygame.Rect(panel.x + 12, panel.bottom - 48, panel.width - 24, 42)


def cache_button_rect(pos):
    return choice_rects(pos)[0]


def persistent_event_marker(tile) -> str | None:
    """Return only event markers that still represent a live or lasting object."""
    if tile.event_category == "neutral":
        return None
    if tile.event_category == "danger" and tile.event_resolved:
        return "barbed-cache" if tile.trapped_cache else None
    return tile.event_icon or tile.event_category


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
        "guard_blocks_route": "The guard blocks the construction route.",
        "in_fog": "The mist hides part of this route.",
        "not_at_build_frontier": "Geometry fits. Plan a route to its entrance.",
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
        "room_locked": "Sealed portal. Visit every altar before entering.",
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
    # Keep the relief inside the panel, clear of neighboring controls.
    shadow = tuple(channel * 2 // 3 for channel in fill)
    pygame.draw.lines(surface, shadow, False,
                      [(l + cut, b - 1), (right - cut, b - 1), (right - 1, b - cut), (right - 1, t + cut)])
    pygame.draw.line(surface, STEEL if edge == LINE else edge, (l + cut, t), (right - cut, t))
    if r.width >= 140 and r.height >= 42:
        for x in (l + cut, right - cut):
            pygame.draw.line(surface, shadow, (x - 1, t + 4), (x + 1, t + 4), 2)
            surface.set_at((x, t + 3), edge)


class GameRenderer:
    def __init__(self):
        serif = pygame.font.match_font("cinzel,constantia,georgia,dejavuserif")
        self.title_font = pygame.font.Font(serif, 34)
        self.heading_font = pygame.font.Font(None, 26)
        self.font = pygame.font.Font(None, 22)
        self.small_font = pygame.font.Font(None, 18)
        self.language = "en"
        self.english_fonts = self.title_font, self.heading_font, self.font, self.small_font
        font_file = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "SourceHanSansTC-Regular.otf"
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
        guard_art = self.objects["patrol-guard"]
        self.objects["explorer"], self.traveler_frames, self.lantern_lights = traveler_art(self.objects["explorer"])
        self.explorer_preview = self.objects["explorer"].copy()
        self.explorer_preview.set_alpha(175)
        bounds = guard_art.get_bounding_rect(min_alpha=64)
        self.guard_sprite = pygame.transform.scale(
            guard_art.subsurface(bounds), bounds.fit(pygame.Rect(0, 0, 50, 56)).size
        )
        sprites = event_sprites(self.objects)
        self.room_events = fit_sprites(sprites, 24)
        self.event_badges = fit_sprites(sprites, 18)
        pouch = pygame.Surface((24, 24), pygame.SRCALPHA)
        pygame.draw.rect(pouch, GOLD, (7, 3, 10, 7), 2, border_radius=2)
        pygame.draw.rect(pouch, "#844d45", (1, 8, 22, 15), border_radius=3)
        pygame.draw.rect(pouch, "#e3ae88", (2, 8, 20, 13), 1, border_radius=2)
        pygame.draw.rect(pouch, "#fff1d5", (10, 10, 4, 9))
        pygame.draw.rect(pouch, "#fff1d5", (7, 13, 10, 3))
        self.tool_icons = fit_sprites({"medkit": pouch, "door_seal": self.objects["seal"],
                                      "emergency_chisel": sprites["construction"]}, 31)
        self.encounter_art = fit_sprites({kind: sprites[kind] for kind in (*ENCOUNTERS, "spring")}, 34)
        self.spent_encounters = {kind: pygame.transform.grayscale(sprite)
                                 for kind, sprite in self.encounter_art.items()}
        for sprite in self.spent_encounters.values():
            sprite.fill((160, 160, 174, 255), special_flags=pygame.BLEND_RGBA_MULT)
        dry_well = sprites["spring"].copy()
        pygame.draw.ellipse(dry_well, RECESS, (4, 7, 16, 8))
        self.spent_encounters["spring"] = pygame.transform.scale(dry_well, (34, 34))
        self.chest_frames = chest_frames()
        self.vine_tile = vine_spires_art(self.objects["vine-spires"], CELL_SIZE)
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
                # Paired bronze pins mark the edges of an open threshold, never its center.
                for open_side, direction in zip(doors, ((0, -1), (1, 0), (0, 1), (-1, 0))):
                    if open_side:
                        dx, dy = direction
                        for side in (-1, 1):
                            x = road.get_width() // 2 + 29 * dx + 13 * side * dy
                            y = road.get_height() // 2 + 29 * dy - 13 * side * dx
                            pygame.draw.rect(road, "#52493f", (x - 1, y - 1, 3, 3))
                            road.set_at((x, y - 1), "#c4aa76")
                self.room_tiles[doors] = road
                plate = pygame.Surface((92, 92), pygame.SRCALPHA)
                for offset in range(10, 92, 12):
                    pygame.draw.line(plate, (105, 150, 173, 30), (offset, 5), (offset, 86))
                    pygame.draw.line(plate, (105, 150, 173, 30), (5, offset), (86, offset))
                plate.blit(pygame.transform.scale(road, plate.get_size()), (0, 0))
                self.card_tiles[doors] = plate
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
        # Both altars share one symmetric amethyst silhouette and state palette.
        for state in ("idle", "activated"):
            crystal = pygame.Surface((44, 44), pygame.SRCALPHA)
            edge = (216, 181, 255) if state == "activated" else (158, 119, 211)
            face = (174, 104, 244) if state == "activated" else (104, 65, 153)
            pygame.draw.ellipse(crystal, (54, 43, 76), (4, 32, 36, 10))
            pygame.draw.ellipse(crystal, edge, (4, 32, 36, 10), 1)
            pygame.draw.polygon(crystal, face, [(22, 2), (34, 14), (31, 31), (22, 38), (13, 31), (10, 14)])
            pygame.draw.polygon(crystal, edge, [(22, 2), (34, 14), (31, 31), (22, 38), (13, 31), (10, 14)], 1)
            pygame.draw.polygon(crystal, (206, 158, 255), [(22, 3), (26, 15), (22, 36), (18, 15)])
            pygame.draw.lines(crystal, (235, 210, 255) if state == "activated" else (170, 132, 212),
                              False, [(11, 14), (17, 16), (20, 8)])
            pygame.draw.line(crystal, face, (14, 27), (17, 22))
            # A raised, stepped stone pedestal anchors the crystal in the ruin.
            pygame.draw.rect(crystal, (59, 54, 79), (8, 33, 28, 7))
            pygame.draw.line(crystal, (153, 137, 177), (8, 33), (35, 33), 2)
            pygame.draw.rect(crystal, (85, 76, 105), (4, 39, 36, 4))
            pygame.draw.line(crystal, (173, 154, 194), (4, 39), (39, 39))
            pygame.draw.line(crystal, edge, (18, 36), (25, 36))
            # Mirror the left half exactly, including rasterized outlines.
            mirrored = pygame.transform.flip(crystal.subsurface((0, 0, 22, 44)), True, False)
            crystal.fill((0, 0, 0, 0), (22, 0, 22, 44))
            crystal.blit(mirrored, (22, 0))
            for altar in ("altar_a", "altar_b"):
                name = f"{altar}-{state}"
                self.objects[name] = crystal
                for doors in self.card_tiles:
                    tile = self.room_tiles[doors].copy()
                    tile.blit(crystal, (16, 16))
                    self.room_tiles[name, doors] = tile
        # The final destination is a carved portal, dark until both altars awaken.
        for state in ("locked", "unlocked"):
            active = state == "unlocked"
            portal = pygame.Surface((44, 44), pygame.SRCALPHA)
            if active:
                for inset, alpha in ((0, 32), (3, 55), (6, 90)):
                    pygame.draw.ellipse(portal, (69, 245, 137, alpha), (inset, inset, 44 - 2 * inset, 44 - 2 * inset))
            arch = [(5, 36), (5, 15), (9, 7), (16, 2), (28, 2), (35, 7), (39, 15), (39, 36)]
            pygame.draw.polygon(portal, (78, 82, 91), arch)
            pygame.draw.lines(portal, (154, 160, 165), False, arch, 2)
            opening = [(11, 35), (11, 16), (14, 10), (22, 6), (30, 10), (33, 16), (33, 35)]
            pygame.draw.polygon(portal, (22, 85, 52) if active else (15, 17, 24), opening)
            for start, end in (((6, 15), (11, 17)), ((9, 8), (14, 11)),
                               ((38, 15), (33, 17)), ((35, 8), (30, 11))):
                pygame.draw.line(portal, (53, 54, 68), start, end, 2)
            if active:
                pygame.draw.ellipse(portal, (44, 171, 100), (13, 10, 18, 27))
                pygame.draw.ellipse(portal, (91, 242, 151), (16, 13, 12, 21))
                pygame.draw.ellipse(portal, (199, 255, 218), (19, 17, 6, 15))
                pygame.draw.lines(portal, (115, 255, 170), False, opening, 1)
            else:
                # Two dormant sockets echo the two altar objectives.
                for x in (18, 26):
                    pygame.draw.polygon(portal, (56, 54, 67), [(x, 20), (x + 2, 23), (x, 26), (x - 2, 23)])
            rune = (120, 255, 172) if active else (91, 96, 105)
            for x in (7, 36):
                for y in (17, 24, 31):
                    pygame.draw.line(portal, rune, (x, y), (x + 1, y + 2))
            # Keystone and broad entry steps distinguish the exit from a room.
            pygame.draw.polygon(portal, rune, [(22, 1), (25, 4), (22, 7), (19, 4)])
            for y, x in ((36, 7), (39, 3)):
                pygame.draw.rect(portal, (73, 80, 87), (x, y, 44 - 2 * x, 4))
                pygame.draw.line(portal, rune, (x, y), (43 - x, y))
            name = f"core-{state}"
            self.objects[name] = portal
            for doors in self.card_tiles:
                tile = self.room_tiles[doors].copy()
                tile.blit(portal, (16, 16))
                self.room_tiles[name, doors] = tile
        # The tutorial uses different doorway shapes for its landmarks. Keep
        # their painted centers while retaining the playable exits.
        landmark_doors = {
            "altar_a-idle": (False, False, True, True),
            "altar_a-activated": (False, False, True, True),
            "altar_b-idle": (True, False, False, True),
            "altar_b-activated": (True, False, False, True),
            "core-locked": (True, False, True, True),
            "core-unlocked": (True, False, True, True),
        }
        center = pygame.Rect(16, 16, 44, 44)
        for name, original_doors in landmark_doors.items():
            original = self.room_tiles[name, original_doors]
            for doors in self.card_tiles:
                if (name, doors) not in self.room_tiles and doors in self.room_tiles:
                    variant = self.room_tiles[doors].copy()
                    variant.fill((0, 0, 0, 0), center)
                    variant.blit(original, center, center)
                    self.room_tiles[name, doors] = variant
        self.lobby_backdrop = self.backdrop.copy()
        self.event_badges["altar"] = pygame.transform.scale(self.objects["altar_a-activated"], (18, 18))
        hall = self.lobby_backdrop
        stone_frame(hall, (138, 134, 1004, 536), RECESS, cut=18)
        # A carved gate on a raised plinth, lit by the two altar stones.
        for inset, fill in ((0, LINE), (9, PANEL), (20, STEEL), (23, BACKGROUND)):
            left, right = 222 + inset, 538 - inset
            top = 173 + inset
            pygame.draw.polygon(hall, fill, [(left, 490), (left, top + 108),
                                (380, top), (right, top + 108), (right, 490)])
        # Reuse the ruin's masonry inside the arch, where the purple altar light falls.
        recess = pygame.Surface((270, 294), pygame.SRCALPHA)
        recess.blit(pygame.transform.scale(pavement, recess.get_size()), (0, 0))
        recess.fill((111, 101, 138, 255), special_flags=pygame.BLEND_RGBA_MULT)
        silhouette = pygame.Surface(recess.get_size(), pygame.SRCALPHA)
        pygame.draw.polygon(silhouette, "white", [(0, 293), (0, 109), (135, 1),
                                                  (269, 109), (269, 293)])
        recess.blit(silhouette, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        hall.blit(recess, (245, 196))
        for x in (233, 527):
            for y in (310, 348, 386):
                pygame.draw.line(hall, LINE, (x - 8, y), (x + 8, y))
                pygame.draw.line(hall, BACKGROUND, (x - 7, y + 1), (x + 7, y + 1))
        gate = self.objects["core-locked"]
        gate = pygame.transform.scale(gate, (140, 180))
        hall.blit(gate, gate.get_rect(midbottom=(380, 482)))
        for step in range(4):
            stone_frame(hall, (220 - step * 10, 487 + step * 13, 320 + step * 20, 14), cut=3)
        for x in (222, 538):
            aura = pygame.Surface((140, 120), pygame.SRCALPHA)
            for radius in range(59, 0, -2):
                pygame.draw.circle(aura, (173, 119, 234, (60 - radius) * 2), (70, 60), radius)
            hall.blit(aura, aura.get_rect(center=(x, 444)))
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

    def lobby(self, surface, seed, started, terminal, *, show_endless=False, resume_endless=False):
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
        self.button(surface, TUTORIAL_RECT, "Learn to play [T]")
        if show_endless:
            self.button(surface, ENDLESS_RECT, "Resume endless [U]" if resume_endless else "Endless mode [U]")

    def tutorial(self, surface, session):
        if session.status == "LOST":
            return  # Keep the normal defeat message and restart controls visible.
        if session.lesson == 5:
            shade = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)
            shade.fill((8, 12, 24, 190))
            surface.blit(shade, (0, 0))
            stone_frame(surface, (384, 278, 512, 290), RECESS, GOLD, cut=16)
            self.text(surface, "You're ready to build your dungeon!", (414, 324), GOLD, self.heading_font)
            self.text(surface, "6 / 6", (820, 292), MUTED, self.small_font)
            self.wrapped_text(surface, session.narration, pygame.Rect(414, 364, 452, 42), TEXT)
            self.button(surface, TUTORIAL_START_RECT, "Start Adventure  [Enter]")
            self.button(surface, TUTORIAL_REPLAY_RECT, "Replay Tutorial  [T]")
            return
        instruction = (
            "Choose a room card.",
            "Rotate to connect doors, then build.",
            "Move through connected rooms.",
            "Plan anywhere. Build from nearby.",
            "Activate both altars to unlock the core.",
        )[session.lesson]
        tip = (
            "Click card 1 / press 1.",
            "R, then click B4.",
            "Left / click A4: free.",
            "G, then Enter." if session.plan_created else "1, R, then click C4.",
            "Walk right to the core.",
        )[session.lesson]
        stone_frame(surface, (20, 250, 181, 126), RECESS, GOLD)
        self.text(surface, "Learn to play", (32, 259), GOLD, self.heading_font)
        self.text(surface, f"{session.lesson + 1} / 6", (149, 261), MUTED, self.small_font)
        for index in range(6):
            pygame.draw.rect(surface, GOLD if index <= session.lesson else LINE,
                             (32 + index * 26, 281, 22, 2))
        self.wrapped_text(surface, instruction, pygame.Rect(32, 284, 156, 40), TEXT)
        self.wrapped_text(surface, tip, pygame.Rect(32, 324, 156, 24), MUTED)
        self.button(surface, TUTORIAL_SKIP_RECT, "Skip Tutorial")
        player = cell_rect(session.player_pos)
        narration = pygame.Rect(player.centerx - 180, player.top - 112, 360, 102)
        narration.clamp_ip(BOARD_RECT.inflate(-12, -12))
        stone_frame(surface, narration, RECESS, GOLD)
        self.wrapped_text(surface, session.narration, narration.inflate(-20, -16), TEXT)
        pygame.draw.line(surface, GOLD, narration.midbottom, player.midtop, 2)
        dim = pygame.Surface(CARD_RECTS[0].size, pygame.SRCALPHA)
        dim.fill((7, 9, 18, 130))
        for index in ((1, 2) if session.lesson in (0, 1, 3) else (0, 1, 2)):
            surface.blit(dim, CARD_RECTS[index])
        focus = CARD_RECTS[0] if session.lesson == 0 else ROTATE_RECT if session.lesson == 1 and (
            session.selected_card is None or not session.selected_card.doors[3]
        ) else cell_rect(session.lesson_target) if session.lesson_target is not None else None
        if focus is not None:
            pulse = 3 + pygame.time.get_ticks() // 220 % 3
            pygame.draw.rect(surface, GOLD, focus.inflate(-4, -4), pulse, border_radius=7)
            pygame.draw.circle(surface, GOLD, (focus.centerx, focus.top - 7), 5 + pulse // 2)
        if session.lesson == 1 and session.selected_card is not None:
            preview = session.geometry_preview(session.BUILD)
            if preview[0]:
                rect = cell_rect(session.BUILD).inflate(-8, -8)
                ghost = pygame.Surface(rect.size, pygame.SRCALPHA)
                self.tile_art(ghost, ghost.get_rect(), session.selected_card.doors, TEAL)
                ghost.set_alpha(130)
                surface.blit(ghost, rect)
                pygame.draw.line(surface, GOLD, cell_rect(session.level.start.pos).midright,
                                 cell_rect(session.BUILD).midleft, 5)
        if session.lesson == 4:
            for room in (*session.level.altars, session.level.core):
                pygame.draw.rect(surface, GOLD, cell_rect(room.pos).inflate(-6, -6), 2, border_radius=8)

    def context_tip(self, surface, message):
        panel = pygame.Rect(986, 574, 262, 66)
        stone_frame(surface, panel, RECESS, GOLD)
        self.wrapped_text(surface, message, panel.inflate(-20, -16), GOLD)

    def tool_inventory(self, surface, session, seal_direction, chisel_mode):
        for name, rect, label, _ in TOOL_SLOTS:
            limit = getattr(session.tools, name).max_uses_per_game
            count = limit - session.tool_uses[name]
            enabled = session.medkit_preview()[0] if name == "medkit" else session.tool_budget(name)[0]
            if name == "door_seal":
                enabled = enabled and session.selected_card is not None
            active = (name == "door_seal" and seal_direction is not None) or (name == "emergency_chisel" and chisel_mode)
            stone_frame(surface, rect, PANEL if enabled else RECESS, GOLD if active else LINE)
            icon = self.tool_icons[name]
            surface.blit(icon, icon.get_rect(center=(rect.x+21, rect.centery)))
            if name == "door_seal" and seal_direction is not None:
                label = Message("Seal {side} [F]", side="NESW"[seal_direction])
            self.text(surface, label, (rect.x+42, rect.y+8), GOLD if active else TEXT, self.small_font)
            self.text(surface, Message("Uses: {left}/{limit}", left=count, limit=limit),
                      (rect.x+42, rect.y+34), TEAL if count else MUTED, self.small_font)

    def build_position_preview(self, surface, destination, guard_step):
        room = cell_rect(destination)
        surface.blit(self.explorer_preview, self.explorer_preview.get_rect(center=room.center))
        caption = self.small_font.render(self.t("After build"), True, TEXT, RECESS)
        surface.blit(caption, caption.get_rect(midbottom=(room.centerx, room.bottom - 4)))
        if guard_step is not None:
            # Offset the boot prints so the player remains visible when the guard follows.
            room = cell_rect(guard_step)
            for dx, dy in ((0, 0), (8, -5)):
                sole = pygame.Rect(room.right - 26 + dx, room.bottom - 20 + dy, 6, 10)
                pygame.draw.rect(surface, RECESS, sole.inflate(4, 4), border_radius=3)
                pygame.draw.ellipse(surface, GOLD, sole)
                pygame.draw.line(surface, RECESS, (sole.left, sole.bottom-4), (sole.right, sole.bottom-4))

    def tool_hover(self, surface, session, pos):
        for name, rect, label, instruction in TOOL_SLOTS:
            if rect.collidepoint(pos):
                panel = pygame.Rect(985, 570, 263, 74)
                stone_frame(surface, panel, RECESS, GOLD)
                cost = getattr(session.tools, name).cost_supplies
                self.text(surface, Message("{tool}  |  {cost} supplies", tool=label, cost=cost),
                          (panel.x+9, panel.y+7), GOLD, self.small_font)
                self.wrapped_text(surface, instruction, pygame.Rect(panel.x+9, panel.y+25, 245, 48))
                break

    def tile_art(self, surface, rect, doors, color=TEAL, *, special=None, card=False):
        tiles = self.card_tiles if card else self.room_tiles
        sprite = tiles.get(doors if special is None else (special, doors))
        if sprite is None:
            # Keep a schematic for custom layouts without corresponding artwork.
            self.room(surface, rect, doors, color)
        else:
            surface.blit(sprite, sprite.get_rect(center=rect.center))

    def terrain_art(self, surface, rect, tile, occupied=False):
        if tile.kind == "rubble":
            surface.blit(self.vine_tile, self.vine_tile.get_rect(center=rect.center))
            return
        self.tile_art(surface, rect, tile.doors)
        kind = tile.kind if tile.kind in ("spring", "bell") else tile.event_icon
        art = self.spent_encounters if tile.event_resolved and not tile.special_state else self.encounter_art
        center = (rect.centerx + 19, rect.centery + 9) if occupied else rect.center
        sprite = art[kind]
        surface.blit(sprite, sprite.get_rect(center=center))

    def card_event_odds(self, surface, rect, weights):
        """Show the room template's distribution, shared by every card of its kind."""
        names = {"supply": "Supplies", "danger": "Trap", "neutral": "Quiet", "relic": "Special"}
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
            if name in self.event_badges:
                icon = self.event_badges[name]
                surface.blit(icon, icon.get_rect(center=(x + 8, y)))
            elif name != "neutral":
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
        tokens = re.findall(r"[A-Za-z0-9_]+|\s+|.", message)
        for font in (self.font, self.small_font):
            spacing = max(font.get_linesize(), 17)
            capacity = max(1, rect.height // spacing)
            lines = [""]
            for word in tokens:
                candidate = lines[-1] + word
                if font.size(candidate)[0] > rect.width and lines[-1]:
                    lines.append(word.lstrip())
                else:
                    lines[-1] = candidate
            if len(lines) <= capacity or font is self.small_font:
                break
        for index, line in enumerate(lines[:capacity]):
            if index == capacity - 1 and len(lines) > capacity:
                line = self.fit_text(line.rstrip() + "...", rect.width, font)
            self.text(surface, self.fit_text(line.rstrip(), rect.width, font),
                      (rect.x, rect.y + index * spacing), color, font)

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

        reachable = reachable_rooms(session.board, session.player_pos)
        well = next(((r, c) for r, row in enumerate(session.board) for c, tile in enumerate(row)
                     if (r, c) in reachable and tile.kind == "spring" and not tile.event_resolved
                     and (not hasattr(session, "visible") or session.visible((r, c)))), None)
        medkit = hasattr(session, "medkit_preview") and session.medkit_preview()[0]
        if well is not None:
            hint = Message("Medkit [M] or free well {cell}" if medkit else "Well {cell} heals 1 HP", cell=cell_label(well))
        else:
            hint = "Medkit [M] heals 1 HP" if medkit else "Watch for traps"
        panel = pygame.Rect(945, 80, 303, 28)
        stone_frame(surface, panel, (47, 30, 39), accent)
        self.text(surface, "1 HP LEFT" if critical else "LOW HP", (955, 85), accent, self.small_font)
        self.text(surface, hint, (1048, 85), TEXT, self.small_font)

    def guard_panel(self, surface, session):
        stone_frame(surface, (20, 251, 181, 122), RECESS)
        awake = session.guard_pos is not None
        limit = session.level.guard_build_limit
        remaining = limit - session.build_turn
        accent = RED if awake or remaining == 1 else GOLD
        self.text(surface, "Guard awake" if awake else "Guard alert", (33, 262), accent, self.heading_font)
        if awake:
            cause = ("An altar echoes." if session.guard_wake_reason == "altar" else "The stonework echoes.")
            self.text(surface, cause, (33, 293), TEXT, self.small_font)
            self.text(surface, "Armored steps follow you.", (33, 316), TEXT, self.small_font)
            if session.guard_next is not None and session.visible(session.guard_next):
                self.text(surface, Message("Next step: {cell}", cell=cell_label(session.guard_next)),
                          (33, 343), GOLD, self.small_font)
            return
        counter = f"{session.build_turn}/{limit}"
        self.text(surface, counter, (188 - self.small_font.size(counter)[0], 269), TEXT, self.small_font)
        track = pygame.Rect(33, 295, 154, 10)
        pygame.draw.rect(surface, LINE, track, border_radius=3)
        width = round(track.width * session.build_turn / limit)
        if width:
            pygame.draw.rect(surface, accent, (track.x, track.y, width, track.height), border_radius=3)
        self.text(surface, "One more room wakes it!" if remaining == 1 else "Each build stirs the guard.",
                  (33, 316), accent if remaining == 1 else TEXT, self.small_font)
        self.text(surface, "Full bar or altar link: awake.", (33, 343), MUTED, self.small_font)

    def supply_chest(self, surface, pos, player_pos, notification, age_ms):
        """Derive an opened chest from persisted resolution, including older rooms."""
        active = notification is not None and notification.category == "supply" and notification.pos == pos
        frame = self.chest_frames[-1]
        if active and 0 <= age_ms < CHEST_OPEN_MS:
            frame = self.chest_frames[min(3, age_ms * 4 // CHEST_OPEN_MS)]
        rect = cell_rect(pos)
        center = (rect.centerx + 19, rect.centery + 10) if pos == player_pos else rect.center
        surface.blit(frame, frame.get_rect(center=center))

    def cache_prompt(self, surface, session):
        panel = cache_prompt_rect(session.player_pos)
        gain = session.cache_gain
        enabled = session.resources.hp > 1 and gain > 0
        cell = cell_rect(session.player_pos)
        pygame.draw.rect(surface, GOLD, cell.inflate(-6, -6), 2, border_radius=6)
        stone_frame(surface, panel, RECESS, GOLD)
        self.text(surface, "Barbed chest", (panel.x + 10, panel.y + 6), GOLD, self.small_font)
        self.button(surface, cache_button_rect(session.player_pos), "Open chest  [E]", enabled)
        detail = Message("Pay 1 HP for {gain} Supplies, or leave it here.", gain=gain)
        if session.resources.hp <= 1:
            detail = "Need at least 2 HP"
        elif not gain:
            detail = "Supplies full"
        self.text(surface, detail, (panel.x + 10, panel.y + 34), TEXT, self.small_font)
        self.text(surface, "Barbed wire binds a ration chest.", (panel.x + 10, panel.y + 58), TEXT, self.small_font)
        self.button(surface, event_close_rect(session.player_pos), "Close")

    def encounter_prompt(self, surface, session, elapsed):
        kind, pos = session.encounter, session.player_pos
        panel = event_panel_rect(pos)
        stone_frame(surface, panel, RECESS, EVENT_COLORS[kind])
        surface.blit(self.event_badges[kind], (panel.x + 10, panel.y + 9))
        self.text(surface, ENCOUNTERS[kind], (panel.x + 36, panel.y + 7), GOLD)
        self.button(surface, event_close_rect(pos), "Close")
        if kind == "monster":
            if elapsed is None:
                description = "Green blocks. Gold counters for 2 supplies. Miss: lose 1 HP."
                labels = ("[J] Lure: 1 supply", "[K] Start block")
            else:
                self.text(surface, "Green: block    Gold: counter", (panel.x+12, panel.y+31), TEXT, self.small_font)
                bar = pygame.Rect(panel.x + 12, panel.y + 57, panel.width - 24, 8)
                pygame.draw.rect(surface, LINE, bar)
                zone = bar.copy()
                zone.left += bar.width * BLOCK_START_MS // BLOCK_END_MS
                zone.width = bar.right - zone.left
                pygame.draw.rect(surface, BUILD_GREEN, zone)
                gold_start = bar.x + bar.width * PERFECT_START_MS // BLOCK_END_MS
                gold_end = bar.x + bar.width * PERFECT_END_MS // BLOCK_END_MS
                pygame.draw.rect(surface, GOLD, (gold_start, bar.y-2, gold_end-gold_start, bar.height+4))
                x = bar.x + min(bar.width - 1, elapsed * bar.width // BLOCK_END_MS)
                pygame.draw.line(surface, TEXT, (x, bar.top-3), (x, bar.bottom+2), 3)
                keycap = block_key_rect(pos)
                accent = GOLD if PERFECT_START_MS <= elapsed < PERFECT_END_MS else (
                    BUILD_GREEN if BLOCK_START_MS <= elapsed < BLOCK_END_MS else TEXT)
                stone_frame(surface, keycap, PANEL, accent)
                pygame.draw.line(surface, LINE, (keycap.left+8, keycap.bottom-4),
                                 (keycap.right-8, keycap.bottom-4), 2)
                label = self.heading_font.render(self.t("SPACE  |  Block"), True, accent)
                surface.blit(label, label.get_rect(center=keycap.center))
                return
        elif kind == "casino":
            description = "The dealer lays out two welcome cards. Turn one over for a gift."
            labels = ("[J] Hearts: +1 HP", "[K] Diamonds: +1 supply")
        else:
            description = "Ring the bell to gain 1 maximum HP."
            labels = ("[J] Ring: +1 max HP",)
        self.wrapped_text(surface, description, pygame.Rect(panel.x+12, panel.y+32, panel.width-24, 39))
        for i, label in enumerate(labels):
            enabled = kind != "monster" or elapsed is not None or i or session.resources.supplies > session.resources.supplies_min
            self.button(surface, choice_rects(pos)[i], label, enabled)

    def event_toast(self, surface, notification, age_ms, avoid_rect=None):
        """Draw transient event flash, source marker and actual resource changes."""
        color = EVENT_COLORS.get(notification.category, MUTED)
        quiet = notification.category == "neutral"
        flash = max(0, 42 - age_ms * 42 // 500) if age_ms < 500 and not quiet else 0
        if flash:
            glow_width = 2 + flash // 14
            pygame.draw.rect(surface, color, BOARD_RECT.inflate(4, 4),
                             width=glow_width, border_radius=12)

        source = cell_rect(notification.pos).inflate(-4, -4)
        if not quiet:
            pulse = 3 + (age_ms // 90) % 4
            pygame.draw.rect(surface, RECESS, source.inflate(pulse + 3, pulse + 3), width=5, border_radius=9)
            pygame.draw.rect(surface, color, source.inflate(pulse, pulse), width=4, border_radius=8)
        if notification.category == "supply" and age_ms < 1000:
            gain = notification.supplies_delta
            if notification.icon == "herb":
                label = "Healing herbs"
            else:
                label = Message("Supplies +{amount}", amount=gain) if gain else "Supplies full"
            rendered = self.small_font.render(self.t(label), True, GOLD)
            position = rendered.get_rect(midbottom=(source.centerx, source.top + 8 - min(age_ms, 550) // 35))
            position.clamp_ip(BOARD_RECT)
            pygame.draw.rect(surface, RECESS, position.inflate(6, 4), border_radius=3)
            surface.blit(rendered, position)

        if not needs_event_panel(notification):
            self.event_panel(surface, notification, age_ms=age_ms)

    def event_panel(self, surface, notification, *, age_ms=None):
        rect = event_panel_rect(notification.pos)
        compact = age_ms is not None
        if compact:
            rect.height = 82
        toast = pygame.Surface(rect.size, pygame.SRCALPHA)
        color = EVENT_COLORS.get(notification.category, MUTED)
        stone_frame(toast, toast.get_rect(), (*PANEL, 246), color)

        category = "SPECIAL EVENT" if notification.category == "relic" else notification.category.replace("_", " ").upper()
        kind = notification.icon or notification.category
        badge = self.encounter_art.get(kind) if not compact else None
        badge = badge if badge is not None else self.event_badges.get(kind)
        inset = 18
        if badge is not None:
            if not compact and kind in self.encounter_art:
                stone_frame(toast, (10, 11, 44, 46), RECESS, color)
                toast.blit(badge, badge.get_rect(center=(32, 34)))
                inset = 62
            else:
                toast.blit(badge, badge.get_rect(center=(26, 17)))
                inset = 42
        self.text(toast, category, (inset, 11), color, self.small_font)
        body_x = inset if inset == 62 else 14
        self.wrapped_text(toast, notification.message,
                          pygame.Rect(body_x, 32, rect.width - body_x - 14, 32 if compact else 57), TEXT)
        left = 18
        delta_y = rect.height - 17
        for name, delta, unit in (("health", notification.hp_delta, "HP"),
                                  ("supply", notification.supplies_delta, "Supplies")):
            if delta:
                icon = self.status_icons[name]
                icon_rect = icon.get_rect(midleft=(left, delta_y))
                toast.blit(icon, icon_rect)
                label = self.t(Message("{delta:+d} {unit}", delta=delta, unit=unit))
                area = pygame.Rect((0, 0), self.small_font.size(label))
                area.midleft = (icon_rect.right + 5, delta_y)
                self.text(toast, label, area.topleft, TEAL if delta > 0 else RED, self.small_font)
                left = area.right + 16
        if notification.loops_closed:
            self.text(toast, loop_label(notification), (left, delta_y - 9), GOLD, self.small_font)
        elif not notification.hp_delta and not notification.supplies_delta:
            self.text(toast, "No resource change" if notification.icon == "herb" or notification.category != "supply" else "Supplies full",
                      (18, delta_y - 9), MUTED, self.small_font)
        if compact:
            toast.set_alpha(min(255, max(0, EVENT_FEEDBACK_MS - age_ms) * 255 // 650))
        surface.blit(toast, rect)
        if not compact:
            self.button(surface, event_close_rect(notification.pos), "Close")

    def help_overlay(self, surface, page=0, endless=None):
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
            if endless and heading in ("DOOR SEAL", "CHISEL"):
                tools = endless.session.tools
                if heading == "DOOR SEAL":
                    description = Message("Press F to seal a door when building. Cost: {cost} supplies. Floor limit: {uses}.",
                                          cost=tools.door_seal.cost_supplies, uses=tools.door_seal.max_uses_per_game)
                else:
                    description = Message("Press C and click a neighboring shared wall. Cost: {cost} supplies. Floor limit: {uses}.",
                                          cost=tools.emergency_chisel.cost_supplies, uses=tools.emergency_chisel.max_uses_per_game)
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
                if index == 0:
                    pygame.draw.rect(surface, color, (x-5, 540, 11, 11), 2)
                elif index == 1:
                    pygame.draw.polygon(surface, color, [(x-4,539),(x+5,545),(x-4,551)])
                elif index == 2:
                    surface.blit(self.event_badges["altar"], (x-9,536))
                else:
                    surface.blit(self.event_badges["danger"], (x-9,536))
                self.text(surface, label, (x + 12, 538), MUTED, self.small_font)
            self.wrapped_text(surface, "Link an altar or fill the guard alert bar to wake the guard. Each walk or build moves it along the arrow. A hit costs 1 HP and sends it back to Start.",
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
            self.wrapped_text(surface, "Close the gold side of this U. Seed 42: build A3 (card 1, R), walk back to A4, build B4 (card 2, Q), then B3 (card 1, R twice).",
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
             help_open: bool = False, help_page: int = 0, event_feedback=None, feedback_age: int = 0,
             pending_plan=None, auto_walking: bool = False, nav_pause_reason: str | None = None,
             endless=None):
        mvp = hasattr(session, "level")
        fog = mvp and session.fog_turns > 0
        if fog and hovered_pos is not None and not session.visible(hovered_pos):
            hovered_pos = None
        terminal = getattr(session, "status", "PLAYING") in ("WON", "LOST") or bool(endless and endless.ended)
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
        map_label = (Message("Endless · Floor {floor}", floor=endless.floor) if endless
                     else Message("MAP  |  {rooms} / 49 ROOMS", rooms=rooms))
        self.text(surface, map_label, (238, 90), MUTED, self.small_font)
        seed_label = self.fit_text(Message("Seed {seed}", seed=endless.seed if endless else session.seed),
                                   180, self.small_font)
        if mvp and session.guard_pos is not None and not terminal:
            threatened = session.guard_next == session.player_pos
            self.text(surface, "Guard targets your room" if threatened else "Guard moves on walk / build",
                      (385, 90), RED if threatened else GOLD, self.small_font)
        self.text(surface, Message("Mist: {n} builds", n=session.fog_turns) if fog else seed_label,
                  (582, 90), GOLD if fog else MUTED, self.small_font)
        self.text(surface, "CHOOSE A ROOM", (806, 86), PURPLE, self.small_font)
        if 0 < resources.hp <= 2 and not terminal and not help_open:
            self.low_health_warning(surface, session)
        legal = (session.legal_cells_with_seal(seal_direction) if seal_direction is not None
                 else session.legal_cells())
        planning = ((session.planning_cells_with_seal(seal_direction) if seal_direction is not None
                     else session.planning_cells()) if mvp and session.selected_card is not None else set())
        reachable = reachable_rooms(session.board, session.player_pos) if mvp else set()
        build_region = (reachable_rooms(session.board, session.player_pos, (session.guard_pos,))
                        if mvp and session.guard_pos is not None else reachable)
        frontier = frontier_cells(session.board, build_region) if mvp else set()
        altar_positions = {altar.pos: index + 1 for index, altar in enumerate(session.level.altars)} if mvp else {}
        lantern_phase = pygame.time.get_ticks() // 75 % len(self.traveler_frames)
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
                    if tile.kind in ("rubble", "spring", "bell") or tile.event_icon in ENCOUNTERS:
                        self.terrain_art(surface, rect, tile, pos == session.player_pos)
                    else:
                        self.tile_art(surface, rect, tile.doors, color, special=special)
                    if pos == session.player_pos:
                        light = self.lantern_lights[lantern_phase]
                        surface.blit(light, light.get_rect(center=rect.center))
                    if tile.kind == "start":
                        self.text(surface, "S", (rect.left + 7, rect.top + 5), GOLD, self.small_font)
                    elif pos in altar_positions:
                        self.text(surface, f"A{altar_positions[pos]}", (rect.left + 7, rect.top + 5), color, self.small_font)
                    elif mvp and pos == session.level.core.pos:
                        if not session.core_unlocked:
                            # Keep matching sockets visible for building, but bar each entrance.
                            for side, (x, y) in enumerate((rect.midtop, rect.midright, rect.midbottom, rect.midleft)):
                                if not tile.doors[side]:
                                    continue
                                horizontal = side in (0, 2)
                                gate = pygame.Rect(0, 0, 26 if horizontal else 9, 9 if horizontal else 26)
                                gate.center = (x, y)
                                gate.clamp_ip(rect)
                                pygame.draw.rect(surface, RECESS, gate)
                                pygame.draw.rect(surface, RED, gate, 1)
                                for offset in (-8, 0, 8):
                                    if horizontal:
                                        pygame.draw.line(surface, STEEL, (x+offset, gate.top+1), (x+offset, gate.bottom-2), 2)
                                    else:
                                        pygame.draw.line(surface, STEEL, (gate.left+1, y+offset), (gate.right-2, y+offset), 2)
                        self.text(surface, "C+" if session.core_unlocked else "C-",
                                  (rect.left + 7, rect.top + 5), color, self.small_font)
                    elif (tile.event_category == "supply" or tile.event_icon == "supply") and (
                        tile.event_resolved and not tile.trapped_cache
                    ):
                        self.supply_chest(surface, pos, session.player_pos, event_feedback, feedback_age)
                    elif tile.event_icon not in ENCOUNTERS and (marker := persistent_event_marker(tile)) is not None and (
                        icon := self.room_events.get(marker)
                    ) is not None:
                        center = (rect.centerx + 17, rect.centery + 9) if pos == session.player_pos else rect.center
                        surface.blit(icon, icon.get_rect(center=center))
                    elif tile.event_category and tile.event_category != "neutral":
                        pygame.draw.circle(surface, MUTED, (rect.right - 9, rect.bottom - 9), 3)
                elif fits:
                    surface.blit(self.legal_tint, rect)
                    pygame.draw.rect(surface, BUILD_GREEN, rect, width=2)
                elif pos in planning:
                    pygame.draw.rect(surface, (*TEAL, 35), rect, width=1)
                    dash = 8
                    for x in range(rect.left, rect.right, dash * 2):
                        pygame.draw.line(surface, TEAL, (x, rect.top), (min(x + dash, rect.right), rect.top), 2)
                        pygame.draw.line(surface, TEAL, (x, rect.bottom), (min(x + dash, rect.right), rect.bottom), 2)
                    for y in range(rect.top, rect.bottom, dash * 2):
                        pygame.draw.line(surface, TEAL, (rect.left, y), (rect.left, min(y + dash, rect.bottom)), 2)
                        pygame.draw.line(surface, TEAL, (rect.right, y), (rect.right, min(y + dash, rect.bottom)), 2)
                elif pos in frontier:
                    pygame.draw.circle(surface, TEAL, rect.center, 3)
                else:
                    surface.blit(self.unknown_mark, self.unknown_mark.get_rect(center=rect.center))
                if chisel_mode and tile is not None and session.chisel_preview(session.player_pos, pos)[0]:
                    pygame.draw.rect(surface, GOLD, rect, width=2, border_radius=7)
        if pending_plan is not None:
            route_points = [cell_rect(pos).center for pos in pending_plan.path]
            if len(route_points) > 1:
                pygame.draw.lines(surface, TEAL, False, route_points, 4)
            for point in route_points:
                pygame.draw.circle(surface, RECESS, point, 7)
                pygame.draw.circle(surface, TEAL, point, 5)
            entry_rect = cell_rect(pending_plan.entry).inflate(-15, -15)
            pygame.draw.rect(surface, GOLD, entry_rect, width=3, border_radius=9)
            target_rect = cell_rect(pending_plan.target).inflate(-5, -5)
            blueprint = pygame.Surface(target_rect.size, pygame.SRCALPHA)
            card = session.selected_card
            if card is not None:
                doors = tuple(False if side == pending_plan.seal_direction else value
                              for side, value in enumerate(card.doors))
                self.tile_art(blueprint, blueprint.get_rect(), doors, TEAL)
                blueprint.set_alpha(105)
            else:
                blueprint.fill((*TEAL, 45))
            surface.blit(blueprint, target_rect)
            pygame.draw.rect(surface, GOLD, target_rect, width=3, border_radius=8)
        for index in range(BOARD_SIZE):
            self.text(surface, chr(ord('A') + index),
                      (cell_rect((0, index)).centerx - 5, BOARD_RECT.top - 15), MUTED, self.small_font)
            self.text(surface, str(index + 1), (BOARD_RECT.left - 18, BOARD_RECT.top + index * CELL_SIZE + 28),
                      MUTED, self.small_font)
        stone_frame(surface, (20, 86, 181, 159), RECESS)
        self.text(surface, "Objectives", (33, 102), TEXT, self.heading_font)
        if mvp:
            for index, altar in enumerate(session.level.altars[:2]):
                active = altar.kind in session.activated_altars
                self.objective_chip(surface, pygame.Rect(33, 129 + index * 31, 155, 28),
                                    Message("A{index} {cell}", index=index + 1, cell=cell_label(altar.pos)
                                            if not fog or session.visible(altar.pos) else "?"),
                                    "ACTIVE" if active else "IDLE", GOLD if active else PURPLE)
            self.objective_chip(surface, pygame.Rect(33, 191, 155, 28),
                                Message("CORE {cell}", cell=cell_label(session.level.core.pos)
                                        if not fog or session.visible(session.level.core.pos) else "?"),
                                "OPEN" if session.core_unlocked else "LOCKED",
                                TEAL if session.core_unlocked else RED)
            self.text(surface, Message("Loops closed   {count}", count=session.loops_closed), (37, 223), GOLD, self.small_font)
            self.guard_panel(surface, session)
        else:
            self.text(surface, "Explore the ruins", (33, 148), MUTED)
        stone_frame(surface, (20, 379, 181, 146), RECESS)
        if pending_plan is not None:
            self.text(surface, "Build plan", (33, 385), TEXT, self.heading_font)
            self.text(surface, Message("Target {cell}", cell=cell_label(pending_plan.target)), (33, 412), GOLD, self.small_font)
            self.text(surface, Message("Entrance {cell}", cell=cell_label(pending_plan.entry)), (33, 430), TEAL, self.small_font)
            self.text(surface, Message("Steps {steps}", steps=pending_plan.steps), (33, 448), TEXT, self.small_font)
            self.button(surface, PLAN_GO_RECT, "Pause" if auto_walking else "Go [G]")
            self.button(surface, PLAN_CANCEL_RECT, "Cancel")
            threatened = any(pos in (session.guard_pos, session.guard_next) for pos in pending_plan.path[1:])
            note = "Guard threat on route" if threatened else "Each step moves guard"
            if pending_plan.steps == 0:
                note = "Ready — Enter to build"
            self.text(surface, note, (33, 508), RED if threatened else MUTED, self.small_font)
        else:
            self.text(surface, "Map key", (33, 385), TEXT, self.heading_font)
            legend = [("Built room", STEEL), ("Can build", BUILD_GREEN), ("Plan only", TEAL), ("Landmark", PURPLE)]
            if mvp:
                legend.extend((("Vine spires", VINE_SPIRES), ("Ancient bell", GOLD)
                               if session.level.well_kind == "bell" else ("Healing well", SPRING)))
            for index, (label, color) in enumerate(legend):
                y = 412 + index * 18
                pygame.draw.rect(surface, color, (34, y, 13, 13), width=1 if index in (1, 2) else 0)
                self.text(surface, label, (58, y), TEXT, self.small_font)
        stone_frame(surface, (20, 531, 181, 177), RECESS)
        self.text(surface, "Map overview", (33, 536), TEXT, self.heading_font)
        for row, tiles in enumerate(session.board):
            for col, tile in enumerate(tiles):
                box = pygame.Rect(44 + col * 19, 563 + row * 19, 17, 17)
                pos = (row, col)
                if fog and not session.visible(pos):
                    surface.blit(mist_texture(), box, (col * 27, row * 23, box.width, box.height))
                    continue
                color = STEEL if tile else LINE
                if pos == session.player_pos:
                    color = GOLD
                elif mvp and pos == session.level.core.pos:
                    color = BUILD_GREEN if session.core_unlocked else RED
                elif pos in altar_positions:
                    color = PURPLE
                elif tile and tile.kind == "rubble":
                    color = VINE_SPIRES
                elif tile and tile.kind == "spring" and not tile.event_resolved:
                    color = SPRING
                elif pos in legal:
                    color = BUILD_GREEN
                pygame.draw.rect(surface, color, box, width=0 if tile else 1)
                if mvp and pos == session.level.core.pos and not session.core_unlocked:
                    pygame.draw.rect(surface, RECESS, box.inflate(-3, -3))
                    pygame.draw.line(surface, RED, box.topleft, box.bottomright, 2)
                    continue
                if tile:
                    for door, tip in zip(tile.doors, (box.midtop, box.midright, box.midbottom, box.midleft)):
                        if door:
                            pygame.draw.line(surface, RECESS, box.center, tip, 2)
        faces_sealed_core = False
        new_loops = 0
        seals_exits = False
        wakes_guard = False
        if hovered_pos is not None:
            occupied = session.board[hovered_pos[0]][hovered_pos[1]] is not None
            walking = occupied and hovered_pos != session.player_pos
            if chisel_mode:
                ok, reason = session.chisel_preview(session.player_pos, hovered_pos)
                if ok:
                    new_loops = int(hovered_pos in reachable_rooms(session.board, session.player_pos))
                    if session.guard_pos is None and not new_loops:
                        other_side = reachable_rooms(session.board, hovered_pos)
                        wakes_guard = any(altar.pos in other_side for altar in session.level.altars)
            elif walking:
                ok, reason = session.movement_preview(hovered_pos)
            elif seal_direction is not None:
                ok, reason = session.preview_with_seal(hovered_pos, seal_direction)
                if not ok and session.geometry_preview_with_seal(hovered_pos, seal_direction)[0]:
                    ok, reason = True, "not_at_build_frontier"
            else:
                ok, reason = session.preview(hovered_pos)
                if mvp and not ok and session.geometry_preview(hovered_pos)[0]:
                    ok, reason = True, "not_at_build_frontier"
            rect = cell_rect(hovered_pos).inflate(-4, -4)
            card = session.selected_card
            if card is not None and not chisel_mode and session.board[hovered_pos[0]][hovered_pos[1]] is None:
                doors = tuple(False if side == seal_direction else value for side, value in enumerate(card.doors))
                self.tile_art(surface, rect, doors, TEAL if ok else RED)
                if ok and mvp:
                    core = session.level.core
                    faces_sealed_core = not session.core_unlocked and session.visible(core.pos) and any(
                        doors[side] and neighbor_pos(*hovered_pos, side) == core.pos and core.doors[OPPOSITE[side]]
                        for side in DIRECTIONS
                    )
                    new_loops = loops_closed_by_room(session.board, hovered_pos, doors)
                    seals_exits, wakes_guard = session.build_warnings(hovered_pos, doors)
            border = (TEAL if reason == "not_at_build_frontier" else BUILD_GREEN if ok else RED) if card is not None or walking or chisel_mode else MUTED
            pygame.draw.rect(surface, border, rect, width=3, border_radius=7)
        else:
            reason = "no_normal_placement" if session.blocked else "no_card_selected"
        if mvp and session.core_unlocked and not terminal:
            unlock_age = feedback_age if event_feedback is not None and event_feedback.category == "altar" else None
            portal_effect(surface, cell_rect(session.level.core.pos), pygame.time.get_ticks(), unlock_age)
        if event_feedback is not None and not terminal:
            clip = surface.get_clip()
            surface.set_clip(BOARD_RECT.clip(clip))
            event_effect(surface, cell_rect(event_feedback.pos), event_feedback, feedback_age, self.room_events)
            surface.set_clip(clip)
        if mvp and session.guard_pos is not None and not terminal:
            guard = cell_rect(session.guard_pos)
            if session.guard_next is not None:
                target = cell_rect(session.guard_next)
                ring = target.inflate(-8, -8)
                pygame.draw.rect(surface, RECESS, ring.inflate(4, 4), width=6, border_radius=7)
                pygame.draw.rect(surface, GOLD, ring, width=3, border_radius=6)
                direction = (pygame.Vector2(target.center) - guard.center).normalize()
                side = direction.rotate(90)
                tip = pygame.Vector2(target.center) - direction * 17
                neck = tip - direction * 17
                tail = tip - direction * 37
                arrow = [tip, neck + side * 12, neck + side * 5, tail + side * 5,
                         tail - side * 5, neck - side * 5, neck - side * 12]
                pygame.draw.polygon(surface, GOLD, arrow)
                pygame.draw.polygon(surface, RECESS, arrow, width=2)
            center = guard.center if session.player_pos != session.guard_pos else (guard.right - 23, guard.top + 26)
            surface.blit(self.guard_sprite, self.guard_sprite.get_rect(center=center))
        player_center = cell_rect(session.player_pos).center
        explorer = self.traveler_frames[lantern_phase]
        surface.blit(explorer, explorer.get_rect(center=player_center))
        if mvp and not (chisel_mode or terminal or help_open):
            destination = hovered_pos
            if destination not in legal and pending_plan is not None and pending_plan.steps == 0:
                destination = pending_plan.target
            if destination in legal:
                step = session.guard_next
                self.build_position_preview(surface, destination, step if step and session.visible(step) else None)
        if fog:
            clouds = mist_texture()
            tick = pygame.time.get_ticks()
            for row in range(BOARD_SIZE):
                for col in range(BOARD_SIZE):
                    if not session.visible((row, col)):
                        area = cell_rect((row, col))
                        x = (col * CELL_SIZE + tick // 90) % (clouds.get_width() // 2)
                        y = (row * CELL_SIZE + tick // 220) % (clouds.get_height() // 2)
                        surface.blit(clouds, area, (x, y, area.width, area.height))

        event_weights = {room.kind: room.event_weights for room in session.config.room_types}
        for index, card in enumerate(session.draw_result.cards):
            rect = CARD_RECTS[index]
            selected = session.selected_index == index
            stone_frame(surface, rect, (45, 39, 67) if selected else PANEL,
                        GOLD if selected else LINE, cut=10)
            stone_frame(surface, (rect.x + 9, rect.y + 23, 98, 98), RECESS, cut=10)
            if selected:
                pygame.draw.polygon(surface, GOLD, [(rect.x + 3, rect.centery - 8),
                                                     (rect.x + 10, rect.centery),
                                                     (rect.x + 3, rect.centery + 8)])
            shown = session.card_at(index)
            shown_doors = (tuple(False if side == seal_direction else value for side, value in enumerate(shown.doors))
                           if selected else shown.doors)
            self.tile_art(surface, pygame.Rect(rect.x + 12, rect.y + 26, 92, 92), shown_doors, card=True)
            self.text(surface, ROOM_NAMES.get(card.kind, card.kind.replace('_', ' ').title()),
                      (rect.x + 122, rect.y + 12), font=self.heading_font)
            trait, trait_color = ROOM_TRAITS.get(card.kind, ("Unknown event", MUTED))
            if isinstance(session, TutorialSession):
                trait, trait_color = "Scripted tutorial event", GOLD
            self.text(surface, trait, (rect.x + 122, rect.y + 38), trait_color, self.small_font)
            self.card_event_odds(surface, rect, event_weights[card.kind])
            pygame.draw.line(surface, LINE, (rect.x + 122, rect.y + 107), (rect.right - 16, rect.y + 107))
            if selected and seal_direction is not None:
                playable = bool(planning)
                fit_message = "Seal fits this rotation" if playable else "No fit with this seal"
            else:
                playable = index in session.draw_result.legal_card_indices
                fit_message = "Fits in some rotation" if playable else "No fit on this map"
            self.text(surface, fit_message,
                      (rect.x + 122, rect.y + 117), TEAL if playable else MUTED, self.small_font)
            self.text(surface, Message("Rotation {angle} deg", angle=session.rotations[index] * 90),
                      (rect.right - 112, rect.y + 117), MUTED, self.small_font)
            self.text(surface, str(index + 1), (rect.right - 25, rect.y + 15), GOLD if selected else MUTED)

        sealed = mvp and session.blocked and session.exits_sealed(session.board, session.player_pos)
        blocked_hint = ("All exits are sealed. Press N to restart." if sealed else
                        "No room shape fits your open exits. You can still walk through built rooms or restart.")
        if session.blocked and not session.draw_result.cards:
            rect = pygame.Rect(806, 112, 442, 456)
            stone_frame(surface, rect, RECESS, RED, cut=10)
            self.text(surface, "No normal placement", (830, 270), RED, self.heading_font)
            self.wrapped_text(surface, blocked_hint,
                              pygame.Rect(830, 312, 390, 60), MUTED)

        self.button(surface, ROTATE_RECT, "Rotate  [R]", session.selected_card is not None and not terminal)
        if mvp:
            self.tool_inventory(surface, session, seal_direction, chisel_mode)
        else:
            self.text(surface, "Q rotates counterclockwise", (990, 607), MUTED, self.small_font)
        feedback = message
        if hovered_pos is not None and chisel_mode:
            feedback = tool_message(reason)
        elif hovered_pos is not None and walking:
            feedback = movement_message(reason)
        elif hovered_pos is not None and session.selected_card is not None:
            feedback = (placement_message(reason) if reason == "not_at_build_frontier" or seal_direction is None
                        else tool_message(reason))
        if new_loops:
            feedback = Message("{action} Closes {n} new loop." if new_loops == 1 else "{action} Closes {n} new loops.",
                               action=feedback, n=new_loops)
        if hovered_pos is not None:
            hovered_tile = session.board[hovered_pos[0]][hovered_pos[1]]
            if hovered_tile:
                kind = "bell" if hovered_tile.kind == "bell" else hovered_tile.event_icon
                feedback = ENCOUNTERS.get(kind, feedback)
            if hovered_tile and hovered_tile.kind == "rubble":
                feedback = movement_message("rubble")
            elif hovered_tile and hovered_tile.kind == "spring" and not chisel_mode:
                if hovered_tile.event_resolved:
                    feedback = "The well is dry. The room is still passable."
                elif hovered_pos in reachable:
                    feedback = Message("Well {cell} heals 1 HP", cell=cell_label(hovered_pos))
                else:
                    feedback = "Healing well. Connect a path and enter to recover 1 HP once."
        if sealed:
            feedback = blocked_hint
        elif session.blocked and hovered_pos is None and not chisel_mode:
            feedback = ("No normal room fits. You can walk, use a tool or restart." if mvp
                        else placement_message("no_normal_placement"))
        if session.hp_depleted and not mvp:
            feedback = "HP depleted (0). Press N to restart."
        if seals_exits:
            feedback = "This build will seal the last exit."
        elif wakes_guard:
            feedback = "This action will wake the guard."
        if faces_sealed_core:
            portal_hint = "Portal sealed: build around it to reach the altars."
            feedback = Message("{warning} {portal}", warning=feedback, portal=portal_hint) if seals_exits or wakes_guard else portal_hint
        stone_frame(surface, (218, 660, 565, 48), RECESS)
        self.wrapped_text(surface, feedback, pygame.Rect(230, 665, 540, 44),
                          RED if session.blocked or seals_exits else TEXT)
        footer = ("1/2/3 Select  R/Q Rotate  Click Build/Plan  G Go  Enter Build  Esc Cancel/Quit  F Seal  C Chisel  H Help  N Restart"
                  if mvp else "1/2/3 Select  R/Q Rotate  Click Build/Walk  Arrows/WASD Walk  F11 Fullscreen  N Restart  Esc Quit")
        self.text(surface, footer,
                  (30, 719), MUTED, self.small_font)
        if endless and not terminal:
            self.text(surface, "X ends the run", (1060, 719), MUTED, self.small_font)
        if event_feedback is not None and not terminal and (not fog or session.visible(event_feedback.pos)):
            avoid = cache_prompt_rect(session.player_pos) if session.trapped_cache else None
            self.event_toast(surface, event_feedback, feedback_age, avoid)
        if terminal:
            shade = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)
            shade.fill((5, 11, 17, 205))
            surface.blit(shade, (0, 0))
            panel = pygame.Rect(260, 220, 760, 300)
            won = session.status == "WON"
            color = GOLD if won else RED
            stone_frame(surface, panel, RECESS, color, cut=16)
            pygame.draw.line(surface, LINE, (310, 299), (970, 299))
            title = ("Run ended" if endless and endless.ended else "Floor cleared" if endless and won
                     else "VICTORY" if won else "DEFEAT")
            self.text(surface, title, (310, 252), color, self.title_font)
            seal = self.objects["core-unlocked" if won else "core-locked"]
            surface.blit(seal, seal.get_rect(midright=(969, 270)))
            explanation = ("All altars are active. You reached the unlocked core."
                           if won else "Your HP reached zero. Try a different route or use your tools earlier.")
            if endless:
                explanation = Message("Cleared floors: {count}  |  Run seed: {seed}",
                                      count=endless.completed, seed=endless.seed)
                if session.guard_wake_build is not None:
                    cause = "altar linked" if session.guard_wake_reason == "altar" else "build limit"
                    self.text(surface, Message("Guard woke after {count} builds ({cause}).",
                                               count=session.guard_wake_build, cause=cause),
                              (310, 352), MUTED, self.small_font)
            self.wrapped_text(surface, explanation, pygame.Rect(310, 312, 660, 60))
            self.text(surface, Message("Rooms built: {rooms}   HP: {hp}   Supplies: {supplies}",
                                       rooms=session.build_turn, hp=resources.hp, supplies=resources.supplies),
                      (310, 382), MUTED)
            advance = endless is not None and endless.can_advance
            self.button(surface, END_RESTART_RECT, "Next floor [Enter]" if advance else "Restart  [N]")
            self.text(surface, "X ends the run" if advance else "Esc closes the game",
                      (558, 482), MUTED, self.small_font)
        if help_open:
            self.help_overlay(surface, help_page, endless)
