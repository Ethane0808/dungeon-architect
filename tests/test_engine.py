"""
tests/test_engine.py
====================
Dungeon Architect — 第一階段核心引擎 pytest 測試。

覆蓋 TEST_PLAN.md：
  ROT-01   任意房型順時針轉四次回到原樣
  PLACE-01 門對門，所有已建鄰邊也匹配 → 允許放置
  PLACE-02 來源入口匹配，但另一相鄰邊門對牆 → 禁止
  PLACE-03 地圖外、已佔用格、覆蓋特殊房 → 禁止，不消耗資源
  PLACE-04 遠端不可達位置建造 → 禁止
  MOVE-01  相鄰已建房間門對門且未上鎖 → 允許移動（進入可達集合）
  MOVE-02  門對牆、牆對牆、核心鎖住 → 禁止穿越（不進入可達集合）

另外包含：
  - rotate_doors 基礎驗證
  - reachable_rooms 與 frontier_cells 功能測試
  - P09：新房間的門不可朝向地圖外
"""

from __future__ import annotations

from copy import deepcopy
from itertools import product

import pytest

from engine.directions import rotate_doors, neighbor_pos, OPPOSITE, N, E, S, W, DIRECTIONS
from engine.models import Tile, make_empty_board, BOARD_SIZE
from engine.placement import can_place, reachable_rooms, frontier_cells


# ═══════════════════════════════════════════════════════════════════════════════
# 輔助函數
# ═══════════════════════════════════════════════════════════════════════════════

def make_tile(n=False, e=False, s=False, w=False, kind="room", **kwargs) -> Tile:
    """快速建立 Tile（預設四面皆牆）。"""
    return Tile(kind=kind, doors=(n, e, s, w), **kwargs)


def place(board, row, col, tile: Tile):
    """將 tile 放到 board[row][col]，回傳 board 自身（方便鏈式呼叫）。"""
    board[row][col] = tile
    return board


# ═══════════════════════════════════════════════════════════════════════════════
# ROT-01：任意房型順時針轉四次回到原樣
# ═══════════════════════════════════════════════════════════════════════════════

class TestRotation:
    """ROT-01：所有五種基礎房型旋轉四次必須回到原始門型。"""

    BASE_DOORS = [
        # (name,            N,     E,     S,     W  )
        ("dead_end",        True,  False, False, False),
        ("straight",        True,  False, True,  False),
        ("corner",          True,  True,  False, False),
        ("t_junction",      True,  True,  True,  False),
        ("cross",           True,  True,  True,  True ),
    ]

    @pytest.mark.parametrize("name,n,e,s,w", BASE_DOORS)
    def test_four_rotations_restore(self, name, n, e, s, w):
        """ROT-01：旋轉四次必須完全還原。"""
        original = (n, e, s, w)
        result = original
        for _ in range(4):
            result = rotate_doors(result)
        assert result == original, (
            f"{name}: 連續四次單步旋轉應回到原始值，但得到 {result}"
        )

    @pytest.mark.parametrize("name,n,e,s,w", BASE_DOORS)
    def test_each_step_clockwise(self, name, n, e, s, w):
        """每次旋轉 90° 順時針：new = (old[3], old[0], old[1], old[2])。"""
        d = (n, e, s, w)
        once = rotate_doors(d, 1)
        assert once == (d[3], d[0], d[1], d[2]), (
            f"{name}: 旋轉一次結果不符合規格"
        )

    def test_rotate_times_zero(self):
        """旋轉 0 次不改變任何值。"""
        d = (True, False, True, False)
        assert rotate_doors(d, 0) == d

    def test_rotate_times_modulo(self):
        """旋轉 5 次等同於旋轉 1 次。"""
        d = (True, True, False, False)
        assert rotate_doors(d, 5) == rotate_doors(d, 1)


# ═══════════════════════════════════════════════════════════════════════════════
# reachable_rooms 基礎功能
# ═══════════════════════════════════════════════════════════════════════════════

