#!/usr/bin/env python3
"""
大戶持股分析器 v2.1
讀取 data/big1000.csv（千張大戶）與 data/big400.csv（400張大戶）
篩選條件：兩個門檻「同時」維持 4 週 >= 趨勢
搭配 yfinance 股價，產生 data/chips_big_holder.json

每週手動更新 CSV 後，由 GitHub Actions 自動執行此腳本。
"""

import csv
import json
import os
import re
import sys
import time
import warnings
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import requests
import yfinance as yf

warnings.filterwarnings("ignore")

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = os.path.join(SCRIPT_DIR, "..", "data")
CSV_1000    = os.path.join(DATA_DIR, "big1000.csv")
CSV_400     = os.path.join(DATA_DIR, "big400.csv")
OUTPUT_PATH = os.path.join(DATA_DIR, "chips_big_holder.json")

TW_TZ       = timezone(timedelta(hours=8))
TODAY       = datetime.now(TW_TZ).strftime("%Y-%m-%d")

BIG_PCT_MIN = 30.0   # 千張大戶最低持股比例 (%)
TREND_WEEKS = 4      # 需連續幾週 >= 趨勢
EMA_PERIOD  = 120    # 日線 EMA120（≈ 週線 EMA24，約 6 個月）
DEV_MIN     = -10.0  # EMA120 乖離率下限 (%)
DEV_MAX     =   5.0  # EMA120 乖離率上限 (%)
VOL_MIN     = 1000   # 最低日均量（張）
PRICE_DAYS  = 200    # yfinance 抓取天數（確保 EMA120 收斂）

FLEX_MAX_STOCKS    = 15
FLEX_COLOR_PRIMARY = "#7b4fa8"   # 紫色：籌碼集中策略專屬
FLEX_COLOR_ACCENT  = "#0c6b3e"   # 綠色：增幅正值


# ─────────────────────────────────────────────────────────────
#  Step 1：讀取 CSV
# ─────────────────────────────────────────────────────────────

