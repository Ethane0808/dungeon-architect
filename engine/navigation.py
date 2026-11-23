"""Deterministic construction-entry routing, independent of pygame.

Routes only use already-built, traversable rooms joined by matching doors.  A
route ends at an existing room from which the proposed target can be built; it
never includes the still-empty target cell.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Collection

from engine.cards import Doors, Position
from engine.directions import DIRECTIONS, OPPOSITE, is_in_bounds, neighbor_pos
from engine.models import BOARD_SIZE, Board, validate_board
from engine.placement import connected_neighbors, reachable_rooms


@dataclass(frozen=True)
class RouteResult:
    """The chosen construction entrance and deterministic shortest route."""

    entry: Position
    path: tuple[Position, ...]
    steps: int


def build_entries(
    board: Board,
    target: Position,
    doors: Doors,
    reachable: Collection[Position],
) -> tuple[Position, ...]:
    """Return reachable existing rooms that can connect to ``target``.

    Ordering is row/column stable so callers that do not need path lengths also
    receive deterministic results.
    """
    validate_board(board)
    if not is_in_bounds(*target, BOARD_SIZE) or len(doors) != len(DIRECTIONS):
        return ()
    reachable_set = set(reachable)
    entries: list[Position] = []
    for side in DIRECTIONS:
        if not doors[side]:
            continue
        entry = neighbor_pos(*target, side)
        if not is_in_bounds(*entry, BOARD_SIZE) or entry not in reachable_set:
            continue
        tile = board[entry[0]][entry[1]]
        if tile is not None and tile.can_traverse() and tile.doors[OPPOSITE[side]]:
            entries.append(entry)
    return tuple(sorted(entries))


def shortest_path(board: Board, start: Position, goal: Position) -> tuple[Position, ...] | None:
    """Find a shortest door-to-door route using stable N/E/S/W BFS order."""
    validate_board(board)
    if not is_in_bounds(*start, BOARD_SIZE) or not is_in_bounds(*goal, BOARD_SIZE):
        return None
    start_tile = board[start[0]][start[1]]
    goal_tile = board[goal[0]][goal[1]]
    if (
        start_tile is None
        or goal_tile is None
        or not start_tile.can_traverse()
        or not goal_tile.can_traverse()
    ):
        return None
    parents: dict[Position, Position | None] = {start: None}
    queue: deque[Position] = deque([start])
    while queue:
        current = queue.popleft()
        if current == goal:
            path: list[Position] = []
            cursor: Position | None = goal
            while cursor is not None:
                path.append(cursor)
                cursor = parents[cursor]
            return tuple(reversed(path))
        for neighbor in connected_neighbors(board, current):
            if neighbor not in parents:
                parents[neighbor] = current
                queue.append(neighbor)
    return None


def route_to_build_site(
    board: Board,
    player_pos: Position,
    target: Position,
    doors: Doors,
) -> RouteResult | None:
    """Choose the nearest valid entrance, breaking ties by row then column."""
    reachable = reachable_rooms(board, player_pos)
    choices: list[tuple[int, int, int, tuple[Position, ...]]] = []
    for entry in build_entries(board, target, doors, reachable):
        path = shortest_path(board, player_pos, entry)
        if path is not None:
            choices.append((len(path) - 1, entry[0], entry[1], path))
    if not choices:
        return None
    steps, row, col, path = min(choices, key=lambda choice: choice[:3])
    return RouteResult((row, col), path, steps)


def is_local_build_source(
    board: Board,
    player_pos: Position,
    target: Position,
    doors: Doors,
) -> bool:
    """Whether the player currently occupies a matching construction entrance."""
    return player_pos in build_entries(board, target, doors, {player_pos})
