# 策略精選檢討報告 2026-05-26

資料基準：`data/right_top_track.json`，最後更新 `2026-05-25`。

分析目的：從已追蹤標的中，對比價差 `>= 10%` 與 `<= 0%`，找出可以縮小每日候選名單的規則。完整強勢與弱勢清單已輸出到 `docs/strategy-refinement-analysis-2026-05-26.csv`。

## 資料限制

`right_top_track.json` 保存了追蹤起始價、現價、價差與追蹤量比，但沒有保存每一檔「入選當下」的完整大戶標籤、週漲幅、乖離與 BBW。

本報告的策略來源與細部欄位，是用目前仍存在的 `momentum_candidates`、`chips_big_holder`、`volume_pullback`、`right_top`、`volume_signal`、`momentum_pullback` 回補，因此適合作為規則優化方向，不應視為嚴格歷史回測。

## 總覽

| 分組 | 筆數 | 平均價差 | 中位價差 | 平均追蹤量比 | 中位追蹤量比 | 平均來源數 | 仍命中量增回測 | 仍在精選候選 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 強勢 >=10% | 61 | +21.20% | +16.12% | 1.92 | 1.70 | 1.92 | 29 檔, 47.5% | 10 檔, 16.4% |
| 中段 0~10% | 97 | +4.85% | +4.10% | 2.03 | 1.75 | 2.27 | 39 檔, 40.2% | 40 檔, 41.2% |
| 弱勢 <=0% | 99 | -2.16% | -0.93% | 1.62 | 1.51 | 2.14 | 31 檔, 31.3% | 34 檔, 34.3% |

## 強勢標的 Top 20

| 標的 | 價差 | 入選價 | 現價 | 追蹤量比 | 回補來源 |
|---|---:|---:|---:|---:|---|
| 3048 益登 | +72.88% | 42.40 | 73.30 | 1.77 | price_breakout_track |
| 6538 倉和 | +58.62% | 82.90 | 131.50 | 1.86 | price_breakout_track |
| 2302 麗正 | +53.35% | 20.15 | 30.90 | 1.64 | price_breakout_track |
| 3537 堡達 | +48.93% | 51.50 | 76.70 | 2.45 | price_breakout_track / volume_pullback |
| 5321 美而快 | +45.90% | 29.30 | 42.75 | 2.04 | price_breakout_track / volume_pullback |
| 3236 千如 | +44.67% | 40.30 | 58.30 | 0.40 | price_breakout_track |
| 6570 維田 | +40.90% | 42.30 | 59.60 | 1.50 | price_breakout_track |
| 6719 力智 | +35.64% | 188.00 | 255.00 | 1.96 | price_breakout_track / right_top / right_top_track / volume_pullback |
| 6742 澤米 | +35.23% | 44.00 | 59.50 | 3.71 | price_breakout_track |
| 6161 捷波 | +33.41% | 44.30 | 59.10 | 2.12 | price_breakout_track |
| 2441 超豐 | +32.07% | 97.30 | 128.50 | 0.81 | price_breakout_track |
| 6227 茂綸 | +29.70% | 101.00 | 131.00 | 1.45 | price_breakout_track / right_top |
| 8926 台汽電 | +27.29% | 49.10 | 62.50 | 3.11 | price_breakout_track / right_top |
| 6116 彩晶 | +25.00% | 10.40 | 13.00 | 5.51 | price_breakout_track |
| 2478 大毅 | +24.61% | 96.30 | 120.00 | 2.03 | price_breakout_track / volume_pullback |
| 8050 廣積 | +23.06% | 44.45 | 54.70 | 1.54 | price_breakout_track |
| 2491 吉祥全 | +22.92% | 19.20 | 23.60 | 1.75 | price_breakout_track / right_top |
| 9105 泰金寶-DR | +20.85% | 6.14 | 7.42 | 1.00 | price_breakout_track / volume_pullback |
| 6284 佳邦 | +20.45% | 93.40 | 112.50 | 2.01 | price_breakout_track / volume_pullback |
| 6237 驊訊 | +20.00% | 45.50 | 54.60 | 3.32 | price_breakout_track / volume_pullback |

