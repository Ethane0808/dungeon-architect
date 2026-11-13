"""Immutable fixed-level configuration and optimistic geometry validation.

Potential connectivity treats empty cells as flexible passages. It rules out
fixed-wall contradictions without promising that cards, resources or a specific
construction sequence will make the level solvable.
"""

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
import json
from pathlib import Path

from engine.cards import DEFAULT_CONFIG_PATH, Doors, Position
from engine.directions import DIRECTIONS, OPPOSITE, is_in_bounds, neighbor_pos
from engine.models import BOARD_SIZE, Board, Tile, make_empty_board


@dataclass(frozen=True)
class SpecialRoom:
    kind: str
    pos: Position
    doors: Doors

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or not self.kind.strip() or self.kind.startswith("_"):
            raise ValueError("Special-room kind must be a nonempty name")
        if not isinstance(self.pos, tuple) or len(self.pos) != 2 or any(
            type(value) is not int for value in self.pos
        ) or not is_in_bounds(*self.pos, BOARD_SIZE):
            raise ValueError("Special-room position must contain two integers inside the 7x7 board")
        if not isinstance(self.doors, tuple) or len(self.doors) != 4 or any(
            type(door) is not bool for door in self.doors
        ) or not any(self.doors):
            raise ValueError("Special-room doors must contain four N/E/S/W booleans and at least one exit")
        for side in DIRECTIONS:
            if self.doors[side] and not is_in_bounds(*neighbor_pos(*self.pos, side), BOARD_SIZE):
                raise ValueError("Special-room doors cannot face outside the board")


@dataclass(frozen=True)
class LevelConfig:
    start: SpecialRoom
    altars: tuple[SpecialRoom, ...]
    core: SpecialRoom
    first_altar_supplies: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.start, SpecialRoom) or self.start.kind != "start":
            raise ValueError("The starting room must have kind 'start'")
        if not isinstance(self.core, SpecialRoom) or self.core.kind != "core":
            raise ValueError("The sealed core must have kind 'core'")
        if not isinstance(self.altars, tuple) or not self.altars or any(
            not isinstance(room, SpecialRoom) for room in self.altars
        ):
            raise ValueError("At least one altar SpecialRoom is required in an immutable tuple")
        if type(self.first_altar_supplies) is not int or self.first_altar_supplies < 0:
            raise ValueError("first_altar_supplies must be a nonnegative integer")
        rooms = (self.start, *self.altars, self.core)
        if len({room.kind for room in rooms}) != len(rooms):
            raise ValueError("Special-room ids must be unique and altars cannot use start/core ids")
        fixed = {room.pos: room for room in rooms}
        if len(fixed) != len(rooms):
            raise ValueError("Special rooms cannot overlap")
        for room in rooms:
            for side in DIRECTIONS:
                adjacent = fixed.get(neighbor_pos(*room.pos, side))
                if adjacent is not None and room.doors[side] != adjacent.doors[OPPOSITE[side]]:
                    raise ValueError("Adjacent fixed-room doors and walls must match")

        def potential_positions(*, core_locked: bool) -> set[Position]:
            visited = {self.start.pos}
            pending = deque([self.start.pos])
            while pending:
                pos = pending.popleft()
                source = fixed.get(pos)
                for side in DIRECTIONS:
                    target_pos = neighbor_pos(*pos, side)
                    if not is_in_bounds(*target_pos, BOARD_SIZE) or target_pos in visited:
                        continue
                    if core_locked and target_pos == self.core.pos:
                        continue
                    target = fixed.get(target_pos)
                    if source is not None and not source.doors[side]:
                        continue
                    if target is not None and not target.doors[OPPOSITE[side]]:
                        continue
                    visited.add(target_pos)
                    pending.append(target_pos)
            return visited

        before_unlock = potential_positions(core_locked=True)
        if any(altar.pos not in before_unlock for altar in self.altars):
            raise ValueError("All altars must be potentially reachable without crossing the locked core")
        if self.core.pos not in potential_positions(core_locked=False):
            raise ValueError("The core must be potentially reachable through its fixed doors")

    def make_board(self) -> Board:
        """Create independent Tiles with unactivated altars and a locked core."""
        board = make_empty_board()
        for room in (self.start, *self.altars, self.core):
            board[room.pos[0]][room.pos[1]] = Tile(
                room.kind, room.doors, special_state="locked" if room.kind == "core" else None,
            )
        return board

    @classmethod
    def from_mapping(cls, data: Mapping) -> "LevelConfig":
        """Load objectives without retaining mutable JSON input containers."""
        try:
            if "board" in data and (
                type(data["board"]["size"]) is not int or data["board"]["size"] != BOARD_SIZE
            ):
                raise ValueError("Fixed levels require a 7x7 board")
            objectives = data["objectives"]
            unknown = {key for key in objectives if not key.startswith("_")} - {
                "start", "altars", "core", "first_altar_supplies"
            }
            if unknown:
                raise ValueError(f"Unknown objective fields: {sorted(unknown)}")

            def room(kind: str, definition: Mapping) -> SpecialRoom:
                return SpecialRoom(kind, tuple(definition["pos"]), tuple(definition["doors"]))

            definitions = objectives["altars"]
            if not isinstance(definitions, list):
                raise ValueError("objectives.altars must be a list")
            return cls(
                start=room("start", objectives["start"]),
                altars=tuple(room(altar["id"], altar) for altar in definitions),
                core=room("core", objectives["core"]),
                first_altar_supplies=objectives.get("first_altar_supplies", 1),
            )
        except (KeyError, TypeError, AttributeError) as error:
            raise ValueError(f"Invalid level configuration: {error}") from error


def load_level_config(path: str | Path = DEFAULT_CONFIG_PATH) -> LevelConfig:
    """Read the fixed-level snapshot independently of the working directory."""
    with Path(path).open(encoding="utf-8-sig") as source:
        return LevelConfig.from_mapping(json.load(source))
