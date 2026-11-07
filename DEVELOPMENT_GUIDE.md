# Dungeon Architect — 組員開發環境與協作 Guide

## 1. 建議環境

- Windows 11 / Python **3.14.7** / pygame-ce / VS Code 或 Antigravity。
- Git / GitHub 用於協作。可使用系統 Python，**虛擬環境不是本專題的必要前提**。
- 已安裝 pygame-ce 者仍應執行依賴檢查；注意可能的 pygame 與 pygame-ce 套件衝突。

## 2. 取得專案與安裝

請使用小組實際的 GitHub repository URL；本文件不假設已決定哪個 URL。

```powershell
git clone <YOUR_REPOSITORY_URL>
cd <YOUR_REPOSITORY_FOLDER>
python --version
python -m pip install -r requirements.txt
python -c "import pygame; print(pygame.version.ver)"
```

如果 `python` 指向錯誤版本，可嘗試 Windows Python Launcher：`py -3.14 --version`、`py -3.14 -m pip install -r requirements.txt`。

**注意：** 僅在 `main.py` 已經實作並提交後，才能透過 `python main.py` 啟動；這份文件包是規格文件，不是已完成的遊戲程式。

## 3. Git 工作流

1. `git pull` 取得最新主分支。
2. 一項任務開一個短功能分支，例如 `feature/tile-placement`。
3. 完成小範圍功能及測試，執行 `git add`、`git commit`、`git push`。
4. 請其他組員 review，再合併到 `main`。
5. 修改規則需同步改 `GAME_DESIGN.md`、`DECISIONS.md` 與測試。

請勿提交 API 密鑰、暫存快取、Python `__pycache__/`、`.env`、個人 IDE 設定和編譯後檔案。若 Repository 為 private，需要先邀請組員。

## 4. AI Agent 使用原則

- 以 `GAME_DESIGN.md` 作為行為規格，以 `TECH_SPEC.md` 作為架構建議。
- 每次只要求 AI 實作**一個模組或一條規則**，例如先做旋轉與邊界驗證。
- 要求 AI 同時提供測試案例與變更摘要，不接受未經審查的大型一次性重寫。
- 未經團隊確認，禁止 AI 加入 Boss 戰鬥、裝備系統、能量貨幣或其他規格以外玩法。
- 遇到標記 [PROVISIONAL] 的參數，放入設定檔而非散落的魔法數字。
- 影響可解性／資源平衡的修改，需要用固定 seed 重現比較。

## 4.1 程式語言與程式碼占比

- Python 是主要語言；如有明確需要，允許使用其他語言開發附屬功能。
- 每位組員或 AI Agent 新增非 Python 程式碼前，須說明用途、預估新增規模與對 Python 占比的影響。
- 在 Pull Request 描述中回報目前 Python SLOC、所有語言總 SLOC 及占比。以 `TECH_SPEC.md` 的統計範圍為準，**Python 比例必須 > 50%** 才可合併。
- 禁止加入填充式、重複、無功能用途的 Python 程式碼來人為提高比例。
- 若課程指定計算工具或百分比依據，應優先使用該規範。


## 5. 第一輪建置順序

`方向與房型 → 7×7 Board → 嚴格拼接 → BFS/DFS 可達性 → 三選一／保底 → UI 放置預覽 → 移動 → 事件 → 資源與道具 → 祭壇／核心 → 勝敗測試 → 遊玩測試`。

不同組員可以平行開發 UI 與邏輯，但需共同確認資料介面。例如同一個方向順序固定為 N,E,S,W。

## 6. 繳交前檢查

- `requirements.txt` 可以在另一台電腦安裝。
- 主視窗可正常開啟，角色、卡牌、地圖與 UI 都能操作。
- 各狀態可正常返回／重新開始，不會一旦失敗就卡死。
- 由組員展示一局完整通關與失敗案例，並說明主要程式模組。
- 第三方素材有來源及使用權限紀錄；AI 生成圖明確標成概念圖或示意圖。
