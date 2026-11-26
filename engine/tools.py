"""Pure spatial recovery rules; sessions own costs, usage and atomic commits.

The two tools are provisional MVP mechanics. Door Seal alters one selected
card; normal placement validation still decides whether it can be built.
Emergency Chisel opens a wall shared by two existing, traversable rooms.
"""

from collections.abc import Mapping, Set
from dataclasses import dataclass, replace
import json
from pathlib import Path

from engine.cards import Card, DEFAULT_CONFIG_PATH, Position
from engine.directions import DIRECTIONS, OPPOSITE, is_in_bounds, neighbor_pos
from engine.models import BOARD_SIZE, Board, validate_board


@dataclass(frozen=True)
class ToolRule:
    cost_supplies: int
    max_uses_per_game: int

    def __post_init__(self) -> None:
        if type(self.cost_supplies) is not int or self.cost_supplies <= 0:
            raise ValueError("Tool cost_supplies must be a positive integer")
        if type(self.max_uses_per_game) is not int or self.max_uses_per_game < 0:
            raise ValueError("Tool max_uses_per_game must be a nonnegative integer")


@dataclass(frozen=True)
class ToolConfig:
    door_seal: ToolRule
    emergency_chisel: ToolRule
    medkit: ToolRule = ToolRule(2, 2)

    def __post_init__(self) -> None:
        if not all(isinstance(rule, ToolRule) for rule in (self.door_seal, self.emergency_chisel, self.medkit)):
            raise ValueError("Tool configuration requires ToolRule values")

    @classmethod
    def from_mapping(cls, data: Mapping) -> "ToolConfig":
        try:
            items = data["items"]
            rules = []
            for name in ("door_seal", "emergency_chisel"):
                definition = items[name]
                rules.append(ToolRule(definition["cost_supplies"], definition["max_uses_per_game"]))
            if "medkit" in items:
                definition = items["medkit"]
                rules.append(ToolRule(definition["cost_supplies"], definition["max_uses_per_game"]))
            return cls(*rules)
        except (KeyError, TypeError, AttributeError) as error:
            raise ValueError(f"Invalid tool configuration: {error}") from error


def load_tool_config(path: str | Path = DEFAULT_CONFIG_PATH) -> ToolConfig:
    """Read existing provisional item costs and limits without changing them."""
    with Path(path).open(encoding="utf-8-sig") as source:
        return ToolConfig.from_mapping(json.load(source))


def seal_card(card: Card, direction: int) -> Card:
    """Close exactly one door, preserving a possible entrance and event category.

    A remaining door is necessary but insufficient: the caller must pass the
    modified card through the existing strict placement validator before paying.
    """
    if type(direction) is not int or direction not in DIRECTIONS:
        raise ValueError("invalid_direction")
    if not card.doors[direction]:
        raise ValueError("not_a_door")
    if sum(card.doors) <= 1:
        raise ValueError("no_entrance")
    doors = list(card.doors)
    doors[direction] = False
    return replace(card, doors=tuple(doors))


def _valid_position(pos: Position) -> bool:
    return isinstance(pos, tuple) and len(pos) == 2 and all(type(value) is int for value in pos)


def chisel_preview(board: Board, source: Position, target: Position,
                   reachable: Set[Position]) -> tuple[bool, str]:
    """Validate an adjacent wall pair without modifying rooms or resources.

    Only the source must already be reachable. The target may be isolated,
    which is what makes this a recovery action; it must still be unlocked.
    Board shape errors use the same ValueError contract as placement queries.
    """
    validate_board(board)
    if not _valid_position(source) or not _valid_position(target):
        return False, "invalid_position"
    if not is_in_bounds(*source, BOARD_SIZE) or not is_in_bounds(*target, BOARD_SIZE):
        return False, "out_of_bounds"
    direction = next((side for side in DIRECTIONS if neighbor_pos(*source, side) == target), None)
    if direction is None:
        return False, "not_adjacent"
    source_tile = board[source[0]][source[1]]
    target_tile = board[target[0]][target[1]]
    if source_tile is None or target_tile is None:
        return False, "no_room"
    if target_tile.kind == "rubble" or source_tile.kind == "rubble":
        return False, "rubble"
    if (source_tile.special_state == "locked" or target_tile.special_state == "locked"
            or not source_tile.can_traverse() or not target_tile.can_traverse()):
        return False, "room_locked"
    if source not in reachable:
        return False, "source_unreachable"
    source_door = source_tile.doors[direction]
    target_door = target_tile.doors[OPPOSITE[direction]]
    if source_door and target_door:
        return False, "already_connected"
    if source_door != target_door:
        return False, "edge_mismatch"
    return True, "ok"


def chisel_board(board: Board, source: Position, target: Position,
                  reachable: Set[Position]) -> Board:
    """Prepare a board with one new matching doorway, leaving the original intact.

    Costs, usage counts, objective activation and draw refresh belong to the
    calling session so they can be committed together with this board.
    """
    ok, reason = chisel_preview(board, source, target, reachable)
    if not ok:
        raise ValueError(reason)
    direction = next(side for side in DIRECTIONS if neighbor_pos(*source, side) == target)
    prepared = [row.copy() for row in board]
    for pos, side in ((source, direction), (target, OPPOSITE[direction])):
        tile = board[pos[0]][pos[1]]
        assert tile is not None
        doors = list(tile.doors)
        doors[side] = True
        prepared[pos[0]][pos[1]] = replace(tile, doors=tuple(doors))
    return prepared
