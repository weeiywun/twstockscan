# TW Stock Scan

台股選股工具，以 GitHub Pages 為前端、GitHub Actions 為排程引擎，每日自動掃描選股策略並透過 LINE 推播結果。

---

## 系統架構

```
index.html                    ← 單頁應用程式入口
js/
  app.js                      ← 策略註冊、資料載入、導覽列、互動邏輯
  render-ssr.js               ← SSR 交集雷達渲染
  render-futures.js           ← FUTURE DASHBOARD 渲染
  render-chips.js             ← 籌碼集中渲染
  render-volume.js            ← 量增訊號渲染
  render-volume-pullback.js   ← 量增回測渲染
  render-momentum-pullback.js ← 動能回測渲染
  render-analysis.js          ← 量增訊號標的追蹤渲染
  render-vcp.js               ← VCP / 潛在 VCP 渲染
  render-right-top.js         ← 突破策略渲染
  render-right-top-track.js   ← 突破策略標的追蹤渲染
  render-trust.js             ← 法人動能渲染（投信 / 外資 / 雙法人共振）
  render-perf.js              ← 績效追蹤渲染
  render-breakout.js          ← （保留）爆量策略渲染
  render-ema.js               ← （保留）均線糾結策略渲染
data/
  price_cache.parquet         ← 全市場日線快取（FinMind，主要 API 請求入口）
  stock_list_cache.json       ← 上市上櫃股票清單快取
  chips_big_holder.json       ← 籌碼集中掃描結果
  volume_signal.json          ← 量增訊號掃描結果
  volume_pullback.json        ← 量增回測候選池
  momentum_pullback.json      ← 動能回測候選池
  intraday_volume_pullback.json ← 10:00 盤中量增回測預警（停用備用）
  vcp.json                    ← VCP / 潛在 VCP 掃描結果
  right_top.json              ← 突破策略掃描結果
  right_top_track.json        ← 突破策略標的追蹤
  trust_momentum.json         ← 法人動能掃描結果（TWSE/TPEx 官方法人買賣超 + price_cache）
  futures_dashboard.json      ← FUTURE DASHBOARD（期貨 + VIX + 情緒指標）
  margin_balance.json         ← 融資餘額金額（TWSE/TPEx 官方資料，前端以億元顯示）
  market_index.json           ← 大盤指數（加權、櫃買、期貨夜盤）
  performance.json            ← 績效追蹤（建倉 / 出場紀錄）
  ai_recommendations.json     ← AI 選股推薦
  ai_analysis.json            ← 量增訊號標的 AI 分析
  current_prices.json         ← 前端手動更新的即時現價
  volume_breakout.json        ← （停用）爆量策略歷史資料
  ema_tangling.json           ← （停用）均線糾結策略歷史資料
scripts/
  update_price_cache.py       ← 維護全市場價格快取（支援 --backfill 回填）
  update_market_index.py      ← 更新大盤指數快取
  update_futures_dashboard.py ← 更新期貨籌碼 + VIX + CNN 情緒指標
  update_margin_balance.py    ← 更新上市 / 上櫃融資餘額快取（官方資料）
  update_current_prices.py    ← 前端觸發的現價更新
  scan_vcp.py                 ← VCP / 潛在 VCP 掃描
  scan_right_top.py           ← 突破策略掃描
  track_right_top.py          ← 突破策略標的追蹤更新
  scan_trust_momentum.py      ← 法人動能掃描（投信 / 外資，不逐檔查 FinMind）
  scan_volume_signal.py       ← 量增訊號掃描（含 LINE 推播）
  scan_volume_pullback.py     ← 量增回測模型
  scan_momentum_pullback.py   ← 動能回測模型
  scan_intraday_volume_pullback.py ← 10:00 盤中量增回測預警（停用備用）
  realtime_quote.py           ← TWSE MIS 即時行情小批量查詢（停用備用）
  stock_analysis.py           ← 量增訊號標的追蹤 + 營收評級
  fetch_tdcc_holdings.py      ← TDCC 股權分散資料下載
  fetch_holdings_twsthr.py    ← 集保大戶持股資料處理
  update_institutional_tags.py← 三大法人標籤更新
  call_ai_ranking.py          ← AI 選股排名（Gemini）
  generate_line_performance_chart.py ← 產生 LINE 卡片用績效折線圖（覆蓋 latest）
  send_daily_scan_summary.py  ← 每日掃描完成 LINE 推播摘要（績效圖 + 持倉 + 精選觀察）
  finmind_client.py           ← FinMind API 封裝
  requirements.txt            ← Python 相依套件
.github/workflows/
  daily_scan.yml              ← 每日主流程（17:00 由 GAS 觸發）
  intraday_volume_pullback.yml ← 10:00 盤中量增回測預警（停用備用）
  holdings_scan.yml           ← 每週六籌碼集中掃描
  stock_analysis.yml          ← 每日主流程成功後自動接續
  institutional_tags.yml      ← 手動補法人標籤
  update_current_prices.yml   ← 前端「更新現價」按鈕觸發
  breakout_scan_manual.yml    ← 手動補跑突破策略
.github/workflows-disabled/   ← 停用或一次性 workflow（不出現於 Actions 介面）
```

