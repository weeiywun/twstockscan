#!/usr/bin/env python3
"""
均線糾結選股策略 (EMA Tangling Scanner)
盤後自動執行，篩選符合「EMA20/60/120 均線糾結且股價站上所有均線」型態的台股。

策略條件：
  條件一：EMA20、EMA60、EMA120 三條均線最大值與最小值的差距 / 最小值 ≤ 5%
  條件二：收盤價 > EMA20、EMA60、EMA120（股價站上所有均線）
  條件三：20 日均量 ≥ 500 張

執行方式：
  python scan_ema_tangling.py          # 全市場掃描
  python scan_ema_tangling.py --quick  # 快速測試（前200支）
"""

import json
import time
import warnings
import sys
import os
from datetime import datetime, timedelta

import requests
import yfinance as yf
import pandas as pd
import numpy as np

warnings.filterwarnings("ignore")

TODAY = datetime.now().strftime("%Y-%m-%d")

# 計算 EMA120 所需最少交易日（120 + 10 天緩衝，確保 EMA 收斂精度）
MIN_REQUIRED_DAYS = 130

# 輸出路徑：scripts/ 的上一層是 repo root，再進 data/
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "..", "data", "ema_tangling.json")

# ─────────────────────────────────────────────────────────────
#  台灣股市休市日（國定假日 + 彈性放假）
#  注意：此列表需每年初依行政院公告手動更新！
#  格式：{"MM-DD": "假日名稱"}，僅列平日休市（六日已由 cron 排除）
# ─────────────────────────────────────────────────────────────
TW_MARKET_HOLIDAYS = {
    # ── 2026 年台灣股市休市日 ──
    "01-01": "元旦",
    "01-26": "農曆除夕",
    "01-27": "農曆春節",
    "01-28": "農曆春節",
    "01-29": "農曆春節",
    "01-30": "農曆春節",
    "02-02": "春節補假",
    "02-28": "和平紀念日",
    "04-03": "清明節",
    "06-19": "端午節",
    "09-25": "中秋節",
    "10-09": "國慶日補假",
    "10-10": "國慶日",
}


# ─────────────────────────────────────────────────────────────
#  Step 1：取得股票清單
# ─────────────────────────────────────────────────────────────

def get_stock_list():
    """取得上市 + 上櫃普通股清單"""
    stocks = []

    # ── 上市 (TWSE) ──
    for attempt in range(2):
        try:
            url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
            r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
            for item in r.json():
                sid = item.get("Code", "").strip()
                name = item.get("Name", "").strip()
                if len(sid) == 4 and sid.isdigit():
                    stocks.append({"stock_id": sid, "name": name, "market": "TWSE"})
            twse_count = sum(1 for s in stocks if s["market"] == "TWSE")
            print(f"  上市股票：{twse_count} 支")
            break
        except Exception as e:
            if attempt == 0:
                print(f"  上市清單取得失敗，3秒後重試：{e}")
                time.sleep(3)
            else:
                print(f"  上市清單取得失敗（已重試）：{e}")

    # ── 上櫃 (TPEx) ──
    for attempt in range(2):
        try:
            url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
            r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
            for item in r.json():
                sid = (item.get("SecuritiesCompanyCode") or item.get("Code") or "").strip()
                name = (item.get("CompanyName") or item.get("Name") or "").strip()
                if len(sid) == 4 and sid.isdigit():
                    stocks.append({"stock_id": sid, "name": name, "market": "TPEX"})
            tpex_count = sum(1 for s in stocks if s["market"] == "TPEX")
            print(f"  上櫃股票：{tpex_count} 支")
            break
        except Exception as e:
            if attempt == 0:
                print(f"  上櫃清單取得失敗，3秒後重試：{e}")
                time.sleep(3)
            else:
                print(f"  上櫃清單取得失敗（已重試）：{e}")

    return stocks


# ─────────────────────────────────────────────────────────────
#  Step 2：策略核心運算
# ─────────────────────────────────────────────────────────────

def calc_ema(arr, span):
    """計算指數移動平均（EWM，adjust=False）"""
    s = pd.Series(arr)
    return s.ewm(span=span, adjust=False).mean().values


