"""Phase 3 construction sandbox state, independent of pygame.

The sandbox starts at (3, 0) with north/east/south exits. It supports building
and auto-entry only; movement, events, resources and objectives are later work.
"""

from random import Random

from engine.cards import Card, CardConfig, Position, draw_cards, load_card_config
from engine.models import BOARD_SIZE, Tile, make_empty_board
from engine.placement import can_place, frontier_cells, reachable_rooms


START_POS = (BOARD_SIZE // 2, 0)


class BuildSession:
    """Own the board and persistent hand; previews never consume random state."""

    def __init__(self, seed: int = 42, config: CardConfig | None = None):
        self.seed = seed
        self.config = load_card_config() if config is None else config
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
        Event categories are saved on the Tile but no event is resolved here.
        """
        ok, reason = self.preview(pos)
        if not ok:
            return False, reason
        card = self.selected_card
        assert card is not None
        next_board = [row.copy() for row in self.board]
        next_board[pos[0]][pos[1]] = Tile(card.kind, card.doors, event_category=card.event_category)
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
        return True, "ok"
