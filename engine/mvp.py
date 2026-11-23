"""Complete MVP loop built on the tested construction/event controller.

BuildSession remains the focused Phase 4 sandbox API. MvpSession adds a validated
fixed level, objective progression, paid spatial tools and terminal states. Each
gameplay operation prepares a private candidate and commits only on success.
"""

from copy import copy
from collections import deque
from dataclasses import replace
from enum import Enum
from random import Random

from engine.cards import Card, CardConfig, Doors, Position, draw_cards, enumerate_legal_placements
from engine.directions import DIRECTIONS, neighbor_pos
from engine.events import EventConfig, EventNotification
from engine.game import BuildSession
from engine.level import LevelConfig, load_level_config
from engine.models import Board, Tile
from engine.messages import Message
from engine.navigation import is_local_build_source
from engine.placement import can_place, connected_neighbors, frontier_cells, loops_closed_by_room, reachable_rooms
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
        if (special_ids | {"rubble", "spring"}).intersection(room.kind for room in self.config.room_types):
            raise ValueError("Ordinary card kinds cannot overlap level special-room ids")

    def restart(self) -> None:
        board = self.level.make_board(self.seed)
        rng = Random(self.seed)
        self.board = board
        self.player_pos = self.level.start.pos
        self.rng = rng
        self.build_turn = 0
        self.selected_index = None
        self.resources = self.initial_resources
        self.current_event = None
        self.loops_closed = 0
        self.guard_pos: Position | None = None
        self.guard_next: Position | None = None
        self.guard_wake_reason: str | None = None
        self.activated_altars: frozenset[str] = frozenset()
        self.tool_uses = {"door_seal": 0, "emergency_chisel": 0}
        self.status = GameStatus.LOST if self.resources.hp_depleted else GameStatus.PLAYING
        self.loss_reason = "HP reached zero." if self.resources.hp_depleted else None
        self.objective_message = "Enter every altar, then reach the unlocked core."
        if self.status == GameStatus.PLAYING:
            self._wake_guard()
        excluded = () if self.guard_pos is None else (self.guard_pos,)
        self.draw_result = draw_cards(board, self.player_pos, rng=rng, config=self.config, locked_specials=excluded)
        self.rotations = [0] * len(self.draw_result.cards)

    @property
    def core_unlocked(self) -> bool:
        return all(altar.kind in self.activated_altars for altar in self.level.altars)

    def select_card(self, index: int) -> bool:
        return self.status == GameStatus.PLAYING and super().select_card(index)

    def rotate_selected(self, times: int = 1) -> bool:
        return self.status == GameStatus.PLAYING and super().rotate_selected(times)

    def open_trapped_cache(self) -> bool:
        return self.status == GameStatus.PLAYING and super().open_trapped_cache()

    def medkit_preview(self) -> tuple[bool, str]:
        if self.status != GameStatus.PLAYING:
            return False, "game_over"
        if self.resources.hp == self.resources.hp_max:
            return False, "full_health"
        if self.resources.supplies - self.resources.supplies_min < 2:
            return False, "insufficient_supplies"
        return True, "ok"

    def use_medkit(self) -> tuple[bool, str]:
        ok, reason = self.medkit_preview()
        if ok:
            self.resources = self.resources.apply(hp_delta=1, supplies_delta=-2)
            self.current_event = EventNotification(self.player_pos, "medkit", "Used a medkit to recover 1 HP.", 1, -2)
        return ok, reason

    def geometry_preview(self, pos: Position) -> tuple[bool, str]:
        """Validate a selected card anywhere on the reachable construction frontier."""
        if self.status != GameStatus.PLAYING:
            return False, "game_over"
        card = self.selected_card
        if card is None:
            return BuildSession.preview(self, pos)
        return self._build_preview(pos, card)

    def preview(self, pos: Position) -> tuple[bool, str]:
        """Validate an actual build, including the player's current entrance."""
        ok, reason = self.geometry_preview(pos)
        if not ok:
            return False, reason
        card = self.selected_card
        assert card is not None
        if not is_local_build_source(self.board, self.player_pos, pos, card.doors):
            return False, "not_at_build_frontier"
        return True, "ok"

    def _build_preview(self, pos: Position, card: Card) -> tuple[bool, str]:
        tile = Tile(card.kind, card.doors, event_category=card.event_category)
        result = can_place(tile, pos, self.board, reachable_rooms(self.board, self.player_pos))
        if result[0] and self.guard_pos is not None:
            accessible = reachable_rooms(self.board, self.player_pos, (self.guard_pos,))
            if pos not in frontier_cells(self.board, accessible):
                return False, "guard_blocks_route"
        return result

    def planning_cells(self) -> set[Position]:
        """Return globally legal previews without changing the draw guarantee."""
        if self.status != GameStatus.PLAYING:
            return set()
        cells = super().legal_cells()
        if cells and self.guard_pos is not None:
            cells &= frontier_cells(self.board, reachable_rooms(self.board, self.player_pos, (self.guard_pos,)))
        return cells

    def legal_cells(self) -> set[Position]:
        """Return only cells buildable from the player's current room."""
        card = self.selected_card
        if card is None:
            return set()
        return {
            pos for pos in self.planning_cells()
            if is_local_build_source(self.board, self.player_pos, pos, card.doors)
        }

    def exits_sealed(self, board: Board, origin: Position) -> bool:
        """Prove a closed region even if the player could afford every remaining chisel."""
        reachable = reachable_rooms(board, origin)
        if frontier_cells(board, reachable):
            return False
        if self.level.core.pos in reachable or any(
            altar.pos in reachable and altar.kind not in self.activated_altars for altar in self.level.altars
        ):
            return False
        if self.tool_uses["emergency_chisel"] < self.tools.emergency_chisel.max_uses_per_game:
            for source in reachable:
                for side in DIRECTIONS:
                    target = neighbor_pos(*source, side)
                    if target not in reachable and chisel_preview(board, source, target, reachable)[0]:
                        return False
        return True

    def build_warnings(self, pos: Position, doors: Doors) -> tuple[bool, bool]:
        """Inspect only visible topology for a legal build preview."""
        board = self.board.copy()
        board[pos[0]] = board[pos[0]].copy()
        board[pos[0]][pos[1]] = Tile("preview", doors)
        wakes = self.guard_pos is None and self._alarm_trigger(board, self.build_turn + 1) is not None
        return self.exits_sealed(board, pos), wakes

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

        Deal after construction or when new access restores an empty hand.
        Existing cards keep their rotations while the guard and exits change.
        """
        excluded = () if self.guard_pos is None else (self.guard_pos,)
        if not self.draw_result.cards:
            self.draw_result = draw_cards(self.board, self.player_pos, rng=self.rng, config=self.config,
                                          locked_specials=excluded)
            self.selected_index = None
            self.rotations = [0] * len(self.draw_result.cards)
        else:
            placements = enumerate_legal_placements(self.board, self.player_pos, self.config, excluded)
            self.draw_result = replace(self.draw_result, status="ready" if placements else "blocked",
                                       legal_placements=placements)

    def _guard_route(self, origin: Position) -> list[Position]:
        """Shortest connected route from origin to player, including both ends."""
        parent = {origin: None}
        queue = deque([origin])
        while queue:
            pos = queue.popleft()
            if pos == self.player_pos:
                route = [pos]
                while parent[pos] is not None:
                    pos = parent[pos]
                    route.append(pos)
                return route[::-1]
            for neighbor in connected_neighbors(self.board, pos):
                if neighbor not in parent:
                    parent[neighbor] = pos
                    queue.append(neighbor)
        return []

    def _alarm_trigger(self, board: Board, build_count: int) -> str | None:
        reachable = reachable_rooms(board, self.level.start.pos)
        if any(altar.pos in reachable for altar in self.level.altars):
            return "altar"
        return "construction" if build_count >= self.level.guard_build_limit else None

    def _wake_guard(self) -> None:
        """Place the guard and telegraph its first step without moving or striking."""
        if self.guard_pos is not None:
            return
        self.guard_wake_reason = self._alarm_trigger(self.board, self.build_turn)
        if self.guard_wake_reason is None:
            return
        route = self._guard_route(self.level.start.pos)
        if len(route) > 1:
            index = max(0, len(route) - 4)
            self.guard_pos, self.guard_next = route[index:index + 2]
        else:
            # A custom starting layout or a chisel can connect an altar from Start.
            self.guard_pos = next(connected_neighbors(self.board, self.player_pos), self.player_pos)
            self.guard_next = self.player_pos if self.guard_pos != self.player_pos else None

    def _update_guard(self, previous_event, build_source: Position | None) -> None:
        if self.guard_pos is None:
            self._wake_guard()
            return
        hit = self.guard_pos == self.player_pos
        if self.guard_next is not None:
            self.guard_pos = self.guard_next
            hit |= self.guard_pos in (build_source, self.player_pos)
        if hit:
            self.resources = self.resources.apply(hp_delta=-1)
            self.guard_pos = self.level.start.pos
            notice = self.current_event
            if notice is not None and notice is not previous_event:
                self.current_event = replace(notice, message=Message("{message} Guard hit!", message=notice.message),
                                             hp_delta=notice.hp_delta - 1)
            else:
                self.current_event = EventNotification(self.player_pos, "guard", "The guard strikes and retreats.", -1, 0)
        route = self._guard_route(self.guard_pos)
        self.guard_next = route[1] if len(route) > 1 else None

    def _finish_entry(self, pos: Position, previous_event, build_source: Position | None = None) -> None:
        if self.resources.hp_depleted:
            self.status = GameStatus.LOST
            self.loss_reason = "HP reached zero."
            return
        tile = self.board[pos[0]][pos[1]]
        if tile is not None and tile.kind == "spring" and not tile.event_resolved:
            before = self.resources.hp
            self.resources = self.resources.apply(hp_delta=1)
            gained = self.resources.hp - before
            self.board[pos[0]][pos[1]] = replace(tile, event_resolved=True, event_outcome={"hp": gained, "supplies": 0})
            self.current_event = EventNotification(pos, "spring", "You drink the last of the clear water.", gained, 0)
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
            self.objective_message = Message("{altar} activated.", altar=altar.kind.replace('_', ' ').title())
            if actual:
                self.objective_message = Message("{message} Supplies {amount:+d}.", message=self.objective_message, amount=actual)
            self.current_event = EventNotification(pos, "altar", self.objective_message, 0, actual)
            if self.core_unlocked:
                core_pos = self.level.core.pos
                core = self.board[core_pos[0]][core_pos[1]]
                assert core is not None
                self.board[core_pos[0]][core_pos[1]] = replace(core, special_state="unlocked")
                self.objective_message = Message("{message} Core unlocked!", message=self.objective_message)
        self._update_guard(previous_event, build_source)
        if self.resources.hp_depleted:
            self.status = GameStatus.LOST
            self.loss_reason = "HP reached zero."
        elif pos == self.level.core.pos and self.core_unlocked:
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
        candidate._finish_entry(pos, self.current_event)
        self._commit(candidate)
        return True, "ok"

    def _reward_loops(self, count: int, notice: EventNotification) -> None:
        before = self.resources.supplies
        self.resources = self.resources.apply(supplies_delta=count)
        self.loops_closed += count
        self.current_event = replace(notice, loops_closed=count, loop_supplies=self.resources.supplies - before)

    def _finish_build(self, pos: Position, previous: "MvpSession") -> None:
        self._finish_entry(pos, previous.current_event, previous.player_pos)
        if self.status != GameStatus.PLAYING:
            return
        tile = self.board[pos[0]][pos[1]]
        assert tile is not None
        count = loops_closed_by_room(previous.board, pos, tile.doors)
        if count:
            notice = self.current_event
            if notice is None or notice.pos != pos:
                notice = EventNotification(pos, "construction", "The new room joins two passages.", 0, 0)
            self._reward_loops(count, notice)

    def place(self, pos: Position) -> tuple[bool, str]:
        ok, reason = self.preview(pos)
        if not ok:
            return False, reason
        candidate = self._candidate()
        ok, reason = candidate.preview(pos)
        if not ok:
            return False, reason
        card = candidate.selected_card
        assert card is not None
        candidate._build_room(pos, card, deal_next=False)
        candidate._finish_build(pos, self)
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

    def geometry_preview_with_seal(self, pos: Position, direction: int) -> tuple[bool, str]:
        """Validate tool budget and sealed geometry without requiring local presence."""
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
        return self._build_preview(pos, sealed)

    def preview_with_seal(self, pos: Position, direction: int) -> tuple[bool, str]:
        ok, reason = self.geometry_preview_with_seal(pos, direction)
        if not ok:
            return False, reason
        assert self.selected_card is not None
        sealed = seal_card(self.selected_card, direction)
        if not is_local_build_source(self.board, self.player_pos, pos, sealed.doors):
            return False, "not_at_build_frontier"
        return True, "ok"

    def planning_cells_with_seal(self, direction: int) -> set[Position]:
        reachable = reachable_rooms(self.board, self.player_pos)
        return {
            pos for pos in frontier_cells(self.board, reachable)
            if self.geometry_preview_with_seal(pos, direction)[0]
        }

    def legal_cells_with_seal(self, direction: int) -> set[Position]:
        card = self.selected_card
        if card is None:
            return set()
        try:
            sealed = seal_card(card, direction)
        except ValueError:
            return set()
        return {
            pos for pos in self.planning_cells_with_seal(direction)
            if is_local_build_source(self.board, self.player_pos, pos, sealed.doors)
        }

    def place_with_seal(self, pos: Position, direction: int) -> tuple[bool, str]:
        ok, reason = self.preview_with_seal(pos, direction)
        if not ok:
            return False, reason
        candidate = self._candidate()
        ok, reason = candidate.preview_with_seal(pos, direction)
        if not ok:
            return False, reason
        assert candidate.selected_index is not None and candidate.selected_card is not None
        sealed = seal_card(candidate.selected_card, direction)
        candidate.resources = candidate.resources.apply(supplies_delta=-candidate.tools.door_seal.cost_supplies)
        candidate.tool_uses["door_seal"] += 1
        candidate._build_room(pos, sealed, deal_next=False)
        candidate._finish_build(pos, self)
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
        reachable = reachable_rooms(candidate.board, candidate.player_pos)
        candidate.board = chisel_board(candidate.board, source, target, reachable)
        candidate.resources = candidate.resources.apply(supplies_delta=-candidate.tools.emergency_chisel.cost_supplies)
        candidate.tool_uses["emergency_chisel"] += 1
        if target in reachable:
            candidate._reward_loops(1, EventNotification(target, "construction", "A shortcut through the wall.", 0, 0))
        candidate._wake_guard()
        candidate._refresh_draw()
        self._commit(candidate)
        return True, "ok"
