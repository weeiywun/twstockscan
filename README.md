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
  render-analysis.js          ← 量增訊號標的追蹤渲染
  render-vcp.js               ← VCP / 潛在 VCP 渲染
  render-right-top.js         ← 突破策略渲染
  render-right-top-track.js   ← 突破策略標的追蹤渲染
  render-perf.js              ← 績效追蹤渲染
  render-breakout.js          ← （保留）爆量策略渲染
  render-ema.js               ← （保留）均線糾結策略渲染
data/
  price_cache.parquet         ← 全市場日線快取（FinMind，主要 API 請求入口）
  stock_list_cache.json       ← 上市上櫃股票清單快取
  chips_big_holder.json       ← 籌碼集中掃描結果
  volume_signal.json          ← 量增訊號掃描結果
  vcp.json                    ← VCP / 潛在 VCP 掃描結果
  right_top.json              ← 突破策略掃描結果
  right_top_track.json        ← 突破策略標的追蹤
  futures_dashboard.json      ← FUTURE DASHBOARD（期貨 + VIX + 情緒指標）
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
  update_current_prices.py    ← 前端觸發的現價更新
  scan_vcp.py                 ← VCP / 潛在 VCP 掃描
  scan_right_top.py           ← 突破策略掃描
  track_right_top.py          ← 突破策略標的追蹤更新
  scan_volume_signal.py       ← 量增訊號掃描（含 LINE 推播）
  stock_analysis.py           ← 量增訊號標的追蹤 + 營收評級
  fetch_tdcc_holdings.py      ← TDCC 股權分散資料下載
  fetch_holdings_twsthr.py    ← 集保大戶持股資料處理
  update_institutional_tags.py← 三大法人標籤更新
  call_ai_ranking.py          ← AI 選股排名（Gemini）
  send_daily_scan_summary.py  ← 每日掃描完成 LINE 推播摘要
  finmind_client.py           ← FinMind API 封裝
  requirements.txt            ← Python 相依套件
.github/workflows/
  daily_scan.yml              ← 每日主流程（17:00 由 GAS 觸發）
  holdings_scan.yml           ← 每週六籌碼集中掃描
  stock_analysis.yml          ← 每日主流程成功後自動接續
  institutional_tags.yml      ← 籌碼掃描完成後自動補法人標籤
  update_current_prices.yml   ← 前端「更新現價」按鈕觸發
  breakout_scan_manual.yml    ← 手動補跑突破策略
.github/workflows-disabled/   ← 停用或一次性 workflow（不出現於 Actions 介面）
```

---

## 策略說明

### FUTURE DASHBOARD
整合台股夜盤、美股收盤、三大法人期貨多空、散戶多空比、PC Ratio（5 日動態基準）、CNN 恐懼貪婪指數與 VIX，計算 Market Bias 分數（-100 ～ +100），反映當前市場動能狀態。各指標均以順勢方向計分，非逆向操作建議。

### 籌碼集中
每週末掃描全市場，追蹤千張大戶與 400 張大戶持股相對成長率（R），篩選低基期且量能充足的標的，標記「持續成長」「雙軌觸發」「單周增幅」三類標籤。

### SSR 交集雷達
彙整籌碼集中、VCP、突破策略三組核心選股，單獨列出同時符合 2 組以上策略的標的，支援 C3 取 2、三策略全中、大戶 + VCP、大戶 + 突破、VCP + 突破等視角。

### 量增訊號
每日盤後針對籌碼集中入池標的掃描量能突破訊號（當日量 ≥ 10 日均量 × 1.5，收盤 > EMA5），捕捉主力啟動時機，觸發時透過 LINE 推播。

### 突破策略
整合盤整突破（週線突破前 10 週高點）與動能突破（日線 Close > MA20 > MA60，突破前 60 日高），區分低波動打底後發動與強勢多頭續攻兩種型態。

### VCP
掃描 Mark Minervini VCP（Volatility Contraction Pattern）型態，分成「潛在 VCP」與「VCP」兩組。潛在 VCP 先找 Stage 2 上升趨勢、至少 2 段波動收縮、深度遞減與量能萎縮；VCP 進一步要求至少 3 段收縮、最後一段 ≤ 10%、接近 pivot，且近期量能收斂。

### 績效追蹤
記錄建倉與出場，計算損益、報酬率與整體投組績效。同一標的多批建倉時，前端自動以加權平均成本合併顯示。需 URL 參數 `?unlock=perf` 解鎖。

---

## 自動更新排程

| 時間 | 觸發方式 | Workflow | 內容 |
|------|----------|----------|------|
| 每個交易日 17:00 | Google Apps Script → repository_dispatch | `daily_scan.yml` | 價格快取、大盤指數、期貨儀錶板、VCP、突破策略、量增訊號 |
| daily_scan 成功後 | workflow_run | `stock_analysis.yml` | 量增訊號標的追蹤、營收評級、AI 排名 |
| 每週六 | cron | `holdings_scan.yml` | TDCC 股權分散、籌碼集中掃描 |
| holdings_scan 成功後 | workflow_run | `institutional_tags.yml` | 三大法人標籤 |
| 前端按鈕 | workflow_dispatch | `update_current_prices.yml` | 即時現價更新 |

失敗時透過 LINE Messaging API 推播通知。

---

## 手動觸發

- `daily_scan.yml`：需輸入 `RUN_DAILY_SCAN`；支援 `backfill_month`（格式 `2025-10`）回填歷史資料
- `holdings_scan.yml`：需輸入 `RUN_HOLDINGS_SCAN`

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