---

## 策略說明

### FUTURE DASHBOARD
Future Dashboard 改為市場背景儀表板：上層分成台股盤面與美股盤面，台股側整合加權 / 櫃買 / 台指期、散戶多空比、PC Ratio 與今日解讀；美股側保留 CNN Fear & Greed 與主要美股指數。下層呈現三大法人現貨買賣超、融資餘額折線圖，以及台指期法人多空（日 / 夜合併）。此頁僅做環境與槓桿溫度判斷，不直接產生個股買賣訊號。

### 籌碼集中
每週末掃描全市場，追蹤千張大戶與 400 張大戶持股相對成長率（R），篩選低基期且量能充足的標的，標記「持續成長」「雙軌觸發」「單周增幅」三類標籤。

### SSR 交集雷達
彙整籌碼集中、VCP、突破策略、投信動能、外資動能五組核心選股，單獨列出同時符合 2 組以上策略的標的，支援 C5 取 2、三組以上、投信 + 外資、大戶 + VCP、投信 + VCP、外資 + 突破等視角。

前台預設新增「精選觀察」視角，從 `momentum_candidates.json` 的 A 級候選再收斂，要求命中量增回測或再啟動，並具備大戶或價格突破追蹤脈絡；同時用量比、週漲幅、BBW 與追蹤漲幅過濾過熱標的。這一層用於每日決策與 LINE Top 5 推播，原始策略清單仍保留供回查。

### 量增訊號
每日盤後針對籌碼集中入池標的掃描量能突破訊號（當日量 ≥ 10 日均量 × 1.5，收盤 > EMA5），捕捉主力啟動時機，觸發時透過 LINE 推播。

### 量增回測
從籌碼集中、價格突破追蹤與既有量增訊號合併候選池，尋找「放量突破 → 回測支撐 → 再啟動」結構。盤後模型保留為主要使用流程；10:00 盤中預警功能目前停用備用，避免盤中監看分散注意力。

### 動能回測
尋找已經被市場資金推升、近期出現 60 日高點後回測到 Fib 23.6%~61.8% 的強勢股候選。模型要求 Close > EMA60、EMA20 > EMA60 > EMA120，並標註回測區、均線共振、回測量能、轉強訊號與防守價，方便人工進一步看圖複查；排序偏向風險距離小、回前高空間足、且有既有策略標籤共振的標的。

### 突破策略
整合盤整突破（週線突破前 10 週高點）、動能突破（日線 Close > MA20 > MA60，突破前 60 日高）與價格突破（Close > EMA20 ≥ EMA60 ≥ EMA120，創前 60 日高且量能續航），區分低波動打底後發動、日線啟動與強勢股續創新高。

### VCP
掃描 Mark Minervini VCP（Volatility Contraction Pattern）型態，分成「潛在 VCP」與「VCP」兩組。潛在 VCP 先找 Stage 2 上升趨勢、至少 2 段波動收縮、深度遞減與量能萎縮；VCP 進一步要求至少 3 段收縮、最後一段 ≤ 10%、接近 pivot，且近期量能收斂。

### 法人動能
追蹤投信與外資近 5～10 日買超動能，篩選買超占成交量有感、股價站上 EMA120 的標的，並區分「攻擊」「承接」「雙法人共振」。此策略獨立於大戶持股池，適合觀察主動式 ETF、投信與外資資金流入造成的短中期動能。

