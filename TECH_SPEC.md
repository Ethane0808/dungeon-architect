# 技術規格

## 1. 技術範圍

Python 負責遊戲狀態與規則，pygame-ce 負責輸入和繪圖。引擎可獨立載入及測試。

### 1.1 課程語言要求

Python 須占全部自行編寫原始碼 **嚴格大於 50%**。若教師未指定算法，以非空白、非純註解的原始碼行數計算。計入主程式、UI、工具與測試，排除依賴、快取、生成碼、編譯成果、素材、資料、文件與 lockfile。重大整合與交付前核對比例，課程指定算法優先。

## 2. 目前模組

| 路徑 | 職責 |
|---|---|
| `main.py` | 解析 `--seed`（省略時隨機選取）、啟動與清理 pygame。匯入模組時不開視窗。 |
| `engine/directions.py`、`engine/models.py` | 方位、旋轉、`Tile`、棋盤與通行狀態。 |
| `engine/placement.py` | BFS 可達性、候選空格與嚴格拼接。 |
| `engine/navigation.py` | 純 Python 的施工入口判定、穩定 BFS 與最近入口路由，不依賴 pygame。 |
| `engine/cards.py` | 設定驗證、合法放置枚舉、加權抽卡及隱藏事件抽選。 |
| `engine/game.py` | 保留 `BuildSession` 的 Phase 4 建造與事件控制器，供 MVP 擴充及既有測試重用。 |
| `engine/mvp.py` | `MvpSession(BuildSession)` 串接固定關卡、目標、工具、勝負、原子操作與重開。 |
| `engine/level.py` | 不可變關卡設定、固定房門向與潛在連通驗證。 |
| `engine/tools.py` | 工具設定與純幾何變更，費用及提交由 session 處理。 |
| `engine/demo.py`、`data/mvp_demo.json` | 透過公開動作重播 seed 159 通關，不覆寫棋盤、卡片或平衡值。 |
| `engine/events.py` | 讀取類別效果、純函式結算，以及帶實際資源變化的事件通知。 |
| `engine/resources.py` | 不可變的 HP／Supplies 快照、範圍驗證與整數增減。 |
| `ui/app.py`、`ui/screens.py` | 輸入轉交 session，繪製地圖、牌面和操作回饋。 |
| [`data/prototype_config.json`](data/prototype_config.json) | 載入地圖、房型、抽牌、事件、資源、目標與工具設定；v0.10 的目標包含明確門向。 |

## 3. 座標與方向

棋盤使用 `board[row][col]`，row、col 為 0–6。UI 顯示欄 A–G、列 1–7，棋盤點擊區域排除右側和下側的外邊界。門牆用布林 tuple 按 N、E、S、W 表示，順時針旋轉 90° 為 `(old[3], old[0], old[1], old[2])`。

## 4. 資料與通行

`Board` 是 7×7 的 `Tile | None` 格陣，`None` 表示空格。主程式載入 `LevelConfig` 的固定房間：預設起點 `(3, 0)` 向北／東／南，祭壇 `(0, 6)` 向南／西、`(6, 6)` 向北／西，核心 `(3, 6)` 向北／南／西。特殊房間的鎖定狀態會影響 BFS 通行，門牆仍照常參與放置驗證。棋盤形狀錯誤會拋出 `ValueError`。原本 `BuildSession` 仍可單獨用於只有起點的 Phase 4 沙盒。

## 5. 規則與狀態更新

### 5.1 可達性與放置

| 介面 | 行為 |
|---|---|
| `reachable_rooms(board, start, locked_specials=())` | BFS 只沿相通且可通行的門走訪。起點越界、為空或上鎖時回傳空集合。 |
| `frontier_cells(board, reachable)` | 找出可達房間的門所朝向的地圖內空格，略過越界來源。 |
| `can_place(tile, pos, board, reachable)` | 依序檢查邊界、空格、朝外的門、至少一個可達入口、全部已建鄰邊，回傳 `(ok, reason)`。 |

### 5.2 抽卡

`enumerate_legal_placements` 對所有候選空格、房型與去重後的旋轉驗證，回傳依位置、房型、旋轉排序的合法選項。旋轉以相對房型基準方向的順時針四分之一圈表示。

`draw_cards(board, start, *, rng, config=None, locked_specials=())` 使用呼叫端提供的 `random.Random`。有合法放置時回傳 `ready`，包含三張卡、整張地圖的合法放置快照與可用卡索引。第一個名額從合法房型抽取，其餘名額提高尚未出現的不同合法幾何形狀的權重。抽出類別後洗牌。無合法放置時回傳 `blocked` 和空資料，保留 RNG 狀態。