class TestReachableRooms:

    def test_single_tile_reachable(self):
        """只有起點一格，可達集合只含起點。"""
        board = make_empty_board()
        t = make_tile(n=True, e=False, s=False, w=False)
        place(board, 3, 3, t)
        result = reachable_rooms(board, (3, 3))
        assert result == {(3, 3)}

    def test_two_connected_tiles(self):
        """兩格南北門對門，應互相可達。"""
        board = make_empty_board()
        # (2,3) 朝南開門，(3,3) 朝北開門
        place(board, 2, 3, make_tile(s=True))
        place(board, 3, 3, make_tile(n=True))
        result = reachable_rooms(board, (2, 3))
        assert (2, 3) in result
        assert (3, 3) in result

    def test_wall_blocks_traversal(self):
        """兩格相鄰但共享邊為牆，不可穿越（MOVE-02 牆對牆情境）。"""
        board = make_empty_board()
        # (2,3) 無南門，(3,3) 有北門 → 牆對門，不連通
        place(board, 2, 3, make_tile(n=True, s=False))
        place(board, 3, 3, make_tile(n=True, s=False))
        result = reachable_rooms(board, (2, 3))
        assert (3, 3) not in result

    def test_locked_core_not_reachable(self):
        """上鎖的 core 即使門對門也不可進入（MOVE-02 / GOAL-03）。"""
        board = make_empty_board()
        place(board, 3, 3, make_tile(e=True))
        place(board, 3, 4, make_tile(w=True, kind="core", special_state="locked"))
        result = reachable_rooms(board, (3, 3))
        assert (3, 4) not in result, "locked core 不應出現在 reachable_rooms"

    def test_unlocked_core_is_reachable(self):
        """解鎖後 core 可以正常進入。"""
        board = make_empty_board()
        place(board, 3, 3, make_tile(e=True))
        place(board, 3, 4, make_tile(w=True, kind="core", special_state="unlocked"))
        result = reachable_rooms(board, (3, 3))
        assert (3, 4) in result

    def test_start_none_returns_empty(self):
        """起點格為空，應回傳空集合。"""
        board = make_empty_board()
        result = reachable_rooms(board, (3, 3))
        assert result == set()

    def test_chain_of_three(self):
        """三格直線連通，全部可達。"""
        board = make_empty_board()
        place(board, 3, 1, make_tile(e=True))
        place(board, 3, 2, make_tile(w=True, e=True))
        place(board, 3, 3, make_tile(w=True))
        result = reachable_rooms(board, (3, 1))
        assert result == {(3, 1), (3, 2), (3, 3)}


# ═══════════════════════════════════════════════════════════════════════════════
# frontier_cells 基礎功能
# ═══════════════════════════════════════════════════════════════════════════════

class TestFrontierCells:

    def test_basic_frontier(self):
        """起點朝東有門，(3,4) 為空 → (3,4) 在 frontier。"""
        board = make_empty_board()
        place(board, 3, 3, make_tile(e=True))
        reachable = {(3, 3)}
        f = frontier_cells(board, reachable)
        assert (3, 4) in f

    def test_occupied_cell_not_frontier(self):
        """已有 Tile 的格不納入 frontier。"""
        board = make_empty_board()
        place(board, 3, 3, make_tile(e=True))
        place(board, 3, 4, make_tile(w=True))  # 已佔用
        reachable = {(3, 3), (3, 4)}
        f = frontier_cells(board, reachable)
        assert (3, 4) not in f

    def test_door_faces_map_edge_not_frontier(self):
        """
        [P09 關聯] frontier 只收集地圖內的空格；
        門若朝向地圖外，neighbor_pos 越界 → 不加入 frontier。
        """
        board = make_empty_board()
        # 放在第 0 列且朝北開門 → 北邊是地圖外
        place(board, 0, 3, make_tile(n=True))
        reachable = {(0, 3)}
        f = frontier_cells(board, reachable)
        assert (-1, 3) not in f

    def test_wall_direction_no_frontier(self):
        """無門方向不產生 frontier。"""
        board = make_empty_board()
        # 四面都是牆
        place(board, 3, 3, make_tile())
        reachable = {(3, 3)}
        f = frontier_cells(board, reachable)
        assert len(f) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# can_place — PLACE-01：合法放置
# ═══════════════════════════════════════════════════════════════════════════════