def check_strategy(close, volume):
    """
    均線糾結策略條件判斷。

    參數：
        close：np.ndarray，按時間升序排列
        volume：np.ndarray，按時間升序排列（單位：股，需轉換為張）

    回傳：
        (True, result_dict)  符合全部條件
        (False, None)        不符合
    """
    n = len(close)
    if n < MIN_REQUIRED_DAYS:
        return False, None

    # ── 計算 EMA ──
    ema20_arr  = calc_ema(close, 20)
    ema60_arr  = calc_ema(close, 60)
    ema120_arr = calc_ema(close, 120)

    ema20  = float(ema20_arr[-1])
    ema60  = float(ema60_arr[-1])
    ema120 = float(ema120_arr[-1])

    if ema20 <= 0 or ema60 <= 0 or ema120 <= 0:
        return False, None

    # ── 條件一：均線糾結（三線最大最小差距 / 最小值 ≤ 5%）──
    ema_max = max(ema20, ema60, ema120)
    ema_min = min(ema20, ema60, ema120)
    tangle_pct = (ema_max - ema_min) / ema_min * 100

    if tangle_pct > 5.0:
        return False, None

    # ── 條件二：收盤價站上所有均線 ──
    today_close = float(close[-1])
    if not (today_close > ema20 and today_close > ema60 and today_close > ema120):
        return False, None

    # ── 條件三：20 日均量 ≥ 500 張（1 張 = 1000 股）──
    vol_20ma = float(np.mean(volume[-20:])) / 1000.0   # 換算為張
    if vol_20ma < 500:
        return False, None

    result = {
        "close":       round(today_close, 2),
        "ema20":       round(ema20, 2),
        "ema60":       round(ema60, 2),
        "ema120":      round(ema120, 2),
        "tangle_pct":  round(tangle_pct, 2),
        "vol_20ma":    round(vol_20ma, 0),
    }

    return True, result


# ─────────────────────────────────────────────────────────────
#  Step 3：批次下載 + 主流程
# ─────────────────────────────────────────────────────────────

def batch_download(tickers_str, start_date, end_date, max_retries=2):
    for attempt in range(max_retries + 1):
        try:
            data = yf.download(
                tickers_str,
                start=start_date,
                end=end_date,
                group_by="ticker",
                auto_adjust=True,
                progress=False,
                threads=True,
            )
            return data
        except Exception as e:
            if attempt < max_retries:
                wait = 5 * (attempt + 1)
                print(f" (重試 {attempt+1}/{max_retries}，等待 {wait}s)", end="", flush=True)
                time.sleep(wait)
            else:
                print(f"    批次下載失敗（已重試 {max_retries} 次）：{e}")
                return None