`load_card_config` 驗證 7×7、三張卡與強制保底。權重須有限且非負，房型池與各事件池各有正權重，多樣性倍率須至少為 1。合法池權重全為零時，保底名額從該池均勻抽取。

### 5.3 建造與重開

`BuildSession.preview` 和 `legal_cells` 只讀狀態。選卡和旋轉只更新預覽狀態，保留棋盤、手牌、回合與亂數。 `place` 以目前棋盤重新驗證，在暫存資料準備新房間、自動進入事件及下一手，成功才一次更新棋盤、角色、手牌、回合、資源及事件通知。若事件準備失敗則不提交；若抽下一手失敗則另還原亂數狀態。 `restart` 以原 seed 與初始資源快照重建整局。

`BuildSession` 保留原沙盒的全圖建造語義。`MvpSession.geometry_preview`／`planning_cells` 驗證全圖幾何與既有守衛施工路線，供抽牌保底和青色規劃格使用；`preview`／`legal_cells` 再要求 `is_local_build_source`，玩家必須位於相鄰且門對門的入口。封門版本以封門後的 doors 做相同分層驗證。`place` 與 `place_with_seal` 在 live state 及私有 candidate 都重驗現地條件，遠端失敗不改棋盤、玩家、資源、工具、手牌、回合或 RNG。

`build_entries` 只接受可通行、在玩家可達集合且與新房門對門的既有房。`shortest_path` 透過 `connected_neighbors` 依 N/E/S/W 做 BFS，路徑含起點與入口、不含未建造目標。`route_to_build_site` 依 `(步數, entry_row, entry_col)` 選入口。UI 的不可變 `BuildPlan` 保存目標、入口、路徑、卡片索引、旋轉與封門方向；任何相關選擇改變都取消計畫。

### 5.4 移動與首次進房事件

`movement_preview(pos)` 回傳 `(ok, reason)`，確認目標相鄰、在地圖內、兩側有門且可通行，不改狀態。`move(pos)` 再驗證並移動一格；只在首次進入普通事件房時更新該房間的 `event_resolved`、`event_outcome`、資源與 `current_event`。起點、祭壇與核心不套用普通事件。普通移動保留手牌、旋轉方向、建造回合與抽牌亂數狀態。

pygame 自動導航每 250ms 最多取 `BuildPlan.path` 的下一格，並呼叫正常的 `MvpSession.move()`，不直接寫入玩家位置。下一格是 `guard_pos`／`guard_next` 時先停；成功一步後若 HP、事件、祭壇或終局改變也停。到入口只顯示確認提示，Enter 才呼叫正式建造。Esc、重開、大廳與終局會清除計畫；手動移動與道具操作會停止自動行走。

`place` 沿用 Phase 3 自動進房，與 `move` 共用 `_prepare_entry`，避免放置與進房各發一次獎勵。`Tile.event_outcome` 記錄套用上下限後的實際 `hp`／`supplies` 變化；已滿而增加 0 也會標記結算。`current_event` 保留最後一次新事件，重訪與無效操作不更新，重開清除。

`EventConfig.from_mapping(data)` 讀取 `events.categories` 與 `events.outcomes`。每類事件可設基本效果與一組 `variants`，各項可指定 `message`、整數 `hp_delta`、`supplies_delta` 與非負整數 `trapped_cache`。`resolve_event(category, pos, resources, config, seed)` 以局種子、座標與類別建立獨立亂數來源，按各項的正整數 `weight`（預設 1）從基本效果與各變體中選取一項，並回傳資源快照與通知。省略 seed 時使用基本效果。首次進房後，`Tile.trapped_cache` 保存未開箱的補給數量，成功開箱後歸零。開箱產生獨立的事件通知。

房型對類別的機率由 `weights_by_kind` 與 session RNG 決定；事件目前直接套用每類設定的效果，不另外抽亂數。因此固定 seed 與相同操作重現相同事件，且不改變既有牌序。卡面只呈現房型傾向，不公開已抽定的精確類別；預覽不會重新抽取或結算效果。

### 5.5 HP 與 Supplies API

`Resources(hp, hp_max, supplies, supplies_max=None, supplies_min=0)` 是不可變資料。建構時拒絕非整數（包括 bool）、非正 HP 上限、越界 HP、負 Supplies 下限與越界 Supplies。