def parse_csv(path: str, encoding: str) -> tuple[dict, list]:
    """
    讀取持股 CSV，回傳 (stocks_dict, sorted_date_cols)。
    stocks_dict: {stock_id: {name, industry, market_cap, csv_close, pct_map}}
    pct_map: {YYYYMMDD: float}
    """
    stocks = {}
    with open(path, encoding=encoding, newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        date_cols = sorted([h for h in headers if re.fullmatch(r"\d{8}", h)])

        close_col = next((h for h in headers if "收盤" in h), None)

        for row in reader:
            raw = (row.get("股票") or "").strip()
            if not raw:
                continue
            parts = raw.split(None, 1)
            if len(parts) < 2 or not re.fullmatch(r"\d{4}", parts[0]):
                continue
            sid, name = parts[0], parts[1].strip()

            mc_raw = (row.get("市值(億)") or "").replace(",", "").strip()
            try:
                market_cap = float(mc_raw) if mc_raw else None
            except ValueError:
                market_cap = None

            close_raw = (row.get(close_col) or "").strip() if close_col else ""
            try:
                csv_close = float(close_raw) if close_raw else None
            except ValueError:
                csv_close = None

            pct_map = {}
            for d in date_cols:
                val = (row.get(d) or "").strip()
                try:
                    pct_map[d] = float(val)
                except ValueError:
                    pass

            stocks[sid] = {
                "name":       name,
                "industry":   (row.get("類別") or "").strip(),
                "market_cap": market_cap,
                "csv_close":  csv_close,
                "pct_map":    pct_map,
            }

    return stocks, date_cols


# ─────────────────────────────────────────────────────────────
#  Step 2：策略篩選
# ─────────────────────────────────────────────────────────────

def passes_trend(pct_map: dict, date_cols: list, n: int = TREND_WEEKS) -> bool:
    """
    檢查最近 n 週是否每週 >= 前一週（允許持平，不能下降）。
    date_cols 已排序由舊到新。
    """
    valid = [d for d in date_cols if d in pct_map]
    if len(valid) < n:
        return False
    recent = valid[-n:]
    for i in range(1, n):
        if pct_map[recent[i]] < pct_map[recent[i - 1]]:
            return False
    return True


# ─────────────────────────────────────────────────────────────
#  Step 3：取得市場對照表
# ─────────────────────────────────────────────────────────────

def get_market_map() -> dict:
    """回傳 {stock_id: 'TWSE'|'TPEX'}"""
    mmap = {}
    for url, market in [
        ("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", "TWSE"),
        ("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes", "TPEX"),
    ]:
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            for item in r.json():
                sid = (item.get("Code") or item.get("SecuritiesCompanyCode") or "").strip()
                if re.fullmatch(r"\d{4}", sid):
                    mmap[sid] = market
        except Exception as e:
            print(f"  ⚠️  市場清單取得失敗（{market}）：{e}")
    return mmap


# ─────────────────────────────────────────────────────────────
#  Step 4：yfinance 取股價與 EMA120
# ─────────────────────────────────────────────────────────────

def fetch_price_ema(stock_id: str, suffix: str) -> dict | None:
    """回傳 {close, ema120, deviation, vol_lots}，失敗回傳 None。"""
    ticker = f"{stock_id}{suffix}"
    end   = datetime.now(TW_TZ)
    start = end - timedelta(days=PRICE_DAYS)
    try:
        df = yf.download(
            ticker,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=True,
        )
        if df is None or df.empty or len(df) < 10:
            return None

        close_arr = df["Close"].dropna().values.astype(float)
        vol_arr   = df["Volume"].dropna().values.astype(float)
        if len(close_arr) < 10:
            return None

        ema120    = float(pd.Series(close_arr).ewm(span=EMA_PERIOD, adjust=False).mean().iloc[-1])
        close     = float(close_arr[-1])
        deviation = round((close - ema120) / ema120 * 100, 2)
        vol_lots  = int(round(np.mean(vol_arr[-20:]) / 1000)) if len(vol_arr) >= 20 else int(round(np.mean(vol_arr) / 1000))

        return {
            "close":     round(close, 2),
            "ema120":    round(ema120, 2),
            "deviation": deviation,
            "vol_lots":  vol_lots,
        }
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────
#  LINE 推播（Flex Message）
# ─────────────────────────────────────────────────────────────

def build_flex_message(results_1000: list) -> dict:
    """組裝 Flex Message JSON"""

    if not results_1000:
        bubble = {
            "type": "bubble",
            "size": "mega",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "◈ 籌碼集中選股", "weight": "bold", "size": "lg", "color": FLEX_COLOR_PRIMARY},
                ],
                "paddingAll": "20px",
                "backgroundColor": "#f7f8fa"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "本週無符合條件標的", "size": "md", "color": "#888888", "align": "center", "margin": "xl"}
                ],
                "paddingAll": "20px"
            }
        }
        return {"type": "flex", "altText": f"◈ 籌碼集中選股 {TODAY}：無符合條件標的", "contents": bubble}

    stock_rows = []
    for r in results_1000[:FLEX_MAX_STOCKS]:
        chg_color = FLEX_COLOR_ACCENT if r["big_4w_chg"] >= 0 else "#c0392b"
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
                        {"type": "text", "text": f"乖離 {r['deviation']:+.1f}%", "size": "xs", "align": "center", "color": "#888888"}
                    ],
                    "flex": 2
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": f"{r['big_pct_latest']:.1f}%", "size": "sm", "align": "center", "weight": "bold"},
                        {"type": "text", "text": f"4週 {r['big_4w_chg']:+.2f}", "size": "xs", "align": "center", "color": chg_color}
                    ],
                    "flex": 2
                }
            ],
            "margin": "md",
            "paddingAll": "4px"
        })

    if len(results_1000) > FLEX_MAX_STOCKS:
        stock_rows.append({"type": "separator", "margin": "md"})
        stock_rows.append({"type": "text", "text": f"...還有 {len(results_1000) - FLEX_MAX_STOCKS} 支，請查看完整報告", "size": "xs", "color": "#aaaaaa", "margin": "md", "align": "center"})

    bubble = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "◈ 籌碼集中選股", "weight": "bold", "size": "lg", "color": FLEX_COLOR_PRIMARY},
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": f"📅 {TODAY}", "size": "xs", "color": "#aaaaaa"},
                        {"type": "text", "text": f"✅ {len(results_1000)} 支符合", "size": "xs", "color": FLEX_COLOR_ACCENT, "align": "end"},
                    ],
                    "margin": "md"
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "千張+400張雙門檻 4週增持，EMA120 低基期", "size": "xxs", "color": "#aaaaaa"}
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
                        {"type": "text", "text": "收盤/乖離", "size": "xxs", "color": "#aaaaaa", "flex": 2, "align": "center"},
                        {"type": "text", "text": "千張%/4週", "size": "xxs", "color": "#aaaaaa", "flex": 2, "align": "center"},
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
                    "color": FLEX_COLOR_PRIMARY,
                    "height": "sm"
                }
            ],
            "paddingAll": "12px"
        }
    }

    return {"type": "flex", "altText": f"◈ 籌碼集中選股 {TODAY}：{len(results_1000)} 支符合條件", "contents": bubble}