### 績效追蹤
記錄建倉與出場，計算損益、報酬率與整體投組績效。同一標的多批建倉時，前端自動以加權平均成本合併顯示。需 URL 參數 `?unlock=perf` 解鎖。

每日與週六 workflow 會覆蓋產生 `assets/line/performance-latest.png`，作為 LINE Flex Message 上方績效圖。圖片只保留最新版本，LINE 推播以 GitHub Pages 公開網址加日期參數引用，避免快取顯示舊圖。

---

## 自動更新排程

| 時間 | 觸發方式 | Workflow | 內容 |
|------|----------|----------|------|
| 每個交易日 17:00 | Google Apps Script → repository_dispatch | `daily_scan.yml` | 價格快取、大盤指數、期貨儀錶板、VCP、突破策略、法人動能、量增訊號、量增回測、動能回測 |
| daily_scan 成功後 | workflow_run | `stock_analysis.yml` | 量增訊號標的追蹤、營收評級、AI 排名 |
| 每週六或手動 | Google Apps Script → repository_dispatch / workflow_dispatch | `holdings_scan.yml` | TDCC 股權分散、籌碼集中掃描 |
| 手動執行 | workflow_dispatch | `institutional_tags.yml` | 三大法人標籤 |
| 前端按鈕 | workflow_dispatch | `update_current_prices.yml` | 即時現價更新 |

失敗時透過 LINE Messaging API 推播通知。

### Trigger 設計

每日主流程不使用 GitHub Actions 內建 `schedule`，避免排程延遲或漏跑；改由 Google Apps Script 在台灣時間 17:00 呼叫 GitHub `repository_dispatch`，事件型別為 `daily_scan_1700`。17:00 通常已可取得 TWSE/TPEx 盤後法人彙總資料，因此法人動能會在同一條每日掃描流程內更新。

10:00 盤中量增回測預警目前停用備用。程式碼與 workflow 保留，GAS 端請不要啟用 `triggerIntradayVolumePullback1000` 觸發器；若未來要恢復，可重新啟用 GAS trigger 並在前端打開 SSR 的盤中面板。

GAS 腳本位於 `gas/workflow-triggers.gs`。首次部署或重建觸發器時，於 Apps Script 執行：

- `installDailyScan1700Trigger()`：建立每日 17:00 觸發 `daily_scan_1700`
- `installIntradayVolumePullback1000Trigger()`：建立每日 10:00 觸發 `intraday_volume_pullback_1000`（停用備用）
- `installHoldingsScanWeeklyTrigger()`：建立每週六觸發 `holdings_scan_weekly`

---

## 手動觸發

- `daily_scan.yml`：需輸入 `RUN_DAILY_SCAN`；支援 `backfill_month`（格式 `2025-10`）回填歷史資料
- `intraday_volume_pullback.yml`：手動補跑 10:00 盤中量增回測預警（停用備用）
- `holdings_scan.yml`：需輸入 `RUN_HOLDINGS_SCAN`
- `institutional_tags.yml`：手動補上目前 `chips_big_holder.json` 標的的外資 / 投信連買標籤

---

## 所需 Secrets

| Secret | 用途 |
|--------|------|
| `FINMIND_API_TOKEN` | FinMind 股價、籌碼資料 |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE 推播 |
| `LINE_USER_IDS` | LINE 推播目標（逗號分隔） |

---

## 新增選股策略

1. 在 `js/app.js` 的 `STRATEGIES` 陣列加入策略物件（`id`、`name`、`group`、`dataKey` 等）
2. 新增對應 `render-xxx.js` 渲染函式，並在 `index.html` 引入
3. 在 `DATA` 物件加入對應 `dataKey`，在 `loadData()` 新增 fetch，在 `renderStrategy()` 新增 dispatch
4. 新增 Python 掃描腳本至 `scripts/`，加入 `daily_scan.yml` 或另建 workflow

---

## 部署

1. Fork 此 repo
2. Settings → Pages → Source：`main` branch / root
3. Settings → Secrets → 新增上述三組 Secrets
4. 完成，GitHub Pages 自動部署
