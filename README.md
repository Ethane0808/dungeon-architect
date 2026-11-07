# Dungeon Architect — MVP 開發文件

> 規格版號：**v0.9 / Implementation Baseline**  
> 編寫日期：2026-11-05  
> 文件用途：小組共同開發、Antigravity / Codex 工作交接、MVP 測試驗收。

## 專案定位

Dungeon Architect 是一款 Python 3.14.7 + pygame-ce 製作的單人 2D 空間規劃與地城探索遊戲。玩家從三張候選房間中選擇一張、旋轉並嚴格拼接，逐步建構自己的地下城。HP 與 Supplies 提供輔助性的風險與策略取捨。

**兩階段原則：** MVP 必須可獨立遊玩、成功或失敗；MVP 完成並測試後，才進入 Final Goal，設計回合制、空間解謎或混合 Boss 相關玩法。現階段**不實作 Boss 戰鬥或主動干擾**。

## 文件導覽

| 文件 | 用途 | 主要讀者 |
|---|---|---|
| `GAME_DESIGN.md` | 遊戲循環、完整 MVP 規則、已確認與暫定內容 | 全員／AI Agent |
| `DECISIONS.md` | 設計決策溯源與待正式確認項目 | 遊戲設計負責人 |
| `TECH_SPEC.md` | 模組、資料模型、狀態轉換及演算法契約 | 程式開發人員 |
| `TEST_PLAN.md` | 核心規則驗收、測試情境與失敗分類 | 測試／整合人員 |
| `DEVELOPMENT_GUIDE.md` | 開發環境、協作、AI 輔助開發流程 | 所有組員 |
| `TASKS.md` | MVP 與 Final Goal 開發里程碑、工作拆分 | 所有組員 |
| `data/prototype_config.json` | **暫定測試值**，不是最終平衡數據 | 程式開發人員 |
| `data/sample_level.json` | 7×7 **示範布局**，非正式關卡定稿 | 程式／測試人員 |
| `requirements.txt` | 遊戲執行依賴 | 開發人員 |
| `requirements-dev.txt` | 可選測試依賴 | 測試人員 |

## 規則優先順序

1. `GAME_DESIGN.md` 中標記 **[CONFIRMED]** 的設計原則。
2. `GAME_DESIGN.md` 中標記 **[PROVISIONAL]** 的 MVP 暫定實作規則，供第一版一致實作。
3. `data/prototype_config.json` 中可調整的測試數值。
4. `DECISIONS.md` 的後續變更紀錄；經全組同意後升版。

任何未列入 MVP 的功能，不能由 AI 自行補充成必需項目。若規則有矛盾，先記錄問題再修改，不要在不同模組加入不同的隱含假設。

## 程式語言限制

本專題允許視需要使用其他程式語言，但 **Python 自行編寫原始碼占比必須嚴格高於 50%**。目前以非空白、非純註解的原始碼行數（SLOC）計算，包含測試與工具腳本，排除依賴與生成碼；若教師指定不同方法，優先遵守課程標準。詳細規則及驗證方式請見 `TECH_SPEC.md`、`TEST_PLAN.md`。


## MVP 定義

玩家能：開始一局 → 看見 7×7 地圖與目標 → 從三張房間卡選擇、旋轉與合法放置 → 沿連通道路免費探索 → 進入房間觸發一次事件 → 管理 HP／Supplies 並使用有限補救 → 完成關卡目標或得到明確失敗結果 → 重新開始。

**現階段不要求：** Boss 回合制、複雜 RPG、AI 敵人、存檔系統、線上多人、精美美術或完全程序生成的關卡。

## 使用提醒

這是**可開始寫程式的 MVP 開發基準**，不是團隊已核准所有細節的最終 `v1.0`。詳見 `DECISIONS.md` 末尾的待確認事項。`sample_level.json` 提供一組幾何上存在合法連通配置的測試關卡，不表示每一串隨機抽牌都必然可通關。