class TestCanPlaceLegal:
    """PLACE-01：門對門，其他已建鄰邊也匹配 → 允許放置。"""

    def test_place_01_simple_east(self):
        """
        PLACE-01：起點 (3,3) 朝東有門，新 tile 朝西有門，
        無其他鄰房 → 允許放置在 (3,4)。
        """
        board = make_empty_board()
        place(board, 3, 3, make_tile(e=True))
        reachable = {(3, 3)}

        new_tile = make_tile(w=True)  # 朝西有門，對上起點東門
        ok, reason = can_place(new_tile, (3, 4), board, reachable)
        assert ok, f"PLACE-01 應允許放置，但拒絕原因：{reason}"

    def test_place_01_multiple_neighbors_all_match(self):
        """
        PLACE-01 加強版：目標格 (3,4) 有兩個相鄰已建房間，
        所有共享邊均門對門或牆對牆 → 允許。
        """
        board = make_empty_board()
        # 西鄰：(3,3) 朝東有門
        place(board, 3, 3, make_tile(e=True))
        # 北鄰：(2,4) 朝南無門（牆）
        place(board, 2, 4, make_tile(s=False))
        reachable = {(3, 3)}

        # 新 tile：西門(w=True) 對接 (3,3) 東門；北牆(n=False) 對接 (2,4) 南牆
        new_tile = make_tile(w=True, n=False)
        ok, reason = can_place(new_tile, (3, 4), board, reachable)
        assert ok, f"PLACE-01 多鄰匹配應允許，但拒絕原因：{reason}"


# ═══════════════════════════════════════════════════════════════════════════════
# can_place — PLACE-02：來源匹配，但另一相鄰邊門對牆 → 禁止
# ═══════════════════════════════════════════════════════════════════════════════

class TestCanPlaceMismatch:
    """PLACE-02：即使入口門對門，第三個鄰邊衝突應拒絕。"""

    def test_place_02_third_neighbor_mismatch(self):
        """
        PLACE-02：
        - (3,3) 東門 ↔ 新 tile (3,4) 西門：匹配（來源可達）
        - (2,4) 南牆 ↔ 新 tile (3,4) 北門：門對牆衝突 → 拒絕
        """
        board = make_empty_board()
        place(board, 3, 3, make_tile(e=True))          # 西鄰：東門
        place(board, 2, 4, make_tile(s=False))          # 北鄰：南牆
        reachable = {(3, 3)}

        new_tile = make_tile(w=True, n=True)  # 西門對接 OK，但北門對上 (2,4) 南牆 → 衝突
        ok, reason = can_place(new_tile, (3, 4), board, reachable)
        assert not ok, "PLACE-02 門對牆衝突應拒絕"
        assert "edge_mismatch" in reason

    def test_place_02_source_wall_vs_neighbor_door(self):
        """
        來源可達且門對門，但另一鄰邊是牆對門（new 牆，neighbor 門）→ 拒絕。
        """
        board = make_empty_board()
        place(board, 3, 3, make_tile(e=True))          # 西鄰：東門（來源）
        place(board, 2, 4, make_tile(s=True))           # 北鄰：南門
        reachable = {(3, 3)}

        new_tile = make_tile(w=True, n=False)  # 北牆對上 (2,4) 南門 → 衝突
        ok, reason = can_place(new_tile, (3, 4), board, reachable)
        assert not ok, "PLACE-02 牆對門也應拒絕"
        assert "edge_mismatch" in reason


# ═══════════════════════════════════════════════════════════════════════════════
# can_place — PLACE-03：地圖外、已佔用、特殊房覆蓋 → 禁止
# ═══════════════════════════════════════════════════════════════════════════════