## 弱勢標的 Bottom 20

| 標的 | 價差 | 入選價 | 現價 | 追蹤量比 | 回補來源 |
|---|---:|---:|---:|---:|---|
| 8488 吉源-KY | -10.51% | 10.85 | 9.71 | 1.51 | price_breakout_track |
| 3024 憶聲 | -9.83% | 17.80 | 16.05 | 2.46 | momentum_pullback / price_breakout_track |
| 1598 岱宇 | -9.23% | 22.20 | 20.15 | 1.96 | price_breakout_track |
| 6629 泰金-KY | -8.85% | 130.00 | 118.50 | 1.92 | price_breakout_track |
| 3033 威健 | -8.72% | 53.90 | 49.20 | 4.70 | price_breakout_track |
| 4440 宜新實業 | -7.55% | 19.20 | 17.75 | 1.93 | price_breakout_track |
| 6703 軒郁 | -7.53% | 119.50 | 110.50 | 0.38 | price_breakout_track |
| 5210 寶碩 | -6.99% | 28.60 | 26.60 | 3.73 | price_breakout_track |
| 3717 聯嘉投控 | -6.90% | 24.65 | 22.95 | 2.55 | price_breakout_track |
| 2108 南帝 | -6.48% | 29.30 | 27.40 | 0.53 | momentum_pullback / price_breakout_track |
| 2107 厚生 | -6.04% | 26.50 | 24.90 | 1.03 | price_breakout_track |
| 1714 和桐 | -5.85% | 10.25 | 9.65 | 0.87 | price_breakout_track |
| 8213 志超 | -5.38% | 41.80 | 39.55 | 1.73 | price_breakout_track |
| 6150 撼訊 | -5.23% | 72.60 | 68.80 | 1.55 | price_breakout_track |
| 1904 正隆 | -5.16% | 20.35 | 19.30 | 3.24 | price_breakout_track |
| 2354 鴻準 | -4.98% | 64.30 | 61.10 | 3.83 | price_breakout_track |
| 6203 海韻電 | -4.72% | 76.20 | 72.60 | 2.36 | price_breakout_track |
| 2392 正崴 | -4.69% | 40.50 | 38.60 | 1.74 | price_breakout_track |
| 1460 宏遠 | -4.67% | 7.28 | 6.94 | 1.08 | chips / price_breakout_track |
| 2412 中華電 | -4.21% | 142.50 | 136.50 | 1.29 | chips / price_breakout_track / right_top_track |

## 初步共同點

強勢組：

- 價格突破仍是有效入口，尤其是 60 日新高後快速延伸的標的。
- 後續若又進入 `volume_pullback`，代表它不是只漲一天，而是有「點火 -> 回測/再啟動」結構。
- 量比多集中在 `1.5x ~ 4x`，超高量能不是必要條件，但完全無量延伸的勝率也較不穩。
- 強勢股很多並不在當週大戶池，表示大戶策略不能當唯一精選入口。

弱勢組：

- 單純價格突破但沒有後續再啟動結構，容易變成假突破或短線熄火。
- 已經出現明顯負週漲幅、低動能或防守失守者，應該從前台精選中快速降級。
- `C` 級、突破延伸但沒有量增回測者，適合留在全部候選，不適合每天推播。
- 大戶標籤本身不是保證，穩定大戶股若缺少價格動能，容易佔用觀察名額。

## 精選候選規則草案

我建議先建立一個「精選觀察」視角，不刪既有策略，只改預設顯示與 LINE 推播排序。

納入條件：

1. `priority_level = A`
2. 來源含 `volume_pullback`，或 `pullback_status = reentry`
3. 來源含 `right_top_track` 或 `chips`
4. 量能不失控：`1.2 <= 量比 <= 5.0`，缺資料不硬排除
5. 避免過熱：`week_chg_pct <= 18`，缺資料不硬排除
6. 盤整品質：`BBW <= 14`，缺資料不硬排除
7. 追蹤已漲幅：`track_pnl_pct <= 14`，避免已經噴太遠才進精選

