# 開發指南

## 環境設定

專案以 Python 3.14.7 和 pygame-ce 開發。需要 Git，以及該 repository 的讀取權限。

```sh
git clone https://github.com/Ethane0808/dungeon-architect.git
cd dungeon-architect
python --version
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

`requirements-dev.txt` 會一併安裝遊戲依賴。Windows 若有多個 Python 版本，可用 `py -3.14` 取代上面的 `python`。要試玩視窗，參考 [README](README.md#啟動遊戲)。

## 修改與審查

1. 從更新後的 `main` 開分支，一個分支處理一項工作。
2. 提交前跑測試。修正抽卡或放置問題時，在 PR 附上 seed 和操作順序，方便組員重現。
3. PR 說明改動與驗證結果，請組員審查後合併。玩法有變動時，同步更新[遊戲設計](GAME_DESIGN.md)、[設計決策](DECISIONS.md)與相關測試。
4. 提交程式、測試和共用設定。API 金鑰、本機設定及快取留在本機。

課程要求自行編寫的原始碼中，Python 占比須嚴格大於 50%。計算方式見[技術規格](TECH_SPEC.md#11-課程語言要求)。

## 交付檢查

請用另一台電腦確認依賴能安裝、視窗能啟動，並依[測試計畫](TEST_PLAN.md)試玩當前交付範圍。最終繳交時準備一局可重現的通關與失敗示範，並記錄第三方素材的來源和授權。