def main(quick_test=False):
    print("=" * 55)
    print(f"  均線糾結選股  {TODAY}")
    print("=" * 55)

    # ── 判斷是否為休市日 ──
    today_mmdd = datetime.now().strftime("%m-%d")
    if today_mmdd in TW_MARKET_HOLIDAYS:
        holiday_name = TW_MARKET_HOLIDAYS[today_mmdd]
        print(f"今日為休市日 ({TODAY} {holiday_name})，跳過掃描")
        sys.exit(0)

    # ── 取得股票清單 ──
    print("\n[1] 取得股票清單...")
    stocks = get_stock_list()
    if not stocks:
        print("無法取得股票清單，結束執行")
        sys.exit(1)

    if quick_test:
        stocks = stocks[:200]
        print(f"    ⚡ 快速測試模式：僅掃描前 {len(stocks)} 支")

    print(f"    合計：{len(stocks)} 支\n")

    # 資料範圍：EMA120 需要足夠天數，抓 200 個日曆天
    end_date   = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=200)).strftime("%Y-%m-%d")

    # ── 批次掃描 ──
    print("[2] 開始掃描...")
    results = []
    BATCH = 100
    total = len(stocks)
    n_batches = (total + BATCH - 1) // BATCH
    total_scanned = 0
    total_skipped = 0

    for b_idx in range(n_batches):
        batch = stocks[b_idx * BATCH:(b_idx + 1) * BATCH]

        stock_map = {}
        for s in batch:
            suffix = ".TW" if s["market"] == "TWSE" else ".TWO"
            ticker = s["stock_id"] + suffix
            stock_map[ticker] = s

        ticker_str = " ".join(stock_map.keys())
        print(f"  批次 {b_idx+1}/{n_batches}：{len(batch)} 支", end="", flush=True)

        raw = batch_download(ticker_str, start_date, end_date)
        if raw is None or raw.empty:
            print(" → 下載失敗，跳過")
            total_skipped += 1
            continue

        total_scanned += len(batch)

        batch_hits = 0
        for ticker, s in stock_map.items():
            try:
                # 處理單支 vs 多支回傳格式不同的問題
                if len(batch) == 1:
                    df = raw.dropna(how="all")
                else:
                    lvl0 = raw.columns.get_level_values(0)
                    if ticker not in lvl0:
                        continue
                    df = raw[ticker].dropna(how="all")

                if df is None or df.empty or len(df) < MIN_REQUIRED_DAYS:
                    continue

                close  = df["Close"].values.astype(float)
                volume = df["Volume"].values.astype(float)

                passed, result = check_strategy(close, volume)

                if passed:
                    result["stock_id"] = s["stock_id"]
                    result["name"]     = s["name"]
                    result["market"]   = s["market"]
                    results.append(result)
                    batch_hits += 1

            except Exception:
                pass

        print(f" → 找到 {batch_hits} 支" if batch_hits else " → 本批無符合")
        time.sleep(1.2)   # 避免頻繁請求

    # ── 輸出結果 ──
    print(f"\n{'='*55}")
    print(f"  篩選完成！符合條件：{len(results)} 支")
    coverage_rate = round(total_scanned / len(stocks) * 100, 1) if stocks else 0
    print(f"  掃描覆蓋率：{total_scanned:,} / {len(stocks):,}（{coverage_rate}%）")
    if total_skipped:
        print(f"  跳過批次：{total_skipped}")
    print(f"{'='*55}\n")

    if results:
        results.sort(key=lambda x: x["tangle_pct"])
        print(f"{'代號':<6} {'名稱':<10} {'收盤':>8} {'EMA20':>8} {'EMA60':>8} {'EMA120':>9} {'糾結%':>7} {'均量(張)':>9}")
        print("-" * 75)
        for r in results:
            print(
                f"{r['stock_id']:<6} {r['name'][:8]:<10} "
                f"{r['close']:>8.2f} {r['ema20']:>8.2f} {r['ema60']:>8.2f} {r['ema120']:>9.2f} "
                f"{r['tangle_pct']:>6.2f}% {r['vol_20ma']:>8.0f}"
            )

    output = {
        "strategy_id": "ema_tangling",
        "updated": TODAY,
        "total": len(results),
        "scan_coverage": {
            "scanned": total_scanned,
            "total": len(stocks),
            "rate": round(total_scanned / len(stocks) * 100, 1) if stocks else 0,
            "skipped_batches": total_skipped,
        },
        "results": results,
    }

    os.makedirs(os.path.dirname(os.path.abspath(OUTPUT_PATH)), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n結果已寫入：{os.path.abspath(OUTPUT_PATH)}")

    # ── 寫入歷史紀錄 ──
    history_dir = os.path.join(SCRIPT_DIR, "..", "data", "history")
    os.makedirs(history_dir, exist_ok=True)
    history_path = os.path.join(history_dir, f"ema_tangling_{TODAY}.json")
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"歷史紀錄已寫入：{os.path.abspath(history_path)}")

    # ── LINE 推播通知 ──
    send_line_notification(results)

    return results


FLEX_MAX_STOCKS = 15          # Flex Message 最多顯示股票數，避免超過 LINE 50KB 限制
FLEX_COLOR_PRIMARY = "#1a5fa8"
FLEX_COLOR_TANGLE  = "#0c6b3e"


