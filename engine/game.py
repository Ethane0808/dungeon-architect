"""Construction, room entry and first-entry events, independent of pygame.

The sandbox starts at (3, 0) with north/east/south exits. It supports building
and auto-entry, with free walking and bounded resources. Objectives are later work.
"""

from dataclasses import replace
from random import Random

from engine.cards import Card, CardConfig, Position, draw_cards, load_card_config
from engine.directions import DIRECTIONS, OPPOSITE, is_in_bounds, neighbor_pos
from engine.events import EventConfig, EventNotification, load_event_config, resolve_event
from engine.models import BOARD_SIZE, Tile, make_empty_board, validate_board
from engine.placement import can_place, frontier_cells, reachable_rooms
from engine.resources import Resources, load_resources


START_POS = (BOARD_SIZE // 2, 0)


class BuildSession:
    """Own the board and persistent hand; previews never consume random state."""

    def __init__(self, seed: int = 42, config: CardConfig | None = None, *,
                 resources: Resources | None = None, event_config: EventConfig | None = None):
        self.seed = seed
        self.config = load_card_config() if config is None else config
        self.initial_resources = load_resources() if resources is None else resources
        self.event_config = load_event_config() if event_config is None else event_config
        for room in self.config.room_types:
            for category, _ in room.event_weights:
                self.event_config.outcome_for(category)
        self.restart()

    def restart(self) -> None:
        """Reset the entire sandbox with the same seed and initial hand."""
        board = make_empty_board()
        board[START_POS[0]][START_POS[1]] = Tile("start", (True, True, True, False))
        rng = Random(self.seed)
        result = draw_cards(board, START_POS, rng=rng, config=self.config)
        self.board = board
        self.player_pos = START_POS
        self.rng = rng
        self.draw_result = result
        self.build_turn = 0
        self.selected_index: int | None = None
        self.rotations = [0] * len(result.cards)
        self.resources = self.initial_resources
        self.current_event: EventNotification | None = None

    @property
    def hp_depleted(self) -> bool:
        """Expose zero HP for future defeat logic; this phase does not end the game."""
        return self.resources.hp_depleted

    def movement_preview(self, pos: Position) -> tuple[bool, str]:
        """Validate one adjacent step through matching, unlocked doors."""
        validate_board(self.board)
        if not is_in_bounds(*pos, BOARD_SIZE):
            return False, "out_of_bounds"
        if not is_in_bounds(*self.player_pos, BOARD_SIZE):
            return False, "invalid_source"
        direction = next((side for side in DIRECTIONS
                          if neighbor_pos(*self.player_pos, side) == pos), None)
        if direction is None:
            return False, "not_adjacent"
        source = self.board[self.player_pos[0]][self.player_pos[1]]
        target = self.board[pos[0]][pos[1]]
        if source is None or not source.can_traverse():
            return False, "invalid_source"
        if target is None:
            return False, "no_room"
        if target.kind == "rubble":
            return False, "rubble"
        if not source.doors[direction] or not target.doors[OPPOSITE[direction]]:
            return False, "doors_not_connected"
        if not target.can_traverse():
            return False, "room_locked"
        return True, "ok"

    def _prepare_entry(self, tile: Tile, pos: Position) -> tuple[Tile, Resources, EventNotification | None]:
        """Prepare once-only event effects, leaving the live state untouched."""
        if tile.kind in {"start", "altar_a", "altar_b", "core"} or tile.event_resolved or tile.event_category is None:
            return tile, self.resources, None
        resources, notification = resolve_event(tile.event_category, pos, self.resources, self.event_config, self.seed)
        resolved = replace(tile, event_resolved=True, event_icon=notification.icon, trapped_cache=notification.trapped_cache, event_outcome={
            "hp": notification.hp_delta, "supplies": notification.supplies_delta,
        })
        return resolved, resources, notification

    @property
    def trapped_cache(self) -> int:
        row, col = self.player_pos
        tile = self.board[row][col]
        return tile.trapped_cache if tile else 0

    @property
    def cache_gain(self) -> int:
        updated = self.resources.apply(supplies_delta=self.trapped_cache)
        return updated.supplies - self.resources.supplies

    def open_trapped_cache(self) -> bool:
        """Trade one HP for the supplies that fit. Unopened chests survive revisits."""
        if self.resources.hp <= 1 or not self.trapped_cache or not self.cache_gain:
            return False
        row, col = self.player_pos
        tile = self.board[row][col]
        assert tile is not None and tile.event_category is not None
        gain = self.cache_gain
        self.resources = self.resources.apply(hp_delta=-1, supplies_delta=gain)
        self.board[row][col] = replace(tile, trapped_cache=0, event_icon="supply")
        self.current_event = EventNotification(self.player_pos, tile.event_category,
                                               "Wire cuts your hand. The rations are yours.", -1, gain, icon="barbed-cache")
        return True

    def move(self, pos: Position) -> tuple[bool, str]:
        """Walk one step. Preserve cards, rotations, build turns and random state."""
        ok, reason = self.movement_preview(pos)
        if not ok:
            return False, reason
        tile = self.board[pos[0]][pos[1]]
        assert tile is not None
        entered, resources, notification = self._prepare_entry(tile, pos)
        self.board[pos[0]][pos[1]] = entered
        self.player_pos = pos
        self.resources = resources
        if notification is not None:
            self.current_event = notification
        return True, "ok"

    @property
    def blocked(self) -> bool:
        return self.draw_result.status == "blocked"

    def card_at(self, index: int) -> Card:
        return self.draw_result.cards[index].rotated(self.rotations[index])

    @property
    def selected_card(self) -> Card | None:
        return None if self.selected_index is None else self.card_at(self.selected_index)

    def select_card(self, index: int) -> bool:
        if not 0 <= index < len(self.draw_result.cards):
            return False
        self.selected_index = index
        return True

    def rotate_selected(self, times: int = 1) -> bool:
        if self.selected_index is None:
            return False
        self.rotations[self.selected_index] = (self.rotations[self.selected_index] + times) % 4
        return True

    def preview(self, pos: Position) -> tuple[bool, str]:
        """Validate the current orientation against the live board without writes."""
        if self.blocked:
            return False, "no_normal_placement"
        card = self.selected_card
        if card is None:
            return False, "no_card_selected"
        tile = Tile(card.kind, card.doors, event_category=card.event_category)
        return can_place(tile, pos, self.board, reachable_rooms(self.board, self.player_pos))

    def legal_cells(self) -> set[Position]:
        """Return all legal positions for the selected card's current orientation."""
        card = self.selected_card
        if card is None or self.blocked:
            return set()
        reachable = reachable_rooms(self.board, self.player_pos)
        tile = Tile(card.kind, card.doors, event_category=card.event_category)
        return {pos for pos in frontier_cells(self.board, reachable)
                if can_place(tile, pos, self.board, reachable)[0]}

    def place(self, pos: Position) -> tuple[bool, str]:
        """Revalidate, then atomically place/auto-enter/deal the next hand.

        Failed validation preserves board, hand, orientation, turn and RNG. If
        preparing the next draw raises, the previous state and RNG are restored.
        Automatic entry resolves the new room's event before drawing. A failed
        event or draw commits neither the entry nor its resources/notification.
        """
        ok, reason = self.preview(pos)
        if not ok:
            return False, reason
        card = self.selected_card
        assert card is not None
        next_board = [row.copy() for row in self.board]
        tile = Tile(card.kind, card.doors, event_category=card.event_category)
        entered, resources, notification = self._prepare_entry(tile, pos)
        next_board[pos[0]][pos[1]] = entered
        rng_state = self.rng.getstate()
        try:
            next_draw = draw_cards(next_board, pos, rng=self.rng, config=self.config)
        except Exception:
            self.rng.setstate(rng_state)
            raise
        self.board = next_board
        self.player_pos = pos
        self.draw_result = next_draw
        self.build_turn += 1
        self.selected_index = None
        self.rotations = [0] * len(next_draw.cards)
        self.resources = resources
        if notification is not None:
            self.current_event = notification
        return True, "ok"