class TestCanPlaceInvalidCell:
    """PLACE-03：各種非法目標格情境。"""

    def test_place_03_out_of_bounds_negative(self):
        """PLACE-03：座標 (-1, 3) 超出地圖邊界。"""
        board = make_empty_board()
        place(board, 0, 3, make_tile(n=True, s=True))
        reachable = {(0, 3)}
        ok, reason = can_place(make_tile(), (-1, 3), board, reachable)
        assert not ok
        assert reason == "out_of_bounds"

    def test_place_03_out_of_bounds_overflow(self):
        """PLACE-03：座標 (7, 3) 超出地圖邊界。"""
        board = make_empty_board()
        reachable: set[tuple[int, int]] = set()
        ok, reason = can_place(make_tile(), (7, 3), board, reachable)
        assert not ok
        assert reason == "out_of_bounds"

    def test_place_03_cell_occupied(self):
        """PLACE-03：目標格已有 Tile（例如普通房間）→ 禁止。"""
        board = make_empty_board()
        place(board, 3, 3, make_tile(e=True))
        place(board, 3, 4, make_tile(w=True))  # 目標格已佔用
        reachable = {(3, 3)}
        ok, reason = can_place(make_tile(w=True), (3, 4), board, reachable)
        assert not ok
        assert reason == "cell_occupied"

    def test_place_03_overwrite_altar(self):
        """PLACE-03：嘗試覆蓋祭壇（已佔用的特殊格）→ 禁止。"""
        board = make_empty_board()
        place(board, 3, 3, make_tile(e=True))
        place(board, 3, 4, make_tile(w=True, kind="altar_a", special_state="unlocked"))
        reachable = {(3, 3)}
        ok, reason = can_place(make_tile(w=True), (3, 4), board, reachable)
        assert not ok
        assert reason == "cell_occupied"

    def test_place_03_overwrite_start(self):
        """PLACE-03：嘗試覆蓋起點格 → 禁止。"""
        board = make_empty_board()
        # 起點在 (3,3)，(3,2) 有房間連向起點
        place(board, 3, 3, make_tile(w=True, kind="start"))
        place(board, 3, 2, make_tile(e=True))
        reachable = {(3, 2), (3, 3)}
        ok, reason = can_place(make_tile(w=True), (3, 3), board, reachable)
        assert not ok
        assert reason == "cell_occupied"

    def test_place_03_door_faces_outside_p09(self):
        """
        [P09]：新房間的門不可朝向地圖外側。
        位置在第 0 列，新 tile 朝北（方向 N）有門 → 禁止。
        """
        board = make_empty_board()
        # 讓 (0,3) 有來源可達（從西鄰）
        place(board, 0, 2, make_tile(e=True))
        reachable = {(0, 2)}
        # 新 tile：西門對接 (0,2) 東門，但北門朝地圖外
        new_tile = make_tile(w=True, n=True)
        ok, reason = can_place(new_tile, (0, 3), board, reachable)
        assert not ok, "P09：門朝外應拒絕"
        assert "door_faces_outside_board" in reason


# ═══════════════════════════════════════════════════════════════════════════════
# can_place — PLACE-04：遠端不可達位置 → 禁止
# ═══════════════════════════════════════════════════════════════════════════════

class TestCanPlaceUnreachable:
    """PLACE-04：幾何上相容，但來源房間不在 reachable 集合內 → 禁止。"""

    def test_place_04_unreachable_source(self):
        """
        PLACE-04：(3,3) 朝東有門，(3,4) 為空，幾何上可接；
        但 (3,3) 不在 reachable（玩家無法到達）→ 拒絕。
        """
        board = make_empty_board()
        place(board, 3, 3, make_tile(e=True))
        reachable: set[tuple[int, int]] = set()  # 玩家無法到達任何格

        new_tile = make_tile(w=True)
        ok, reason = can_place(new_tile, (3, 4), board, reachable)
        assert not ok, "PLACE-04 不可達來源應拒絕"
        assert reason == "no_reachable_source"

    def test_place_04_isolated_island_blocked(self):
        """
        PLACE-04：地圖上有兩個互相不連通的島嶼，
        玩家在島嶼 A，嘗試從島嶼 B 擴建 → 拒絕。
        """
        board = make_empty_board()
        # 島嶼 A：玩家在 (1,1)，朝東有門，(1,2) 朝西有門
        place(board, 1, 1, make_tile(e=True))
        place(board, 1, 2, make_tile(w=True))

        # 島嶼 B：孤立的 (5,5) 朝東有門
        place(board, 5, 5, make_tile(e=True))

        # 玩家只能到達 A 島
        reachable = reachable_rooms(board, (1, 1))

        # 嘗試在 (5,6) 建造（來源為不可達的 (5,5)）
        new_tile = make_tile(w=True)
        ok, reason = can_place(new_tile, (5, 6), board, reachable)
        assert not ok, "PLACE-04 孤立島嶼不應允許建造"
        assert reason == "no_reachable_source"


