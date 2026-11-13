"""Complete MVP loop built on the tested construction/event controller.

BuildSession remains the focused Phase 4 sandbox API. MvpSession adds a validated
fixed level, objective progression, paid spatial tools and terminal states. Each
gameplay operation prepares a private candidate and commits only on success.
"""

from copy import copy
from dataclasses import replace
from enum import Enum
from random import Random

from engine.cards import CardConfig, Position, draw_cards, enumerate_legal_placements
from engine.events import EventConfig, EventNotification
from engine.game import BuildSession
from engine.level import LevelConfig, load_level_config
from engine.models import Tile
from engine.placement import can_place, frontier_cells, reachable_rooms
from engine.resources import Resources
from engine.tools import ToolConfig, chisel_board, chisel_preview, load_tool_config, seal_card


class GameStatus(str, Enum):
    PLAYING = "PLAYING"
    WON = "WON"
    LOST = "LOST"


class MvpSession(BuildSession):
    """Configurable single-level game; balancing and tool rules are provisional."""

    def __init__(self, seed: int = 42, config: CardConfig | None = None, *,
                 resources: Resources | None = None, event_config: EventConfig | None = None,
                 level: LevelConfig | None = None, tools: ToolConfig | None = None):
        self.level = load_level_config() if level is None else level
        self.tools = load_tool_config() if tools is None else tools
        super().__init__(seed, config, resources=resources, event_config=event_config)
        special_ids = {room.kind for room in (self.level.start, *self.level.altars, self.level.core)}
        if special_ids.intersection(room.kind for room in self.config.room_types):
            raise ValueError("Ordinary card kinds cannot overlap level special-room ids")

    def restart(self) -> None:
        board = self.level.make_board()
        rng = Random(self.seed)
        draw = draw_cards(board, self.level.start.pos, rng=rng, config=self.config)
        self.board = board
        self.player_pos = self.level.start.pos
        self.rng = rng
        self.draw_result = draw
        self.build_turn = 0
        self.selected_index = None
        self.rotations = [0] * len(draw.cards)
        self.resources = self.initial_resources
        self.current_event = None
        self.activated_altars: frozenset[str] = frozenset()
        self.tool_uses = {"door_seal": 0, "emergency_chisel": 0}
        self.status = GameStatus.LOST if self.resources.hp_depleted else GameStatus.PLAYING
        self.loss_reason = "HP reached zero." if self.resources.hp_depleted else None
        self.objective_message = "Enter every altar, then reach the unlocked core."

    @property
    def core_unlocked(self) -> bool:
        return all(altar.kind in self.activated_altars for altar in self.level.altars)

    def select_card(self, index: int) -> bool:
        return self.status == GameStatus.PLAYING and super().select_card(index)

    def rotate_selected(self, times: int = 1) -> bool:
        return self.status == GameStatus.PLAYING and super().rotate_selected(times)

    def preview(self, pos: Position) -> tuple[bool, str]:
        if self.status != GameStatus.PLAYING:
            return False, "game_over"
        return super().preview(pos)

    def legal_cells(self) -> set[Position]:
        return super().legal_cells() if self.status == GameStatus.PLAYING else set()

    def movement_preview(self, pos: Position) -> tuple[bool, str]:
        if self.status != GameStatus.PLAYING:
            return False, "game_over"
        if pos == self.level.core.pos and not self.core_unlocked:
            return False, "room_locked"
        return super().movement_preview(pos)

    def _candidate(self) -> "MvpSession":
        candidate = copy(self)
        candidate.board = [row.copy() for row in self.board]
        candidate.rotations = self.rotations.copy()
        candidate.tool_uses = self.tool_uses.copy()
        candidate.rng = Random()
        candidate.rng.setstate(self.rng.getstate())
        return candidate

    def _commit(self, candidate: "MvpSession") -> None:
        self.__dict__.update(candidate.__dict__)

    def _refresh_draw(self) -> None:
        """Refresh geometry without rerolling an existing hand during exploration.

        A chisel/altar unlock can recover a blocked empty hand. Only that case
        deals cards; it uses the same protected draw API and has no retry loop.
        """
        placements = enumerate_legal_placements(self.board, self.player_pos, self.config)
        if placements and not self.draw_result.cards:
            self.draw_result = draw_cards(self.board, self.player_pos, rng=self.rng, config=self.config)
            self.selected_index = None
            self.rotations = [0] * len(self.draw_result.cards)
        else:
            self.draw_result = replace(self.draw_result, status="ready" if placements else "blocked",
                                       legal_placements=placements)

    def _finish_entry(self, pos: Position) -> None:
        if self.resources.hp_depleted:
            self.status = GameStatus.LOST
            self.loss_reason = "HP reached zero."
            return
        altar = next((room for room in self.level.altars if room.pos == pos), None)
        if altar is not None and altar.kind not in self.activated_altars:
            first = not self.activated_altars
            self.activated_altars = self.activated_altars | {altar.kind}
            tile = self.board[pos[0]][pos[1]]
            assert tile is not None
            self.board[pos[0]][pos[1]] = replace(tile, special_state="activated")
            reward = self.level.first_altar_supplies if first else 0
            before = self.resources
            self.resources = before.apply(supplies_delta=reward)
            actual = self.resources.supplies - before.supplies
            self.objective_message = f"{altar.kind.replace('_', ' ').title()} activated."
            if actual:
                self.objective_message += f" Supplies {actual:+d}."
            self.current_event = EventNotification(pos, "altar", self.objective_message, 0, actual)
            if self.core_unlocked:
                core_pos = self.level.core.pos
                core = self.board[core_pos[0]][core_pos[1]]
                assert core is not None
                self.board[core_pos[0]][core_pos[1]] = replace(core, special_state="unlocked")
                self.objective_message += " Core unlocked!"
        if pos == self.level.core.pos and self.core_unlocked:
            self.status = GameStatus.WON
            self.objective_message = "All altars activated. You reached the core!"
        if self.status == GameStatus.PLAYING:
            self._refresh_draw()

    def move(self, pos: Position) -> tuple[bool, str]:
        ok, reason = self.movement_preview(pos)
        if not ok:
            return False, reason
        candidate = self._candidate()
        ok, reason = BuildSession.move(candidate, pos)
        if not ok:
            return False, reason
        candidate._finish_entry(pos)
        self._commit(candidate)
        return True, "ok"

    def place(self, pos: Position) -> tuple[bool, str]:
        ok, reason = self.preview(pos)
        if not ok:
            return False, reason
        candidate = self._candidate()
        ok, reason = BuildSession.place(candidate, pos)
        if not ok:
            return False, reason
        candidate._finish_entry(pos)
        self._commit(candidate)
        return True, "ok"

    def _tool_budget(self, name: str) -> tuple[bool, str]:
        if self.status != GameStatus.PLAYING:
            return False, "game_over"
        rule = getattr(self.tools, name)
        if self.tool_uses[name] >= rule.max_uses_per_game:
            return False, "tool_limit_reached"
        if self.resources.supplies - rule.cost_supplies < self.resources.supplies_min:
            return False, "insufficient_supplies"
        return True, "ok"

    def preview_with_seal(self, pos: Position, direction: int) -> tuple[bool, str]:
        ok, reason = self._tool_budget("door_seal")
        if not ok:
            return False, reason
        card = self.selected_card
        if card is None:
            return False, "no_card_selected"
        try:
            sealed = seal_card(card, direction)
        except ValueError as error:
            return False, str(error)
        return can_place(Tile(sealed.kind, sealed.doors, event_category=sealed.event_category), pos,
                         self.board, reachable_rooms(self.board, self.player_pos))

    def legal_cells_with_seal(self, direction: int) -> set[Position]:
        reachable = reachable_rooms(self.board, self.player_pos)
        return {pos for pos in frontier_cells(self.board, reachable) if self.preview_with_seal(pos, direction)[0]}

    def place_with_seal(self, pos: Position, direction: int) -> tuple[bool, str]:
        ok, reason = self.preview_with_seal(pos, direction)
        if not ok:
            return False, reason
        candidate = self._candidate()
        assert candidate.selected_index is not None and candidate.selected_card is not None
        sealed = seal_card(candidate.selected_card, direction)
        cards = list(candidate.draw_result.cards)
        cards[candidate.selected_index] = sealed
        candidate.draw_result = replace(candidate.draw_result, cards=tuple(cards))
        candidate.rotations[candidate.selected_index] = 0
        candidate.resources = candidate.resources.apply(supplies_delta=-candidate.tools.door_seal.cost_supplies)
        candidate.tool_uses["door_seal"] += 1
        ok, reason = BuildSession.place(candidate, pos)
        if not ok:
            return False, reason
        candidate._finish_entry(pos)
        self._commit(candidate)
        return True, "ok"

    def chisel_preview(self, source: Position, target: Position) -> tuple[bool, str]:
        ok, reason = self._tool_budget("emergency_chisel")
        if not ok:
            return False, reason
        if self.level.core.pos in (source, target) and not self.core_unlocked:
            return False, "room_locked"
        return chisel_preview(self.board, source, target, reachable_rooms(self.board, self.player_pos))

    def chisel(self, source: Position, target: Position) -> tuple[bool, str]:
        ok, reason = self.chisel_preview(source, target)
        if not ok:
            return False, reason
        candidate = self._candidate()
        candidate.board = chisel_board(candidate.board, source, target,
                                       reachable_rooms(candidate.board, candidate.player_pos))
        candidate.resources = candidate.resources.apply(supplies_delta=-candidate.tools.emergency_chisel.cost_supplies)
        candidate.tool_uses["emergency_chisel"] += 1
        candidate._refresh_draw()
        self._commit(candidate)
        return True, "ok"