排除或降級條件：

- `priority_level = C`
- 僅有價格突破追蹤，且沒有量增回測/再啟動
- `track_pnl_pct > 14`，改列強勢延伸，不列每日精選
- `week_chg_pct > 18`，除非同時出現回測量縮與再啟動
- 週漲跌轉負且沒有重新站回 EMA5 / EMA20

## 套用草案後的目前候選 Top 20

目前 `momentum_candidates` 會從 91 檔收斂到 44 檔。

| 標的 | 狀態 | 分數 | 量比 | 週漲跌 | BBW | 追蹤價差 | 來源 |
|---|---|---:|---:|---:|---:|---:|---|
| 2421 建準 | 再啟動 | 124 | 2.40 | 15.66 | 11.73 | 2.52 | chips / right_top_track / volume_pullback / volume_signal |
| 2362 藍天 | 點火首日 | 119 | 4.97 | 8.46 | 6.58 | 3.55 | chips / right_top_track / stock_analysis / volume_pullback / volume_signal |
| 2332 友訊 | 再啟動 | 113 | 2.02 | 12.14 | 11.10 | — | chips / volume_pullback / volume_signal |
| 3372 典範 | 點火首日 | 92 | 3.36 | 12.28 | 13.92 | — | chips / volume_pullback / volume_signal |
| 2352 佳世達 | 再啟動 | 92 | 4.11 | — | — | 5.33 | right_top_track / stock_analysis / volume_pullback |
| 6214 精誠 | 再啟動 | 89 | 2.78 | 4.45 | 8.96 | -0.77 | chips / right_top_track / volume_pullback |
| 8081 致新 | 再啟動 | 87 | 3.65 | — | — | 9.09 | right_top_track / volume_pullback |
| 6209 今國光 | 再啟動 | 87 | 3.39 | — | — | 9.25 | right_top_track / volume_pullback |
| 6151 晉倫 | 再啟動 | 87 | 4.58 | — | — | 12.70 | right_top_track / volume_pullback |
| 4908 前鼎 | 再啟動 | 87 | 3.66 | — | — | 9.93 | right_top_track / volume_pullback |
| 2420 新巨 | 再啟動 | 87 | 4.23 | — | — | 8.74 | right_top_track / volume_pullback |
| 3708 上緯投控 | 再啟動 | 85 | 4.00 | 7.30 | 12.56 | — | chips / stock_analysis / volume_pullback |
| 6491 晶碩 | 回穩觀察 | 81 | 4.57 | 4.95 | 13.12 | 0.65 | chips / right_top_track / volume_pullback |
| 8255 朋程 | 再啟動 | 80 | 2.71 | — | — | 10.39 | right_top_track / volume_pullback |
| 8043 蜜望實 | 再啟動 | 80 | 2.72 | — | — | 12.78 | right_top_track / volume_pullback |
| 6558 興能高 | 再啟動 | 80 | 2.58 | — | — | 6.06 | right_top_track / volume_pullback |
| 6432 今展科 | 再啟動 | 80 | 2.55 | — | — | 8.35 | right_top_track / volume_pullback |
| 6174 安碁 | 再啟動 | 80 | 2.99 | — | — | 1.60 | right_top_track / volume_pullback |
| 5425 台半 | 再啟動 | 80 | 2.85 | — | — | 7.01 | right_top_track / volume_pullback |
| 5236 凌陽創新 | 再啟動 | 80 | 2.92 | — | — | 3.04 | right_top_track / volume_pullback |

## 建議下一步

1. 前端新增 `精選觀察` toggle，預設只顯示上述規則命中的標的。
2. LINE 每日卡片只送精選 Top 3~5。
3. `right_top_track` 後續新增入選當下快照欄位：`source_tags`、`week_chg_pct`、`deviation`、`bbw`、`volume_pullback_status`，之後才能做真正嚴格的回測。
4. 觀察 1~2 週後，再調整 `week_chg_pct <= 18`、`BBW <= 14`、`track_pnl_pct <= 14` 這三個門檻。
