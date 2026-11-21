"""
engine/models.py
================
核心資料結構（TECH_SPEC §4）。

注意：僅包含純資料 dataclass，不依賴 pygame。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


BOARD_SIZE = 7  # [CONFIRMED] 7×7 格地圖


@dataclass
class Tile:
    """
    一個已放置在 Board 上的房間格。

    doors : (N, E, S, W) 各方向是否有門
    kind  : 房型字串，例如 'dead_end', 'straight', 'corner', 't_junction', 'cross',
            或特殊房 'start', 'altar_a', 'altar_b', 'core'
    event_category : None | 'supply' | 'danger' | 'neutral' | 'relic'
    event_outcome  : 首次進房後的實際資源變化，例如 {'hp': -1, 'supplies': 0}
    event_resolved : 是否已觸發過（首次進入後設為 True）
    special_state  : None | 'locked' | 'unlocked' | 'activated'
                     特殊房才使用；幾何匹配(door_match)與通行(can_traverse)分開
    """

    kind: str
    doors: tuple[bool, bool, bool, bool]
    event_category: Optional[str] = None
    event_outcome: Optional[dict] = None
    event_resolved: bool = False
    special_state: Optional[str] = None
    trapped_cache: int = 0

    def can_traverse(self) -> bool:
        """
        判斷此房間當下是否可供角色通行（進入）。

        普通房間：永遠可通行。
        核心房間（locked）：在解鎖前不可進入（GAME_DESIGN §3.4 / GOAL-03）。
        其他特殊房間：可通行（祭壇可進入後觸發啟動）。
        """
        if self.kind == "rubble" or (self.kind == "core" and self.special_state == "locked"):
            return False
        return True


# ── Board 型別別名（方便型別提示） ───────────────────────────────────────────
# board[row][col] 為 Tile | None
Board = list[list[Optional[Tile]]]


def make_empty_board(size: int = BOARD_SIZE) -> Board:
    """建立固定 7×7 全空 Board；其他尺寸會拋出 ValueError。"""
    if size != BOARD_SIZE:
        raise ValueError(f"Board size must be {BOARD_SIZE}")
    return [[None] * size for _ in range(size)]


def validate_board(board: Board) -> None:
    """拒絕非 7×7 或各列長度不一致的 Board，避免規則查詢越界。"""
    if len(board) != BOARD_SIZE or any(len(row) != BOARD_SIZE for row in board):
        raise ValueError(f"Board must be {BOARD_SIZE}x{BOARD_SIZE}")