# ═══════════════════════════════════════════════════════════════════════════════
# MOVE-01：門對門且未上鎖 → 可移動（進入可達集合）
# ═══════════════════════════════════════════════════════════════════════════════

class TestMove01:
    """MOVE-01：相鄰已建房間門對門且未上鎖 → 允許移動。"""

    def test_move_01_basic(self):
        """
        MOVE-01：(3,3)—東門—(3,4)—西門，玩家從 (3,3) 出發，
        reachable_rooms 應包含 (3,4)。
        """
        board = make_empty_board()
        place(board, 3, 3, make_tile(e=True))
        place(board, 3, 4, make_tile(w=True))
        result = reachable_rooms(board, (3, 3))
        assert (3, 4) in result, "MOVE-01 門對門應可移動"

    def test_move_01_altar_traversable(self):
        """
        MOVE-01：祭壇（altar_a, 未啟動）與普通房門對門 → 可進入。
        """
        board = make_empty_board()
        place(board, 3, 3, make_tile(e=True))
        place(board, 3, 4, make_tile(w=True, kind="altar_a", special_state=None))
        result = reachable_rooms(board, (3, 3))
        assert (3, 4) in result, "MOVE-01 祭壇門對門應可進入"

    def test_move_01_free_backtrack(self):
        """
        MOVE-03 關聯：玩家可沿連通道路自由回溯，三格直線所有格皆可達。
        """
        board = make_empty_board()
        place(board, 3, 1, make_tile(e=True))
        place(board, 3, 2, make_tile(w=True, e=True))
        place(board, 3, 3, make_tile(w=True))
        result = reachable_rooms(board, (3, 2))  # 從中間格出發
        assert result == {(3, 1), (3, 2), (3, 3)}, "MOVE-03 三格連通應全部可達"


# ═══════════════════════════════════════════════════════════════════════════════
# MOVE-02：門對牆、牆對牆、核心鎖住 → 禁止穿越
# ═══════════════════════════════════════════════════════════════════════════════

class TestMove02:
    """MOVE-02：各種不可穿越的情境。"""

    def test_move_02_wall_vs_door(self):
        """MOVE-02：來源朝東無門（牆），目標朝西有門 → 牆對門，不可穿越。"""
        board = make_empty_board()
        place(board, 3, 3, make_tile(e=False, n=True))  # 東方無門
        place(board, 3, 4, make_tile(w=True))            # 西方有門
        result = reachable_rooms(board, (3, 3))
        assert (3, 4) not in result, "MOVE-02 牆對門不可穿越"

    def test_move_02_door_vs_wall(self):
        """MOVE-02：來源朝東有門，目標朝西無門（牆）→ 門對牆，不可穿越。"""
        board = make_empty_board()
        place(board, 3, 3, make_tile(e=True))
        place(board, 3, 4, make_tile(w=False))
        result = reachable_rooms(board, (3, 3))
        assert (3, 4) not in result, "MOVE-02 門對牆不可穿越"

    def test_move_02_wall_vs_wall(self):
        """MOVE-02：兩格共享邊皆為牆 → 牆對牆，不可穿越。"""
        board = make_empty_board()
        place(board, 3, 3, make_tile(e=False))
        place(board, 3, 4, make_tile(w=False))
        result = reachable_rooms(board, (3, 3))
        assert (3, 4) not in result, "MOVE-02 牆對牆不可穿越"

    def test_move_02_locked_core(self):
        """MOVE-02 / GOAL-03：核心未解鎖，即使門對門也不可進入。"""
        board = make_empty_board()
        place(board, 3, 3, make_tile(e=True))
        place(board, 3, 4, make_tile(w=True, kind="core", special_state="locked"))
        result = reachable_rooms(board, (3, 3))
        assert (3, 4) not in result, "MOVE-02 鎖定的核心不可穿越"

    def test_move_02_no_diagonal(self):
        """移動只沿四方向（無斜向）：對角格不可到達。"""
        board = make_empty_board()
        place(board, 3, 3, make_tile())
        place(board, 4, 4, make_tile())
        result = reachable_rooms(board, (3, 3))
        assert (4, 4) not in result, "斜向不可移動"


