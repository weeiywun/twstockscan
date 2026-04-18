#!/usr/bin/env python3
"""
大戶持股分析器 v2.2
讀取 data/big1000.csv（千張大戶）與 data/big400.csv（400張大戶）
篩選條件：兩個門檻「同時」維持 4 週 >= 趨勢
股價來自 TWSE/TPEX OpenAPI；EMA120 透過個股月份資料計算。
產生 data/chips_big_holder.json

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

import requests

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
EMA_MONTHS  = 7      # 抓取月份數（7 個月 ≈ 154 交易日，足夠收斂）

FLEX_MAX_STOCKS    = 15
FLEX_COLOR_PRIMARY = "#e66e29"
FLEX_COLOR_ACCENT  = "#0c6b3e"


# ─────────────────────────────────────────────────────────────
#  Step 1：讀取 CSV
# ─────────────────────────────────────────────────────────────

def parse_csv(path: str, encoding: str) -> tuple[dict, list]:
    stocks = {}
    with open(path, encoding=encoding, newline="") as f:
        reader = csv.DictReader(f)
        headers   = reader.fieldnames or []
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
    valid = [d for d in date_cols if d in pct_map]
    if len(valid) < n:
        return False
    recent = valid[-n:]
    for i in range(1, n):
        if pct_map[recent[i]] < pct_map[recent[i - 1]]:
            return False
    return True


# ─────────────────────────────────────────────────────────────
#  Step 3：取得市場對照表 + 今日股價
# ─────────────────────────────────────────────────────────────

def get_market_and_price() -> tuple[dict, dict]:
    """
    mmap: {stock_id: 'TWSE'|'TPEX'}
    pmap: {stock_id: {close, vol_lots}}
    """
    mmap, pmap = {}, {}
    sources = [
        ("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL",
         "TWSE", "Code", "ClosingPrice", "TradeVolume"),
        ("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes",
         "TPEX", "SecuritiesCompanyCode", "Close", "TradeVolume"),
    ]
    for url, market, code_key, close_key, vol_key in sources:
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            for item in r.json():
                sid = (item.get(code_key) or "").strip()
                if not re.fullmatch(r"\d{4}", sid):
                    continue
                mmap[sid] = market
                try:
                    close    = float(str(item.get(close_key) or "").replace(",", ""))
                    vol_lots = int(float(str(item.get(vol_key) or "0").replace(",", ""))) // 1000
                    if close > 0:
                        pmap[sid] = {"close": close, "vol_lots": vol_lots}
                except (ValueError, TypeError):
                    pass
        except Exception as e:
            print(f"  ⚠️  {market} 資料取得失敗：{e}")
    return mmap, pmap


# ─────────────────────────────────────────────────────────────
#  Step 4：個股月份資料 → EMA120
# ─────────────────────────────────────────────────────────────

def _month_list(n: int) -> list[tuple[int, int]]:
    """回傳最近 n 個月的 (year, month)，由舊到新。"""
    now = datetime.now(TW_TZ)
    result, y, m = [], now.year, now.month
    for _ in range(n):
        result.append((y, m))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return list(reversed(result))


def _fetch_closes_twse(stock_id: str, year: int, month: int) -> list[float]:
    url = (f"https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY"
           f"?stockNo={stock_id}&date={year}{month:02d}01&response=json")
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        data = r.json()
        if data.get("stat") != "OK":
            return []
        closes = []
        for row in data.get("data", []):
            try:
                val = str(row[6]).replace(",", "")
                if val not in ("--", ""):
                    closes.append(float(val))
            except (ValueError, IndexError):
                pass
        return closes
    except Exception:
        return []


def _fetch_closes_tpex(stock_id: str, year: int, month: int) -> list[float]:
    roc = year - 1911
    url = (f"https://www.tpex.org.tw/web/stock/aftertrading/daily_trading_info/"
           f"st43_result.php?l=zh-tw&d={roc}/{month:02d}&stkno={stock_id}&s=0,asc&o=json")
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        data = r.json()
        rows = data.get("aaData") or data.get("data", [])
        closes = []
        for row in rows:
            try:
                val = str(row[6]).replace(",", "")
                if val not in ("--", "", "0"):
                    closes.append(float(val))
            except (ValueError, IndexError):
                pass
        return closes
    except Exception:
        return []


def _calc_ema(closes: list[float], span: int) -> float | None:
    if len(closes) < span // 2:
        return None
    k = 2 / (span + 1)
    ema = closes[0]
    for c in closes[1:]:
        ema = c * k + ema * (1 - k)
    return ema


def fetch_ema120(stock_id: str, is_twse: bool, current_close: float) -> dict | None:
    """取近 EMA_MONTHS 個月日收盤，計算 EMA120 與乖離率。"""
    closes = []
    for y, m in _month_list(EMA_MONTHS):
        if is_twse:
            closes.extend(_fetch_closes_twse(stock_id, y, m))
        else:
            closes.extend(_fetch_closes_tpex(stock_id, y, m))
        time.sleep(0.2)

    ema = _calc_ema(closes, EMA_PERIOD)
    if ema is None:
        return None

    return {
        "ema120":    round(ema, 2),
        "deviation": round((current_close - ema) / ema * 100, 2),
    }


# ─────────────────────────────────────────────────────────────
#  LINE 推播（Flex Message）
# ─────────────────────────────────────────────────────────────

def build_flex_message(results_1000: list) -> dict:
    if not results_1000:
        bubble = {
            "type": "bubble", "size": "mega",
            "header": {
                "type": "box", "layout": "vertical",
                "contents": [{"type": "text", "text": "◈ 籌碼集中選股",
                               "weight": "bold", "size": "lg", "color": FLEX_COLOR_PRIMARY}],
                "paddingAll": "20px", "backgroundColor": "#f7f8fa"
            },
            "body": {
                "type": "box", "layout": "vertical",
                "contents": [{"type": "text", "text": "本週無符合條件標的",
                               "size": "md", "color": "#888888", "align": "center", "margin": "xl"}],
                "paddingAll": "20px"
            }
        }
        return {"type": "flex", "altText": f"◈ 籌碼集中選股 {TODAY}：無符合條件標的", "contents": bubble}

    stock_rows = []
    for r in results_1000[:FLEX_MAX_STOCKS]:
        chg_color = FLEX_COLOR_ACCENT if r["big_4w_chg"] >= 0 else "#c0392b"
        dev_text  = f"乖離 {r['deviation']:+.1f}%" if r.get("deviation") is not None else "乖離 —"
        stock_rows.append({"type": "separator", "margin": "md"})
        stock_rows.append({
            "type": "box", "layout": "horizontal",
            "contents": [
                {
                    "type": "box", "layout": "vertical", "flex": 3,
                    "contents": [
                        {"type": "text", "text": r["stock_id"], "size": "md",
                         "weight": "bold", "color": FLEX_COLOR_PRIMARY},
                        {"type": "text", "text": r["name"], "size": "xs", "color": "#555555"}
                    ]
                },
                {
                    "type": "box", "layout": "vertical", "flex": 2,
                    "contents": [
                        {"type": "text", "text": f"{r['close']:.2f}" if r.get("close") else "—",
                         "size": "sm", "align": "center", "weight": "bold"},
                        {"type": "text", "text": dev_text, "size": "xs",
                         "align": "center", "color": "#888888"}
                    ]
                },
                {
                    "type": "box", "layout": "vertical", "flex": 2,
                    "contents": [
                        {"type": "text", "text": f"{r['big_pct_latest']:.1f}%",
                         "size": "sm", "align": "center", "weight": "bold"},
                        {"type": "text", "text": f"4週 {r['big_4w_chg']:+.2f}",
                         "size": "xs", "align": "center", "color": chg_color}
                    ]
                }
            ],
            "margin": "md", "paddingAll": "4px"
        })

    if len(results_1000) > FLEX_MAX_STOCKS:
        stock_rows += [
            {"type": "separator", "margin": "md"},
            {"type": "text", "text": f"...還有 {len(results_1000) - FLEX_MAX_STOCKS} 支，請查看完整報告",
             "size": "xs", "color": "#aaaaaa", "margin": "md", "align": "center"}
        ]

    bubble = {
        "type": "bubble", "size": "mega",
        "header": {
            "type": "box", "layout": "vertical",
            "contents": [
                {"type": "text", "text": "◈ 籌碼集中選股",
                 "weight": "bold", "size": "lg", "color": FLEX_COLOR_PRIMARY},
                {
                    "type": "box", "layout": "horizontal", "margin": "md",
                    "contents": [
                        {"type": "text", "text": f"📅 {TODAY}", "size": "xs", "color": "#aaaaaa"},
                        {"type": "text", "text": f"✅ {len(results_1000)} 支符合",
                         "size": "xs", "color": FLEX_COLOR_ACCENT, "align": "end"},
                    ]
                },
                {
                    "type": "box", "layout": "horizontal", "margin": "sm",
                    "contents": [
                        {"type": "text", "text": "千張+400張雙門檻 4週增持，EMA120 低基期",
                         "size": "xxs", "color": "#aaaaaa"}
                    ]
                }
            ],
            "paddingAll": "20px", "backgroundColor": "#f7f8fa"
        },
        "body": {
            "type": "box", "layout": "vertical", "paddingAll": "20px",
            "contents": [
                {
                    "type": "box", "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "代號/名稱", "size": "xxs", "color": "#aaaaaa", "flex": 3},
                        {"type": "text", "text": "收盤/乖離", "size": "xxs", "color": "#aaaaaa",
                         "flex": 2, "align": "center"},
                        {"type": "text", "text": "千張%/4週", "size": "xxs", "color": "#aaaaaa",
                         "flex": 2, "align": "center"},
                    ]
                },
                *stock_rows
            ]
        },
        "footer": {
            "type": "box", "layout": "vertical", "paddingAll": "12px",
            "contents": [{
                "type": "button",
                "action": {"type": "uri", "label": "📈 查看完整報告",
                           "uri": "https://weeiywun.github.io/twstockscan/"},
                "style": "primary", "color": FLEX_COLOR_PRIMARY, "height": "sm"
            }]
        }
    }
    return {"type": "flex", "altText": f"◈ 籌碼集中選股 {TODAY}：{len(results_1000)} 支符合條件",
            "contents": bubble}


def send_line_notification(results_1000: list):
    token   = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    raw_ids = os.environ.get("LINE_USER_IDS") or os.environ.get("LINE_USER_ID")
    if not token or not raw_ids:
        print("\n[LINE] 環境變數未設定，跳過推播通知")
        return
    user_ids = [uid.strip() for uid in raw_ids.split(",") if uid.strip()]
    print(f"[LINE] 推播對象：{len(user_ids)} 人")
    flex_msg = build_flex_message(results_1000)
    try:
        resp = requests.post(
            "https://api.line.me/v2/bot/message/multicast",
            json={"to": user_ids, "messages": [flex_msg]},
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {token}"},
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
    print("=== 大戶持股分析器 v2.2 ===")

    # Step 1：讀取 CSV
    print("\nStep 1：讀取 big1000.csv / big400.csv...")
    stocks_1000, dates_1000 = parse_csv(CSV_1000, "utf-8-sig")
    stocks_400,  dates_400  = parse_csv(CSV_400,  "utf-8")
    print(f"  big1000: {len(stocks_1000)} 支，{len(dates_1000)} 週")
    print(f"  big400:  {len(stocks_400)} 支，{len(dates_400)} 週")

    # Step 2：策略篩選（千張 AND 400張 同時符合）
    print(f"\nStep 2：篩選（千張 AND 400張 均 {TREND_WEEKS} 週≥趨勢，千張>{BIG_PCT_MIN}%）...")
    candidates = []
    for sid in sorted(set(stocks_1000) & set(stocks_400)):
        s1 = stocks_1000[sid]
        s4 = stocks_400[sid]
        latest = max(s1["pct_map"].keys()) if s1["pct_map"] else None
        if not latest or s1["pct_map"][latest] < BIG_PCT_MIN:
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

    # Step 3：市場清單 + 今日股價
    print("\nStep 3：取得市場清單與今日股價...")
    mmap, pmap = get_market_and_price()
    print(f"  上市+上櫃：{len(mmap)} 支，有股價：{len(pmap)} 支")
    if "2330" in pmap:
        p = pmap["2330"]
        print(f"  [診斷] 2330 ✅ close={p['close']}  vol={p['vol_lots']}張")
    else:
        print("  [診斷] 2330 ❌ 未取得股價，請確認 TWSE API 回應")

    # Step 4：個股月份資料 → EMA120
    print(f"\nStep 4：計算 EMA120（{len(candidates)} 支，每支 {EMA_MONTHS} 個月資料）...")
    results_1000, results_400 = [], []
    ema_ok, ema_fail = 0, 0

    for i, sid in enumerate(candidates, 1):
        s1      = stocks_1000[sid]
        s4      = stocks_400[sid]
        price   = pmap.get(sid)
        is_twse = mmap.get(sid, "TWSE") == "TWSE"

        ema_data = None
        if price:
            ema_data = fetch_ema120(sid, is_twse, price["close"])

        if ema_data:
            ema_ok += 1
        else:
            ema_fail += 1

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
            "close":       price["close"]       if price    else None,
            "ema120":      ema_data["ema120"]   if ema_data else None,
            "deviation":   ema_data["deviation"] if ema_data else None,
            "vol_lots":    price["vol_lots"]    if price    else None,
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

        if i % 50 == 0:
            print(f"  進度：{i}/{len(candidates)}，EMA 成功 {ema_ok} / 失敗 {ema_fail}")

    results_1000.sort(key=lambda r: r["big_4w_chg"], reverse=True)
    results_400.sort(key=lambda r: r["big_4w_chg"],  reverse=True)

    print(f"\n  EMA120：成功 {ema_ok} 支 / 失敗 {ema_fail} 支")
    print(f"  最終：千張 {len(results_1000)} 支 / 400張 {len(results_400)} 支")
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
