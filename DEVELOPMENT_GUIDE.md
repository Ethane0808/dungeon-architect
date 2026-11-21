python main.py --seed 42# 開發指南

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

### Windows 測試暫存目錄權限

若 pytest 在 `tmp_path` 建立前出現 WinError 5，或 `.pytest_cache` 寫入出現 WinError 183，先檢查目錄擁有者與 ACL。沙盒代理可能以不同 Windows 帳號執行，卻與桌面帳號共用 TEMP；它建立的私有目錄可能讓桌面帳號無法存取。這是測試環境權限問題，不能只靠遊戲測試在沙盒通過就判定已解決。

僅針對受影響的 pytest 生成目錄恢復父層繼承權限，應由目錄擁有者或經授權的管理員執行；不要更改整個 TEMP、原始碼或虛擬環境的權限，也不要停用警告。之後由桌面帳號執行原本的測試指令，確認沒有錯誤或警告。

沙盒代理後續驗證須為每次執行產生獨立的暫存與 cache 路徑，指令見 [AGENTS.md](AGENTS.md)，避免再次建立桌面帳號無法使用的預設目錄。

## 修改與審查

1. 從更新後的 `main` 開分支，一個分支處理一項工作。
2. 提交前跑測試。修正抽卡或放置問題時，在 PR 附上 seed 和操作順序，方便組員重現。
3. PR 說明改動與驗證結果，請組員審查後合併。玩法有變動時，同步更新[遊戲設計](GAME_DESIGN.md)與相關測試。
4. 提交程式、測試和共用設定。API 金鑰、本機設定及快取留在本機。

課程要求自行編寫的原始碼中，Python 占比須嚴格大於 50%。計算方式見[技術規格](TECH_SPEC.md#11-課程語言要求)。

## 交付檢查

提交前執行完整 pytest，並用 `python -m engine.demo` 驗證 seed 159 的通關重播。桌面驗收至少確認：

- 視窗及全螢幕模式都能啟動，地圖、房卡、資源、目標狀態與 Help 面板清楚且沒有遮擋。
- 選牌、旋轉、建造、移動、Seal、Chisel、祭壇啟動、核心解鎖與重開皆可操作。
- HP 歸零會失敗；進入解鎖核心會勝利；終局不再接受遊戲操作。
- 以另一台電腦確認依賴可安裝，並測試常用顯示縮放比例。

最終繳交時準備一局可重現的通關與失敗示範，並記錄第三方素材的來源和授權。