# ═══════════════════════════════════════════════════════════════════════════════
# 整合測試：frontier + can_place 組合使用
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntegration:

    def test_frontier_to_can_place_flow(self):
        """
        整合：先計算 frontier，再對 frontier 內的格執行 can_place。
        起點 (3,3) 朝東有門 → frontier 包含 (3,4)
        → 新 tile 朝西有門放置 (3,4) → 合法。
        """
        board = make_empty_board()
        place(board, 3, 3, make_tile(e=True))
        reachable = reachable_rooms(board, (3, 3))
        f = frontier_cells(board, reachable)

        assert (3, 4) in f
        new_tile = make_tile(w=True)
        ok, reason = can_place(new_tile, (3, 4), board, reachable)
        assert ok, f"整合測試應允許放置，reason={reason}"

    def test_after_placement_frontier_expands(self):
        """
        放置後若新 Tile 有朝東的門，frontier 應進一步擴展。
        (3,3)東 → 放置 (3,4) 東西門 → frontier 新增 (3,5)。
        """
        board = make_empty_board()
        place(board, 3, 3, make_tile(e=True))

        # 模擬放置後更新 board
        new_tile = make_tile(w=True, e=True)
        place(board, 3, 4, new_tile)

        reachable = reachable_rooms(board, (3, 3))
        f = frontier_cells(board, reachable)
        assert (3, 5) in f, "放置後 frontier 應向東擴展"

    def test_place_then_cant_place_already_occupied(self):
        """
        放置後再嘗試放同一格 → 應因 cell_occupied 拒絕。
        """
        board = make_empty_board()
        place(board, 3, 3, make_tile(e=True))
        place(board, 3, 4, make_tile(w=True))  # 模擬第一次放置成功
        reachable = reachable_rooms(board, (3, 3))

        ok, reason = can_place(make_tile(w=True), (3, 4), board, reachable)
        assert not ok
        assert reason == "cell_occupied"

    def test_cross_tile_all_four_directions(self):
        """
        十字房型四面都有門，放置在地圖中央 (3,3) 附近，
        frontier 應向所有非邊界空格延伸。
        """
        board = make_empty_board()
        # 起點 (3,3) 朝東有門
        place(board, 3, 3, make_tile(e=True))
        reachable = {(3, 3)}

        # 在 (3,4) 放置十字房（W 門對接來源，另三方向均有門）
        cross = make_tile(n=True, e=True, s=True, w=True)
        ok, reason = can_place(cross, (3, 4), board, reachable)
        assert ok, f"十字房應可放置，reason={reason}"

        place(board, 3, 4, cross)
        reachable2 = reachable_rooms(board, (3, 3))
        f = frontier_cells(board, reachable2)

        # 十字房的 N/E/S 均指向地圖內空格 → 均應在 frontier
        assert (2, 4) in f, "十字房北方應在 frontier"
        assert (3, 5) in f, "十字房東方應在 frontier"
        assert (4, 4) in f, "十字房南方應在 frontier"


INVALID_POSITIONS = [(-1, 3), (3, -1), (7, 3), (3, 7), (-8, 3), (3, 8)]


@pytest.mark.parametrize("pos", INVALID_POSITIONS)
def test_invalid_start_returns_empty(pos):
    board = make_empty_board()
    # Populate every cell so negative indices cannot silently pass as empty.
    for row in range(BOARD_SIZE):
        for col in range(BOARD_SIZE):
            board[row][col] = make_tile(n=True, e=True, s=True, w=True)
    assert reachable_rooms(board, pos) == set()


@pytest.mark.parametrize("pos", INVALID_POSITIONS)
def test_frontier_ignores_invalid_coordinates(pos):
    board = make_empty_board()
    place(board, 3, 3, make_tile(e=True))
    place(board, 6, 3, make_tile(s=True))
    place(board, 3, 6, make_tile(e=True))
    assert frontier_cells(board, {(3, 3), pos}) == {(3, 4)}


