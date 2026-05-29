# twstockscan

台股選股工具，以 GitHub Pages 作為前端，GitHub Actions 作為資料更新與掃描流程。

## 前端頁面

主要入口在 `index.html`，分頁設定在 `js/app.js`。

- `future_dashboard`：市場背景儀表板，讀取 `futures_dashboard.json`、`market_index.json`、`margin_balance.json`。
- `ssr`：每日標的池，讀取 `momentum_candidates.json`。
- `chips_big_holder`：籌碼集中，讀取 `chips_big_holder.json`。
- `big_holder_trend`：大戶趨勢池，讀取 `big_holder_trend.json`。
- `momentum_pullback`：動能回測，讀取 `momentum_pullback.json`。
- `stock_analysis`：籌碼標的追蹤，讀取 `ai_analysis.json`。
- `trend_follow`：策略二趨勢標的追蹤，讀取 `trend_follow.json`。
- `right_top`：突破策略，讀取 `right_top.json`。
- `right_top_track`：突破標的追蹤，讀取 `right_top_track.json`。
- `performance`：績效追蹤，需 URL 解鎖參數才顯示，讀取 `performance.json`。

`volume_signal` 不直接出現在導覽列，但會作為每日標的池的量增提醒來源。`volume_pullback` 保留給其他追蹤頁與資料流程，但不再替每日標的池加分。

## 每日標的池

`scan_momentum_candidates.py` 目前只做三件事：

1. 從 `chips_big_holder.json` 取得大戶持股增加的股票。
2. 分成 `低基期` 與 `趨勢`：
   - 低基期：EMA120 乖離介於 `0%` 到 `10%`。
   - 趨勢：`EMA5 > EMA20 > EMA60`。
3. 用 `pattern_detect.py` 的型態狀態與型態分數排序。

每日標的池不再使用舊的綜合加分：

- 不使用 `context_score`。
- 不使用 `unified_score`。
- 不使用多來源共振加分。
- 不使用熱門產業加分。
- 不使用 `right_top_track`、`ai_analysis`、`volume_pullback` 對標的池加分。

`focus_results` 只放 `pattern_state == "值得看圖"` 的股票。

型態分數在股票第一次進入每日標的池時鎖定，後續同一檔股票再次被選到仍沿用第一次的型態快照。此設計用來回推「當下型態分數」和後續績效之間的關係。

## 策略二追蹤

`track_trend_candidates.py` 會從每日標的池中的 `trend_results` 建立追蹤名單。

觸發條件：

- `pool_type == "trend"`
- `volume_alert == true`

追蹤規則與策略一追蹤頁一致：

- active 留存 10 個交易日。
- expired 未釘選保留 5 個交易日。
- 釘選後持續保留。
- 追蹤頁使用第一次入池時鎖定的型態分數，不重算舊分數。

## 目前資料檔

- `price_cache.parquet` / `stock_list_cache.json`：全市場價量與股票清單快取。
- `current_prices.json`：前端現價快照。
- `market_index.json`、`futures_dashboard.json`、`margin_balance.json`：市場背景。
- `chips_big_holder.json`、`big_holder_trend.json`：大戶與籌碼池。
- `volume_signal.json`：量增提醒。
- `momentum_candidates.json`：每日型態標的池。
- `trend_follow.json`：策略二趨勢標的追蹤。
- `momentum_pullback.json`：動能回測。
- `right_top.json`、`right_top_track.json`：突破策略與追蹤。
- `ai_analysis.json`：籌碼標的追蹤與營收評級。
- `performance.json`：績效追蹤資料。

## 目前腳本

- `update_price_cache.py`：維護全市場價格快取。
- `fetch_tdcc_holdings.py`、`fetch_holdings_twsthr.py`：抓取與分析 TDCC 大戶資料。
- `scan_volume_signal.py`：量增提醒。
- `scan_momentum_candidates.py`、`pattern_detect.py`：每日標的池與型態分數。
- `track_trend_candidates.py`：策略二趨勢標的追蹤。
- `scan_big_holder_trend.py`、`update_big_holder_trend_prices.py`：大戶趨勢池與追蹤。
- `scan_momentum_pullback.py`：動能回測模型。
- `scan_right_top.py`、`track_right_top.py`：突破策略與追蹤。
- `stock_analysis.py`：籌碼標的追蹤與營收評級。
- `enrich_candidate_features.py`、`unified_scoring.py`、`apply_unified_scores.py`：其他頁面使用的共用特徵與統一評分；每日標的池不再套用此分數。
- `send_daily_scan_summary.py`：LINE 每日摘要。

## GitHub Actions

- `daily_scan.yml`：每日主流程。
- `holdings_scan.yml`：週六大戶資料流程。
- `stock_analysis.yml`：每日主流程成功後自動更新 `ai_analysis.json`。
- `update_current_prices.yml`：前端現價快照更新。
- `institutional_tags.yml`：手動補籌碼池法人標籤。

所有資料寫入 workflow 使用同一個 `data-writes-main` concurrency group，避免同時推送互相覆蓋。
