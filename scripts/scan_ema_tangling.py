#!/usr/bin/env python3
"""
均線糾結選股策略 (EMA Tangling Scanner)
盤後自動執行，篩選符合「EMA20/60/120 均線糾結且股價站上所有均線」型態的台股。

策略條件：
  條件一：EMA20、EMA60、EMA120 三條均線最大值與最小值的差距 / 最小值 ≤ 10%
  條件二：收盤價 > EMA20、EMA60、EMA120（股價站上任意二條均線）
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
import pandas as pd
import numpy as np
from finmind_client import fetch_all_stocks

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

    # ── 條件一：均線糾結（三線最大最小差距 / 最小值 ≤ 10%）──
    ema_max = max(ema20, ema60, ema120)
    ema_min = min(ema20, ema60, ema120)
    tangle_pct = (ema_max - ema_min) / ema_min * 100

    if tangle_pct > 10.0:
        return False, None

    # ── 條件二：收盤價至少大於二條均線 ──
    today_close = float(close[-1])
    count = sum([
        today_close > ema20,
        today_close > ema60,
        today_close > ema120
    ])
    if count < 2:
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
#  Step 3：下載資料（FinMind）+ 主流程
# ─────────────────────────────────────────────────────────────

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

    # 資料範圍：EMA120 需要 130 個交易日，300 個日曆天可確保取到足夠資料
    end_date   = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=300)).strftime("%Y-%m-%d")

    # ── 批次下載全市場資料（yfinance）──
    print("[2] 下載股價資料（yfinance）...")
    stock_data = fetch_all_stocks(stocks, start_date, end_date)

    if not stock_data:
        print("無法取得任何股票資料，結束執行")
        sys.exit(1)

    # ── 套用策略 ──
    print("\n[3] 套用均線糾結策略...")
    results      = []
    total_scanned = 0
    total_skipped = 0

    for s in stocks:
        sid = s["stock_id"]
        df  = stock_data.get(sid)

        if df is None or df.empty or len(df) < MIN_REQUIRED_DAYS:
            total_skipped += 1
            continue

        total_scanned += 1
        try:
            close  = df["Close"].values.astype(float)
            volume = df["Volume"].values.astype(float)

            passed, result = check_strategy(close, volume)

            if passed:
                result["stock_id"] = sid
                result["name"]     = s["name"]
                result["market"]   = s["market"]
                results.append(result)
        except Exception:
            pass

    # ── 輸出結果 ──
    print(f"\n{'='*55}")
    print(f"  篩選完成！符合條件：{len(results)} 支")
    coverage_rate = round(total_scanned / len(stocks) * 100, 1) if stocks else 0
    print(f"  掃描覆蓋率：{total_scanned:,} / {len(stocks):,}（{coverage_rate}%）")
    if total_skipped:
        print(f"  資料不足跳過：{total_skipped} 支")
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

if __name__ == "__main__":
    quick = "--quick" in sys.argv
    main(quick_test=quick)
