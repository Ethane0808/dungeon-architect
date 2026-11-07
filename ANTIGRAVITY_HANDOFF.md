# Antigravity / Codex 開發交接指令

以下文字可直接貼給 AI Agent 開始第一階段開發。**不要一次產出整款遊戲。**

---

你要協助我們開發 Python 3.14.7 + pygame-ce 期末遊戲 **Dungeon Architect**。

**先閱讀且遵守：**
1. `README.md`
2. `GAME_DESIGN.md`（規則唯一來源）
3. `DECISIONS.md`（已確認 vs 暫定狀態）
4. `TECH_SPEC.md`（資料與演算法契約）
5. `TEST_PLAN.md`（驗收條件）

規則標籤 `[CONFIRMED]` 必須遵守；`[PROVISIONAL]` 是一致的原型實作假設，放入設定檔以便修改；`[POST-MVP]` 不可先實作。

## 第一個實作任務（只做這個）

建立純 Python 的地圖／房間規則模組，不必做正式遊戲 UI：

- 7×7 Board 與 N,E,S,W 四方向房間資料。
- 支援房間旋轉 0/90/180/270 度。
- `can_place(tile, pos, board, reachable_rooms)`：驗證邊界、空格、門對門、牆對牆、來源可達性及所有已建造鄰邊。
- `reachable_rooms(board, start, locked_specials)`：用 BFS/DFS 取得真正可通行的房間集合。
- `frontier_cells(board, reachable_rooms)`：從有門的可達房間找到可用擴張格。
- 寫 pytest 測試，至少覆蓋 `TEST_PLAN.md` 的 ROT-01、PLACE-01~04、MOVE-01~02。
- 先不要加入抽卡、事件、Boss、道具、美術與動畫。

開始前請先列出你計畫新增或修改的檔案，再實作；完成後提供：變更摘要、測試結果、已知限制，以及第二階段可開始的條件。不可宣稱沒有執行過的測試已通過。

---

## 後續循序開發提示

第一階段通過後，再依序製作：三張卡保底 → Pygame 地圖與卡片預覽 → 移動 → 首次事件 → 資源與補救道具 → 祭壇與核心 → 勝敗結算。每次只開發一部分、附測試、回報與規格的差異。


## 跨語言政策（適用於 Antigravity 與 Codex）

可以為明確技術需求使用 Python 之外的程式語言，但 Python 必須占所有自行編寫的程式碼行數 **嚴格超過 50%**。修改前先查閱 `TECH_SPEC.md` 的統計範圍；修改完成及提交 PR 前核算比例，依 `TEST_PLAN.md` 的 LANG-01~05 回報結果。不得藉由無效或重複程式碼灌高 Python 比例。課程官方算法優先。
