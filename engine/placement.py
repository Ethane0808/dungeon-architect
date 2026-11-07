"""
engine/placement.py
===================
地圖放置合法性核心邏輯（TECH_SPEC §5.1 / GAME_DESIGN §3.4）。

公開 API：
  can_place(tile, pos, board, reachable) -> tuple[bool, str]
  reachable_rooms(board, start, locked_specials) -> set[tuple[int,int]]
  frontier_cells(board, reachable) -> set[tuple[int,int]]

不依賴 pygame，可在純 Python 環境下單元測試。
"""

from __future__ import annotations

from collections import deque
from typing import Collection, Optional

from engine.directions import (
    DIRECTIONS, DIR_DELTA, OPPOSITE,
    is_in_bounds, neighbor_pos,
)
from engine.models import Board, BOARD_SIZE, Tile


# ─────────────────────────────────────────────────────────────────────────────
# reachable_rooms
# ─────────────────────────────────────────────────────────────────────────────

def reachable_rooms(
    board: Board,
    start: tuple[int, int],
    locked_specials: Collection[tuple[int, int]] = (),
) -> set[tuple[int, int]]:
    """
    從 start 以 BFS 找出玩家可沿已建造、門對門的道路通行的所有房間座標集合。

    規則（TECH_SPEC §5.1 / GAME_DESIGN §3.5）：
    - 相鄰兩格都已放置 Tile。
    - 兩格之間的共享邊：來源方向有門 & 目標方向的反向也有門。
    - 目標 Tile 的 can_traverse() 為 True（上鎖核心無法進入）。

    locked_specials：可以由外部額外傳入「不可抵達」的座標集合；
    目前主要由 Tile.can_traverse() 決定，此參數保留為未來擴充接口。

    回傳值包含 start 本身（若有 Tile 且可通行）。
    """
    start_row, start_col = start
    start_tile = board[start_row][start_col]
    if start_tile is None or not start_tile.can_traverse():
        return set()

    visited: set[tuple[int, int]] = {start}
    queue: deque[tuple[int, int]] = deque([start])
    locked_set = set(locked_specials)

    while queue:
        row, col = queue.popleft()
        tile = board[row][col]
        if tile is None:
            continue

        for direction in DIRECTIONS:
            if not tile.doors[direction]:
                continue  # 此方向沒有門，不能連通

            nb_row, nb_col = neighbor_pos(row, col, direction)
            if not is_in_bounds(nb_row, nb_col, BOARD_SIZE):
                continue
            if (nb_row, nb_col) in visited:
                continue
            if (nb_row, nb_col) in locked_set:
                continue

            nb_tile = board[nb_row][nb_col]
            if nb_tile is None:
                continue  # 目標格為空，不是已建房間

            # 目標格反向也必須有門（門對門匹配）
            back_dir = OPPOSITE[direction]
            if not nb_tile.doors[back_dir]:
                continue

            # 目標 Tile 本身必須可通行
            if not nb_tile.can_traverse():
                continue

            visited.add((nb_row, nb_col))
            queue.append((nb_row, nb_col))

    return visited


# ─────────────────────────────────────────────────────────────────────────────
# frontier_cells
# ─────────────────────────────────────────────────────────────────────────────

def frontier_cells(
    board: Board,
    reachable: set[tuple[int, int]],
) -> set[tuple[int, int]]:
    """
    從可達房間中，找出所有「有門朝向地圖內空白格」的空白格座標集合，
    即可供建造的候選位置（TECH_SPEC §5.1 步驟 2）。

    規則（GAME_DESIGN §3.4 / P09）：
    - 有門的可達房間 → 該方向相鄰格在地圖內 → 目標格是空白格 → 加入 frontier。
    - 不含地圖外座標。
    """
    frontier: set[tuple[int, int]] = set()
    for (row, col) in reachable:
        tile = board[row][col]
        if tile is None:
            continue
        for direction in DIRECTIONS:
            if not tile.doors[direction]:
                continue
            nb_row, nb_col = neighbor_pos(row, col, direction)
            if not is_in_bounds(nb_row, nb_col, BOARD_SIZE):
                continue
            if board[nb_row][nb_col] is None:
                frontier.add((nb_row, nb_col))
    return frontier


# ─────────────────────────────────────────────────────────────────────────────
# can_place
# ─────────────────────────────────────────────────────────────────────────────

def can_place(
    tile: Tile,
    pos: tuple[int, int],
    board: Board,
    reachable: set[tuple[int, int]],
) -> tuple[bool, str]:
    """
    驗證將 tile 放置在 pos 是否合法，回傳 (ok, reason)。

    依序檢查（GAME_DESIGN §3.4 / TECH_SPEC §5.1）：

    1. 目標格在 7×7 範圍內。
    2. 目標格為空（無 Tile）。
    3. [P09] 新房間的門不可朝向地圖外側。
    4. 目標格是 frontier（有至少一條已連通的來源門對接）。
       即：pos 必須在 frontier_cells(board, reachable) 中，
       且 tile 在對應方向上確實有門與來源房間的門相對。
    5. 所有已建造的鄰房都必須符合「門對門、牆對牆」（嚴格拼接 D04）。

    回傳：
      (True, "ok")               → 合法放置
      (False, <原因字串>)         → 非法放置，不消耗任何資源
    """
    row, col = pos

    # ── 規則 1：邊界 ──────────────────────────────────────────────────────────
    if not is_in_bounds(row, col, BOARD_SIZE):
        return False, "out_of_bounds"

    # ── 規則 2：空格 ──────────────────────────────────────────────────────────
    if board[row][col] is not None:
        return False, "cell_occupied"

    # ── 規則 3：新房間的門不可朝外 [P09] ────────────────────────────────────
    for direction in DIRECTIONS:
        if tile.doors[direction]:
            nb_row, nb_col = neighbor_pos(row, col, direction)
            if not is_in_bounds(nb_row, nb_col, BOARD_SIZE):
                return False, f"door_faces_outside_board (direction={direction})"

    # ── 規則 4：來源可達性 ────────────────────────────────────────────────────
    # 至少有一扇門，面向可達房間且雙方門對門。
    has_valid_source = False
    for direction in DIRECTIONS:
        if not tile.doors[direction]:
            continue
        nb_row, nb_col = neighbor_pos(row, col, direction)
        if not is_in_bounds(nb_row, nb_col, BOARD_SIZE):
            continue
        nb_tile = board[nb_row][nb_col]
        if nb_tile is None:
            continue
        if (nb_row, nb_col) not in reachable:
            continue
        # 鄰房在 tile 這一側的反向必須也有門
        back_dir = OPPOSITE[direction]
        if nb_tile.doors[back_dir]:
            has_valid_source = True
            break

    if not has_valid_source:
        return False, "no_reachable_source"

    # ── 規則 5：所有已建鄰邊嚴格匹配（門對門 / 牆對牆）D04 ─────────────────
    for direction in DIRECTIONS:
        nb_row, nb_col = neighbor_pos(row, col, direction)
        if not is_in_bounds(nb_row, nb_col, BOARD_SIZE):
            continue
        nb_tile = board[nb_row][nb_col]
        if nb_tile is None:
            continue  # 空格，無需匹配
        back_dir = OPPOSITE[direction]
        # 新房間此方向的門/牆 必須與鄰房反向的門/牆 相同
        if tile.doors[direction] != nb_tile.doors[back_dir]:
            return False, (
                f"edge_mismatch at direction={direction} "
                f"(new={tile.doors[direction]}, neighbor={nb_tile.doors[back_dir]})"
            )

    return True, "ok"

