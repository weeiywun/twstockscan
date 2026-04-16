# SR

## 架構說明

```
index.html          ← 主應用程式（單一檔案，可獨立運作）
data/
  chips_big_holder.json   ← 千張大戶策略結果
  volume_breakout.json    ← 爆量追蹤策略結果
  ema_tangling.json       ← 均線糾結策略結果（PHASE3）
  history/                ← 歷史紀錄（每日保存）
scripts/
  scan_volume_breakout.py ← 爆量追蹤選股腳本
  scan_ema_tangling.py    ← 均線糾結選股腳本（PHASE3）
  requirements.txt        ← Python 依賴套件
.github/workflows/
  volume_breakout_scan.yml    ← 爆量追蹤自動執行（台灣時間 15:30）
  ema_tangling_scan.yml       ← 均線糾結自動執行（台灣時間 15:40）
```

## 選股策略

### PHASE1 — 千張大戶籌碼
追蹤全市場個股的千張大戶持股比例，篩選大戶連續增持、散戶持續出場的標的。

### PHASE2 — 爆量追蹤
找出近期異常爆量突破、進入縮量洗盤的個股，捕捉主力蓄勢後二次啟動的進場機會。
- **自動執行時間**：台灣時間 15:30（每個交易日）

### PHASE3 — 均線糾結
篩選 EMA20/60/120 三條均線互相糾結（乖離 ≤ 5%）且股價站上所有均線的標的，捕捉蓄勢待發的突破機會。
- **自動執行時間**：台灣時間 15:40（每個交易日）
- **篩選條件**：
  - EMA20、EMA60、EMA120 三線最大最小差距 / 最小值 ≤ 5%
  - 收盤價站上 EMA20、EMA60、EMA120
  - 20 日均量 ≥ 500 張

## 手動觸發掃描

1. 前往 GitHub repo 的 **Actions** 頁面
2. 選擇對應 workflow（例如 **PHASE3 均線糾結選股**）
3. 點擊 **Run workflow** 手動觸發

## 自動更新

- 每個交易日盤後自動執行，更新 `data/` 資料夾中的 JSON 檔
- 休市日（國定假日）自動跳過（需每年更新 `TW_MARKET_HOLIDAYS`）
- 執行成功/失敗均可透過 LINE Messaging API 推播通知

## 新增選股策略步驟

1. 在 `index.html` 的 `STRATEGIES` 陣列加入新策略物件
2. 將結果 JSON 放到 `data/` 資料夾
3. 在 `DATA` 物件中加入對應的 `dataKey`
4. 新增對應的 Python 掃描腳本至 `scripts/`
5. 新增 GitHub Actions workflow 至 `.github/workflows/`

## 部署

1. Fork 此 repo
2. Settings → Pages → Source: main branch / root
3. Settings → Secrets → 新增 `LINE_CHANNEL_ACCESS_TOKEN` 與 `LINE_USER_ID`
4. 完成