@pytest.mark.parametrize("blocked", [(3, 3), (3, 4)])
def test_extra_lock_blocks_start_or_neighbor(blocked):
    board = make_empty_board()
    place(board, 3, 3, make_tile(e=True))
    place(board, 3, 4, make_tile(w=True, e=True))
    place(board, 3, 5, make_tile(w=True))
    expected = set() if blocked == (3, 3) else {(3, 3)}
    assert reachable_rooms(board, (3, 3), {blocked}) == expected


@pytest.mark.parametrize("size", [0, -1, 3, 6, 8])
def test_board_factory_rejects_other_sizes(size):
    with pytest.raises(ValueError, match="7"):
        make_empty_board(size)


def test_board_has_seven_independent_rows():
    board = make_empty_board(BOARD_SIZE)
    assert len(board) == BOARD_SIZE
    assert all(len(row) == BOARD_SIZE for row in board)
    place(board, 0, 0, make_tile())
    assert all(board[row][0] is None for row in range(1, BOARD_SIZE))


@pytest.mark.parametrize("shape", ["empty", "short", "large", "ragged"])
@pytest.mark.parametrize("query", ["reachable", "frontier", "placement"])
def test_queries_reject_malformed_boards(shape, query):
    board = make_empty_board()
    if shape == "empty":
        board = []
    elif shape == "short":
        board.pop()
    elif shape == "large":
        board.append([None] * BOARD_SIZE)
    else:
        board[6].pop()
    with pytest.raises(ValueError, match="7"):
        if query == "reachable":
            reachable_rooms(board, (3, 3))
        elif query == "frontier":
            frontier_cells(board, {(3, 3)})
        else:
            can_place(make_tile(), (3, 4), board, {(3, 3)})


@pytest.mark.parametrize("doors", list(product((False, True), repeat=4)))
def test_rotations_follow_north_east_south_west(doors):
    # Independent expected orientations, including symmetric room shapes.
    for turns in range(8):
        expected = tuple(doors[(direction - turns) % 4] for direction in DIRECTIONS)
        assert rotate_doors(doors, turns) == expected


@pytest.mark.parametrize("direction", DIRECTIONS)
@pytest.mark.parametrize("new_door,neighbor_door", [(False, True), (True, False)])
def test_mismatch_rejected_among_four_occupied_neighbors(direction, new_door, neighbor_door):
    board = make_empty_board()
    doors = [True] * 4
    doors[direction] = new_door
    reachable = set()
    for side in DIRECTIONS:
        pos = neighbor_pos(3, 3, side)
        other_doors = [False] * 4
        other_doors[OPPOSITE[side]] = neighbor_door if side == direction else True
        place(board, *pos, Tile("room", tuple(other_doors)))
        reachable.add(pos)
    ok, reason = can_place(Tile("room", tuple(doors)), (3, 3), board, reachable)
    assert not ok
    assert "edge_mismatch" in reason


@pytest.mark.parametrize("pos,outside,source", [
    ((0, 0), N, E), ((0, 6), E, S),
    ((6, 6), S, W), ((6, 0), W, N),
])
def test_corner_outward_door_rejected(pos, outside, source):
    board = make_empty_board()
    source_pos = neighbor_pos(*pos, source)
    source_doors = [False] * 4
    source_doors[OPPOSITE[source]] = True
    place(board, *source_pos, Tile("room", tuple(source_doors)))
    doors = [False] * 4
    doors[source] = True
    assert can_place(Tile("room", tuple(doors)), pos, board, {source_pos}) == (True, "ok")
    doors[outside] = True
    ok, reason = can_place(Tile("room", tuple(doors)), pos, board, {source_pos})
    assert not ok
    assert "door_faces_outside_board" in reason


def test_queries_preserve_room_and_event_state():
    board = make_empty_board()
    place(board, 3, 3, make_tile(e=True, event_resolved=True))
    place(board, 3, 4, make_tile(w=True, e=True, event_outcome={"hp": -1}))
    candidate = make_tile(w=True, event_category="supply", event_outcome={"supplies": 1})
    before = deepcopy((board, candidate))
    reachable = reachable_rooms(board, (3, 3))
    assert frontier_cells(board, reachable) == {(3, 5)}
    assert can_place(candidate, (3, 5), board, reachable) == (True, "ok")
    assert not can_place(candidate, (3, 4), board, reachable)[0]
    assert (board, candidate) == before