| API | 行為 |
|---|---|
| `load_resources(path=DEFAULT_CONFIG_PATH)` | 從 `player.hp_initial`、`hp_max`、`supplies_initial`、選用的 `supplies_max`／`supplies_min` 建立初始值。 |
| `resources.apply(hp_delta=0, supplies_delta=0)` | 回傳新的有界快照；HP 固定下限 0，Supplies 下限預設 0。`supplies_max=None` 表示無上限。 |
| `resources.hp_depleted`／`session.hp_depleted` | HP 為 0 時為 True；純資源物件不判定勝負。`MvpSession` 會轉為 LOST 並停止操作。 |
| `session.resources` | 目前 HP、HP 上限、Supplies 及其上下限，供 HUD 只讀顯示。 |
| `BuildSession(..., resources=None, event_config=None)` | 可注入初始資源與事件設定；預設讀取原型 JSON，重開沿用同一份初始快照。 |

資源物件不自行收費、回合補給或再生；工具與里程碑由 MVP 控制器套用。既有 JSON 的所有平衡數值仍為 P08 暫定試玩值。

### 5.6 關卡與目標 API

`SpecialRoom(kind, pos, doors)` 與 `LevelConfig(start, altars, core, first_altar_supplies=1, ..., guard_build_limit=11)` 是不可變資料。`load_level_config()` 讀取 `objectives.start`／`core` 的 `{pos, doors}`、`altars` 的 `[{id, pos, doors}, ...]`、第一座祭壇補給及 `guard.build_limit`。祭壇至少一座，預設兩座；數量、座標、門向與守衛建造門檻皆可調整。

驗證拒絕非 7×7、非整數座標、非布林門向、門朝外、重疊、重複名稱與固定鄰房門牆衝突。潛在路線驗證把空格視為可配置通路：所有祭壇需在不穿過鎖定核心的條件下有潛在路線，核心解鎖後需有潛在路線。這不是牌序或全局可解性保證。`make_board()` 每次建立全新 Tile，核心為 locked，祭壇尚未啟動。

`MvpSession(..., level=None, tools=None)` 預設載入關卡與工具，也保留 `BuildSession` 的 seed、卡片、資源與事件設定注入介面。`activated_altars` 是實際進入過的祭壇 id 集合；不是 BFS 可達集合。首次讓祭壇進入可達集合或達到 `guard_build_limit` 時，`guard_wake_reason` 記錄 `altar` 或 `construction`，守衛先出現並預告下一步。`core_unlocked` 只在所有設定祭壇都已啟動時成立；進入解鎖核心才轉為 WON。第一次啟動祭壇給設定的 Supplies，受上限限制且不重複發放。

### 5.7 工具 API

`ToolRule(cost_supplies, max_uses_per_game)` 驗證正整數費用與非負整數次數；`ToolConfig` 從既有 `items.door_seal`／`emergency_chisel` 載入。`tool_uses` 記錄本局成功次數。可花額為 `supplies - supplies_min`，不能靠下限截斷而少付。

| API | 行為 |
|---|---|
| `geometry_preview_with_seal`／`planning_cells_with_seal` | 依封門後 doors 驗證費用、全圖幾何與可規劃位置；不改狀態。 |
| `preview_with_seal(pos, direction)`／`legal_cells_with_seal(direction)` | 在全圖驗證後再要求玩家位於相鄰門對門入口；不改狀態。 |
| `place_with_seal(pos, direction)` | 與建造、自動進房、事件及下一手一起提交費用和次數；失敗完全保留原狀態。 |
| `chisel_preview(source, target)` | 來源須可達，雙方是相鄰既有未鎖定房間，共用邊須牆對牆。 |
| `chisel(source, target)` | 同時開兩側門，扣費及計次，重新計算可達與合法位置；不自動移入、不啟動祭壇、不觸發事件。 |

有現成手牌時，目標解鎖或鑿壁只更新合法位置快照，保留卡片、旋轉與亂數。若原本 blocked 且手牌為空，恢復合法普通建造後才抽新保底手牌。沒有無限重抽。

### 5.8 原子更新與終局

每個 MVP 建造、移動與工具動作先準備私有候選狀態：複製棋盤列、旋轉、使用次數與 RNG；Tile 變更使用 `dataclasses.replace`。沿用 Phase 4 放置／進房驗證，所有事件、目標與抽卡準備完成後才提交。抽牌或目標更新途中例外不會改動原棋盤、HP、Supplies、目標、使用次數、手牌或 RNG。

狀態為 `PLAYING`、`WON` 或 `LOST`。HP 歸零為 LOST；全部祭壇啟動並進入核心為 WON。終局拒絕選卡、旋轉、放置、移動與工具，僅保留重開及離開。blocked 只代表沒有普通合法放置，不代表敗北；不做全局可解性偵測。`restart()` 以原始設定及 seed 還原整局。