def send_line_notification(results_1000: list):
    """透過 LINE Messaging API 推播籌碼集中掃描結果（Flex Message）。"""
    token   = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    raw_ids = os.environ.get("LINE_USER_IDS") or os.environ.get("LINE_USER_ID")

    if not token or not raw_ids:
        print("\n[LINE] 環境變數未設定，跳過推播通知")
        return

    user_ids = [uid.strip() for uid in raw_ids.split(",") if uid.strip()]
    print(f"[LINE] 推播對象：{len(user_ids)} 人")

    flex_msg = build_flex_message(results_1000)
    payload  = {"to": user_ids, "messages": [flex_msg]}
    headers  = {
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {token}",
    }

    try:
        resp = requests.post(
            "https://api.line.me/v2/bot/message/multicast",
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


# ─────────────────────────────────────────────────────────────
#  主程式
# ─────────────────────────────────────────────────────────────

def now_tw() -> str:
    return datetime.now(TW_TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def main():
    print("=== 大戶持股分析器 v2.1 ===")

    # Step 1：讀取 CSV
    print("\nStep 1：讀取 big1000.csv / big400.csv...")
    stocks_1000, dates_1000 = parse_csv(CSV_1000, "utf-8-sig")
    stocks_400,  dates_400  = parse_csv(CSV_400,  "utf-8")
    print(f"  big1000: {len(stocks_1000)} 支，{len(dates_1000)} 週")
    print(f"  big400:  {len(stocks_400)} 支，{len(dates_400)} 週")

    # Step 2：策略篩選（千張 AND 400張 同時符合）
    print(f"\nStep 2：篩選（千張 AND 400張 均 {TREND_WEEKS} 週≥趨勢，千張>{BIG_PCT_MIN}%）...")
    candidates = []
    common_sids = set(stocks_1000) & set(stocks_400)

    for sid in sorted(common_sids):
        s1 = stocks_1000[sid]
        s4 = stocks_400[sid]

        latest_date = max(s1["pct_map"].keys()) if s1["pct_map"] else None
        if not latest_date or s1["pct_map"][latest_date] < BIG_PCT_MIN:
            continue

        if not passes_trend(s1["pct_map"], dates_1000):
            continue

        if not passes_trend(s4["pct_map"], dates_400):
            continue

        candidates.append(sid)

    print(f"  通過：{len(candidates)} 支")

    if not candidates:
        print("⚠️  無符合條件股票，輸出空結果")
        _write_output([], [])
        return

    # Step 3：市場清單
    print("\nStep 3：取得市場清單...")
    mmap = get_market_map()
    print(f"  上市+上櫃：{len(mmap)} 支")

    # Step 4：yfinance 取股價（僅供顯示，不過濾）
    print(f"\nStep 4：取股價（{len(candidates)} 支）...")
    results_1000, results_400 = [], []

    for sid in candidates:
        s1     = stocks_1000[sid]
        s4     = stocks_400[sid]
        suffix = ".TW" if mmap.get(sid, "TWSE") == "TWSE" else ".TWO"

        price = fetch_price_ema(sid, suffix)

        recent_1000 = sorted(s1["pct_map"])[-TREND_WEEKS:]
        recent_400  = sorted(s4["pct_map"])[-TREND_WEEKS:]
        pcts_1000   = [round(s1["pct_map"][d], 2) for d in recent_1000]
        pcts_400    = [round(s4["pct_map"][d], 2) for d in recent_400]
        labels      = [f"{d[4:6]}-{d[6:8]}" for d in recent_1000]

        base = {
            "stock_id":    sid,
            "name":        s1["name"],
            "industry":    s1["industry"],
            "market_cap":  s1["market_cap"],
            "close":       price["close"]     if price else None,
            "ema120":      price["ema120"]    if price else None,
            "deviation":   price["deviation"] if price else None,
            "vol_lots":    price["vol_lots"]  if price else None,
            "date_labels": labels,
        }

        results_1000.append({**base,
            "big_pct_latest": pcts_1000[-1],
            "big_4w_chg":     round(pcts_1000[-1] - pcts_1000[0], 2),
            "big_trend":      pcts_1000,
        })
        results_400.append({**base,
            "big_pct_latest": pcts_400[-1],
            "big_4w_chg":     round(pcts_400[-1] - pcts_400[0], 2),
            "big_trend":      pcts_400,
        })
        sys.stdout.write(".")
        sys.stdout.flush()
        time.sleep(0.3)

    results_1000.sort(key=lambda r: r["big_4w_chg"], reverse=True)
    results_400.sort(key=lambda r: r["big_4w_chg"],  reverse=True)

    print(f"\n  最終：千張 {len(results_1000)} 支 / 400張 {len(results_400)} 支")
    _write_output(results_1000, results_400)


def _write_output(results_1000: list, results_400: list):
    output = {
        "strategy_id": "chips_big_holder",
        "updated":     now_tw(),
        "results":     results_1000,
        "results_400": results_400,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"✅ 已寫入 {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
