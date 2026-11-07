"""
engine/directions.py
====================
方向常數、旋轉運算、相對邊計算。

doors tuple 索引順序（TECH_SPEC §3）：
  0 = N (上)
  1 = E (右)
  2 = S (下)
  3 = W (左)

旋轉規則（TECH_SPEC §3）：
  順時針 90°：new = (old[3], old[0], old[1], old[2])
"""

from __future__ import annotations

# ── 方向索引 ──────────────────────────────────────────────────────────────────
N, E, S, W = 0, 1, 2, 3
DIRECTIONS = (N, E, S, W)

# 由方向索引換算相鄰格的 (Δrow, Δcol) 偏移
DIR_DELTA: dict[int, tuple[int, int]] = {
    N: (-1,  0),
    E: ( 0, +1),
    S: (+1,  0),
    W: ( 0, -1),
}

# 每個方向的「對面」方向
OPPOSITE: dict[int, int] = {N: S, E: W, S: N, W: E}


def rotate_doors(doors: tuple[bool, bool, bool, bool], times: int = 1) -> tuple[bool, bool, bool, bool]:
    """
    將 doors 順時針旋轉 90° 共 times 次。

    TECH_SPEC §3：new = (old[3], old[0], old[1], old[2])

    >>> rotate_doors((True, False, False, False), 1)
    (False, True, False, False)
    >>> # 旋轉四次應回到原始值（ROT-01）
    >>> d = (True, False, True, False)
    >>> rotate_doors(d, 4) == d
    True
    """
    d = doors
    for _ in range(times % 4):
        d = (d[3], d[0], d[1], d[2])
    return d


def neighbor_pos(row: int, col: int, direction: int) -> tuple[int, int]:
    """回傳 (row, col) 在 direction 方向上的相鄰格座標（不做邊界檢查）。"""
    dr, dc = DIR_DELTA[direction]
    return row + dr, col + dc


def is_in_bounds(row: int, col: int, board_size: int = 7) -> bool:
    """座標是否在 board_size × board_size 的 Board 內。"""
    return 0 <= row < board_size and 0 <= col < board_size

