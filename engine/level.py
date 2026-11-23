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
from random import Random

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
    rubble_count: int = 0
    spring_count: int = 0
    guard_build_limit: int = 11

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
        if type(self.guard_build_limit) is not int or self.guard_build_limit < 1:
            raise ValueError("guard_build_limit must be a positive integer")
        if any(type(n) is not int or n < 0 for n in (self.rubble_count, self.spring_count)):
            raise ValueError("Terrain counts must be nonnegative integers")
        rooms = (self.start, *self.altars, self.core)
        if any(room.kind in {"spring", "rubble"} for room in rooms):
            raise ValueError("Special-room ids cannot overlap terrain kinds")
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

        board = self.make_board()
        before_unlock = self.potential_positions(board, core_locked=True)
        if any(altar.pos not in before_unlock for altar in self.altars):
            raise ValueError("All altars must be potentially reachable without crossing the locked core")
        if self.core.pos not in self.potential_positions(board, core_locked=False):
            raise ValueError("The core must be potentially reachable through its fixed doors")

    def potential_positions(self, board: Board, *, core_locked: bool) -> set[Position]:
        """Walk the fixed doors, treating each empty square as a possible future junction."""
        visited = {self.start.pos}
        pending = deque([self.start.pos])
        while pending:
            row, col = pending.popleft()
            source = board[row][col]
            for side in DIRECTIONS:
                pos = neighbor_pos(row, col, side)
                if not is_in_bounds(*pos, BOARD_SIZE) or pos in visited:
                    continue
                if core_locked and pos == self.core.pos:
                    continue
                target = board[pos[0]][pos[1]]
                if (source and not source.doors[side]) or (target and not target.doors[OPPOSITE[side]]):
                    continue
                visited.add(pos)
                pending.append(pos)
        return visited

    def make_board(self, seed: int | None = None) -> Board:
        """Create independent Tiles with unactivated altars and a locked core."""
        board = make_empty_board()
        for room in (self.start, *self.altars, self.core):
            board[room.pos[0]][room.pos[1]] = Tile(
                room.kind, room.doors, special_state="locked" if room.kind == "core" else None,
            )
        if seed is not None and (self.rubble_count or self.spring_count):
            self._add_terrain(board, seed)
        return board

    def _add_terrain(self, board: Board, seed: int) -> None:
        fixed = (self.start, *self.altars, self.core)
        candidates = [(r, c) for r in range(1, BOARD_SIZE - 1) for c in range(1, BOARD_SIZE - 1)
                      if all(abs(r - room.pos[0]) + abs(c - room.pos[1]) > 1 for room in fixed)]
        Random(f"terrain:{seed}:1").shuffle(candidates)
        required = {altar.pos for altar in self.altars}
        remaining = self.rubble_count
        for r, c in candidates:
            if not remaining:
                break
            board[r][c] = Tile("rubble", (False,) * 4)
            if (required <= self.potential_positions(board, core_locked=True)
                    and self.core.pos in self.potential_positions(board, core_locked=False)):
                remaining -= 1
            else:
                board[r][c] = None
        reachable = self.potential_positions(board, core_locked=True)
        remaining = self.spring_count
        for r, c in candidates:
            if not remaining:
                break
            if board[r][c] or (r, c) not in reachable:
                continue
            doors = []
            for side in DIRECTIONS:
                nr, nc = neighbor_pos(r, c, side)
                neighbor = board[nr][nc]
                doors.append(neighbor is None or neighbor.doors[OPPOSITE[side]])
            board[r][c] = Tile("spring", tuple(doors))
            remaining -= 1

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
                rubble_count=data.get("terrain", {}).get("rubble_count", 0),
                spring_count=data.get("terrain", {}).get("spring_count", 0),
                guard_build_limit=data.get("guard", {}).get("build_limit", 11),
            )
        except (KeyError, TypeError, AttributeError) as error:
            raise ValueError(f"Invalid level configuration: {error}") from error


def load_level_config(path: str | Path = DEFAULT_CONFIG_PATH) -> LevelConfig:
    """Read the fixed-level snapshot independently of the working directory."""
    with Path(path).open(encoding="utf-8-sig") as source:
        return LevelConfig.from_mapping(json.load(source))
