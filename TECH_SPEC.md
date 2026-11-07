# Dungeon Architect — 技術規格（MVP）

**狀態：** v0.9 / 實作建議，受 `GAME_DESIGN.md` 規則約束。

## 1. 技術範圍

- Python 3.14.7 + pygame-ce。單機、單人、2D 俯視格子遊戲。
- 遊戲邏輯不得直接依賴 pygame 渲染，方便單元測試。
- JSON 用於關卡、房型、事件機率、暫定數值；資料載入時驗證。
- 不需要後端資料庫／網路；遊戲存檔不列為 MVP 必須。

## 1.1 程式語言使用規範（課程硬性限制）

- **允許使用 Python 以外的程式語言**，例如 JavaScript、TypeScript、HTML/CSS 或 C++，但須有明確技術用途；不可為了「混用語言」而引入不必要依賴。
- **Python 必須占全部自行編寫程式碼的 50% 以上（嚴格大於 50%，不是剛好 50%）**。在未有教師指定算法前，暫以「非空白、非純註解的原始碼行數（SLOC）」估算：`Python SLOC / 所有語言 SLOC × 100% > 50%`。
- 計算範圍包括本組自行編寫的主程式、UI、工具腳本及測試（不限檔案副檔名）；排除第三方依賴、套件快取、生成碼、編譯成果、素材、資料檔、文件與 lockfile。不以重複或無效的 Python 程式碼湊比例。
- 新增其他語言或大型程式碼前，以及 Codex 修正完成、PR 合併前，皆須重新檢查比例；未達標不得合併。
- 若課程有官方的語言比例計算標準或工具，**以課程規範優先**，並據此更新本節及驗收方法。此條是技術限制，不改變 `GAME_DESIGN.md` 的遊戲規則。


## 2. 建議檔案結構（尚未建立程式）

```text
main.py
engine/
  models.py        # Tile, Card, Player, Board, GameState
  directions.py    # 方向、旋轉、相對邊
  placement.py     # 枚舉邊界、放置合法性、道具修正
  graph.py         # 可通行道路、BFS/DFS、可抵達目標
  deck.py          # 三選一與合法性保底
  events.py        # 事件生成、首次觸發、資源結算
  objectives.py    # 祭壇、核心、勝敗判定
  game.py          # 遊戲狀態與動作協調
ui/
  screens.py       # 畫面繪製與操作回饋
  widgets.py       # 卡片、狀態列、預覽與訊息
assets/             # 圖像、字型、音效；版權要有來源
 data/             # 可從本文件夾拷貝示例 JSON
 tests/            # Python 單元／整合測試
```

## 3. 座標、方向與房間表示

- Board 是 `7×7`，`board[row][col]`，row/col 範圍 0–6。
- Phase 1 API 契約：`make_empty_board(size=7)` 拒絕其他尺寸；`reachable_rooms`、`frontier_cells`、`can_place` 收到非 7×7（包含不等長列）的 Board 時拋出 `ValueError`。
- `reachable_rooms` 的越界、空格或鎖定起點回傳空集合；`locked_specials` 同樣適用於起點。`frontier_cells` 忽略輸入集合中的越界座標；`can_place` 的越界目標回傳 `(False, "out_of_bounds")`。
- 房間的 `doors` 使用 `tuple[bool,bool,bool,bool]`，順序 **N,E,S,W**。
- 朝順時針 90° 旋轉：`new = (old[3],old[0],old[1],old[2])`。重複四次恢復原狀。
- 房間包含：`kind`, `doors`, `event_category`, `event_outcome`, `event_resolved`, `is_special`, `special_state`。
- 特殊房可有 `locked` 狀態；`door_match` 是幾何規則，`can_traverse` 是通行規則，必須分開。
- 房間卡上的事件類別和完整隨機結果在建立卡片時固定，進入房間後只更新 `event_resolved`。

## 4. 建議資料結構

```python
@dataclass
class Tile:
    kind: str
    doors: tuple[bool, bool, bool, bool]
    event_category: str | None = None
    event_outcome: dict | None = None
    event_resolved: bool = False
    special_state: str | None = None

@dataclass
class GameState:
    board: list[list[Tile | None]]
    player_pos: tuple[int, int]
    hp: int
    supplies: int
    altar_activated: dict[str, bool]
    core_unlocked: bool
    cards: list[Tile]
    build_turn: int
    game_status: str  # playing, win, lose
    used_items: dict[str, int]
    rng_seed: int
```

以上只是介面草案，可因實作需要調整，但**行為契約不得改變**。

## 5. 核心演算法契約

### 5.1 可通行圖與 frontier

1. 從角色位置 BFS/DFS 取得所有 `can_traverse` 可抵達的已建造房間。
2. 由這些房間各有門朝向的地圖內空白格產生候選 `frontier`。
3. 對每個 frontier 枚舉房型與四種旋轉（去除相同旋轉）檢查合法性；同時考慮所有已建造的鄰格。
4. 禁止不在地圖內、覆蓋特殊格、入門不連通、門牆衝突及（若採 P09）門指向界外的放置。

### 5.2 三卡抽取

```text
legal = enumerate_legal_normal_placements(state)
if legal 非空:
    至少選入一張可合法放置的房型卡
    若存在第二種不同合法房型：提高其機率，但不保證
    抽取其餘卡片並附上事件類別／結果
    洗牌後顯示三張
else:
    不執行無限重抽；進入 no_legal_placement 處理
```

### 5.3 放置與進入事務

- `preview` 不得修改任何資源、事件狀態或遊戲回合。
- `commit` 再檢查合法；成功後才寫入 Tile／消耗卡與道具／建造回合 +1。
- **P05 暫定：** 角色移入新房，若普通事件未觸發則結算並標記 `event_resolved=True`。
- 更新祭壇狀態／解鎖核心／勝敗；再抽下一輪卡片。
- 任一步失敗都不應只改動一半資料；若涉及多邊修改，需保證原子性。

### 5.4 道具原子修改

- Door Seal：只能封**新房間**的非必需進入門；封完必須重新跑所有邊匹配，否則不得收費或寫入。
- Emergency Chisel：只能對可達一般既有房間朝地圖內**空格**的一面牆開門；完成後重建 frontier，並重新抽卡。
- 道具使用時需檢查餘額、使用上限、與特殊房間限制。

### 5.5 勝敗

- `win` 只能在全部主線目標已啟動、核心解鎖且玩家已進入核心後成立。
- `lose_hp` 應在事件結算後檢查。
- `no_progress` 不等於 `no_normal_placement`：須納入可抵達但未完成的目標、可觸發收益事件、可負擔的有效道具。若程式不能確定全局無解，允許玩家手動重開，不要假裝有完美全局求解。

## 6. UI 建議

地圖畫面顯示 7×7 格、可探索的空格高亮、房間旋轉預覽、當前三張卡及事件類別、HP/Supplies、祭壇/核心狀態。非法放置有具體理由；角色不能走穿牆。遊戲停止狀態有重新開始操作。

## 7. 測試可重現性

亂數統一由 `random.Random(seed)` 管理，保持牌序與事件結果可重現。可顯示 seed 給除錯人員。細節見 `TEST_PLAN.md`。
