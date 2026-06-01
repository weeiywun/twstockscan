# twstockscan

台股選股工具，以 GitHub Pages 作為前端，GitHub Actions 作為資料更新與掃描引擎。此 repo 目前只維護前端仍在使用的頁面、策略與 workflow。

## 前端頁面

主要入口在 `index.html`，分頁註冊在 `js/app.js`。

- `future_dashboard`：市場背景儀表板，讀取 `futures_dashboard.json`、`market_index.json`、`margin_balance.json`。
- `ssr`：標的池，讀取 `momentum_candidates.json`。
- `chips_big_holder`：籌碼集中，讀取 `chips_big_holder.json`。
- `big_holder_trend`：大戶趨勢池，讀取 `big_holder_trend.json`。
- `stock_analysis`：籌碼標的追蹤，讀取 `ai_analysis.json`。
- `right_top`：突破策略，讀取 `right_top.json`。
- `right_top_track`：突破標的追蹤，讀取 `right_top_track.json`。
- `performance`：績效追蹤，需要 URL 解鎖參數才顯示，讀取 `performance.json`。

`volume_signal` 與 `volume_pullback` 不直接出現在導覽列，但仍是標的池與追蹤流程的資料來源，因此保留。

## 目前資料檔

- `price_cache.parquet` / `stock_list_cache.json`：價量與股票清單快取。
- `current_prices.json`：前端現價快照。
- `market_index.json`、`futures_dashboard.json`、`margin_balance.json`：市場背景。
- `chips_big_holder.json`、`big_holder_trend.json`：大戶與籌碼池。
- `right_top.json`、`right_top_track.json`：突破策略與追蹤。
- `volume_signal.json`、`volume_pullback.json`：量增訊號與量增回測來源。
- `ai_analysis.json`：量增訊號標的追蹤與營收評級。
- `performance.json`：績效追蹤資料。

## 目前腳本

- `update_price_cache.py`：維護全市場價格快取。
- `update_market_index.py`：更新大盤指數快取。
- `update_futures_dashboard.py`：更新期貨籌碼、美股與市場情緒儀表板。
- `update_margin_balance.py`：更新融資餘額。
- `update_current_prices.py`：更新前端現價。
- `fetch_tdcc_holdings.py`、`fetch_holdings_twsthr.py`：抓取與分析 TDCC 大戶資料。
- `scan_big_holder_trend.py`、`update_big_holder_trend_prices.py`：大戶趨勢池與每日追蹤。
- `scan_right_top.py`、`track_right_top.py`：突破策略與追蹤。
- `scan_volume_signal.py`、`scan_volume_pullback.py`：量增訊號與量增回測模型。
- `scan_momentum_candidates.py`、`pattern_detect.py`、`apply_pattern_scores.py`：每日標的池與型態評分。
- `stock_analysis.py`：量增訊號標的追蹤與營收評級。
- `generate_line_performance_chart.py`、`send_daily_scan_summary.py`：LINE 推播素材與每日摘要。
- `update_institutional_tags.py`：手動補籌碼池法人標籤。

## GitHub Actions

- `daily_scan.yml`：每日主流程。由 Google Apps Script 以 `daily_scan_1700` 觸發，也可手動輸入 `RUN_DAILY_SCAN` 執行。
- `holdings_scan.yml`：週六大戶資料流程。由 Google Apps Script 以 `holdings_scan_weekly` 觸發，也可手動輸入 `RUN_HOLDINGS_SCAN` 執行。
- `stock_analysis.yml`：每日主流程成功後自動更新 `ai_analysis.json`。
- `update_current_prices.yml`：前端更新現價按鈕與平日市場快照更新。
- `institutional_tags.yml`：手動補法人標籤。

所有資料寫入 workflow 使用同一個 `data-writes-main` concurrency group，避免同時推送互相覆蓋。

## Google Apps Script

GAS 腳本位於 `gas/workflow-triggers.gs`：

- `installDailyScan1700Trigger()`：建立每日 17:00 觸發 `daily_scan_1700`。
- `installHoldingsScanWeeklyTrigger()`：建立週六觸發 `holdings_scan_weekly`。

## 新增策略

1. 在 `js/app.js` 的 `STRATEGIES` 加入分頁設定。
2. 新增對應 renderer，並在 `index.html` 載入。
3. 在 `DATA`、`loadData()`、`renderStrategy()` 補上資料載入與渲染。
4. 新增 Python 掃描腳本，並加入適合的 workflow。
5. 若策略會參與標的池，請以 `pattern_detect.py` 的型態分數作為唯一評分來源。