def build_flex_message(results):
    """組裝 Flex Message JSON"""

    if not results:
        bubble = {
            "type": "bubble",
            "size": "mega",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "◇ 均線糾結選股", "weight": "bold", "size": "lg", "color": FLEX_COLOR_PRIMARY},
                ],
                "paddingAll": "20px",
                "backgroundColor": "#f7f8fa"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "今日無符合條件標的", "size": "md", "color": "#888888", "align": "center", "margin": "xl"}
                ],
                "paddingAll": "20px"
            }
        }
        return {"type": "flex", "altText": f"◇ 均線糾結選股 {TODAY}：無符合條件標的", "contents": bubble}

    stock_rows = []
    for r in results[:FLEX_MAX_STOCKS]:
        stock_rows.append({"type": "separator", "margin": "md"})
        stock_rows.append({
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": r["stock_id"], "size": "md", "weight": "bold", "color": FLEX_COLOR_PRIMARY},
                        {"type": "text", "text": r["name"], "size": "xs", "color": "#555555"}
                    ],
                    "flex": 3
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": f"{r['close']:.2f}", "size": "sm", "align": "center", "weight": "bold"},
                        {"type": "text", "text": f"糾結 {r['tangle_pct']:.2f}%", "size": "xs", "align": "center", "color": FLEX_COLOR_TANGLE}
                    ],
                    "flex": 2
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": f"E20:{r['ema20']:.1f}", "size": "xxs", "align": "center", "color": "#888888"},
                        {"type": "text", "text": f"均量:{r['vol_20ma']:.0f}張", "size": "xxs", "align": "center", "color": "#888888"}
                    ],
                    "flex": 2
                }
            ],
            "margin": "md",
            "paddingAll": "4px"
        })

    if len(results) > FLEX_MAX_STOCKS:
        stock_rows.append({"type": "separator", "margin": "md"})
        stock_rows.append({"type": "text", "text": f"...還有 {len(results) - FLEX_MAX_STOCKS} 支，請查看完整報告", "size": "xs", "color": "#aaaaaa", "margin": "md", "align": "center"})

    bubble = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "◇ 均線糾結選股", "weight": "bold", "size": "lg", "color": FLEX_COLOR_PRIMARY},
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": f"📅 {TODAY}", "size": "xs", "color": "#aaaaaa"},
                        {"type": "text", "text": f"✅ {len(results)} 支符合", "size": "xs", "color": FLEX_COLOR_TANGLE, "align": "end"},
                    ],
                    "margin": "md"
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "EMA20/60/120 糾結 ≤ 5%，股價站上所有均線", "size": "xxs", "color": "#aaaaaa"}
                    ],
                    "margin": "sm"
                }
            ],
            "paddingAll": "20px",
            "backgroundColor": "#f7f8fa"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "代號/名稱", "size": "xxs", "color": "#aaaaaa", "flex": 3},
                        {"type": "text", "text": "收盤/糾結%", "size": "xxs", "color": "#aaaaaa", "flex": 2, "align": "center"},
                        {"type": "text", "text": "EMA/均量", "size": "xxs", "color": "#aaaaaa", "flex": 2, "align": "center"},
                    ]
                },
                *stock_rows
            ],
            "paddingAll": "20px"
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "button",
                    "action": {
                        "type": "uri",
                        "label": "📈 查看完整報告",
                        "uri": "https://weeiywun.github.io/twstockscan/"
                    },
                    "style": "primary",
                    "color": "#1a5fa8",
                    "height": "sm"
                }
            ],
            "paddingAll": "12px"
        }
    }

    return {"type": "flex", "altText": f"◇ 均線糾結選股 {TODAY}：{len(results)} 支符合條件", "contents": bubble}


def send_line_notification(results):
    """透過 LINE Messaging API 推播均線糾結掃描結果（Flex Message）。"""
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = os.environ.get("LINE_USER_ID")

    if not token or not user_id:
        print("\n[LINE] 環境變數未設定，跳過推播通知")
        return

    flex_msg = build_flex_message(results)

    payload = {
        "to": user_id,
        "messages": [flex_msg],
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }

    try:
        resp = requests.post(
            "https://api.line.me/v2/bot/message/push",
            json=payload,
            headers=headers,
            timeout=15,
        )
        if resp.status_code == 200:
            print("[LINE] 推播通知已成功送出")
        else:
            print(f"[LINE] 推播失敗：HTTP {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"[LINE] 推播通知發生例外：{e}")


if __name__ == "__main__":
    quick = "--quick" in sys.argv
    main(quick_test=quick)
