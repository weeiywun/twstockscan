# SR

## 架構說明

```
index.html          ← 主應用程式（單一檔案，可獨立運作）
data/
  chips_big_holder.json   ← 千張大戶策略結果
  volume_breakout.json    ← 停用策略的歷史結果
  ema_tangling.json       ← 停用策略的歷史結果
  history/                ← 歷史紀錄（每日保存）
scripts/
  update_price_cache.py   ← 維護全市場價格快取（主要 FinMind 請求入口）
  scan_right_top.py       ← 從 price_cache 掃描右上角策略（不直接打 API）
  scan_volume_signal.py   ← 從 price_cache 掃描量增訊號並更新追蹤價格
  fetch_tdcc_holdings.py  ← 從 TDCC 更新股權分散 CSV
.github/workflows/
  daily_scan.yml              ← 每日主流程：價格快取、右上角、追蹤、量增訊號
  holdings_scan.yml           ← 每週主流程：TDCC 大戶持股與籌碼集中
  stock_analysis.yml          ← 每日主流程成功後自動維護量增訊號標的營收與觀察期
  institutional_tags.yml      ← 大戶持股分析成功後自動補法人標籤
  update_current_prices.yml   ← 前端按鈕觸發的現價更新

停用或一次性 workflow 放在 `.github/workflows-disabled/`，避免在 GitHub Actions 介面誤觸。
```

## 選股策略

### PHASE1 — 千張大戶籌碼
追蹤全市場個股的千張大戶持股比例，篩選大戶連續增持、散戶持續出場的標的。

### 右上角 / 量增訊號
每日主流程更新 `price_cache.parquet` 後，所有日線、週線與現價計算優先從快取讀取，避免重複打 FinMind。

### 停用策略
爆量追蹤與均線糾結策略仍保留腳本與歷史資料，但 workflow 已移至 `.github/workflows-disabled/`，避免誤觸全市場逐股請求。

## 手動觸發掃描

- `daily_scan.yml`：手動執行需輸入 `RUN_DAILY_SCAN`。
- `holdings_scan.yml`：手動執行需輸入 `RUN_HOLDINGS_SCAN`。
- `update_current_prices.yml`：由前端「更新現價」按鈕觸發。
- 其他補跑或停用策略 workflow 不放在 `.github/workflows/`。

## 自動更新

- 每個交易日盤後執行 `daily_scan.yml`，更新 `price_cache.parquet` 與每日策略資料。
- 每週六執行 `holdings_scan.yml`，更新 TDCC 股權分散資料與籌碼集中結果。
- 接續 workflow 只由主流程成功後觸發，不提供手動入口，降低 FinMind 請求誤用風險。
- 失敗時透過 LINE Messaging API 推播通知。

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
