#!/usr/bin/env python3
"""
右上角選股掃描器（週K版）
掃描全市場，篩選同時滿足：
  1. 最新完整週收盤價創近 10 週新高
  2. 最新完整週成交量 >= 20 週均量 * 1.5
並統計各產業觸發數量。
"""

import json, os, time, requests
import pandas as pd
from datetime import datetime, timedelta, timezone
from finmind_client import fetch_stock_price

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = os.path.join(SCRIPT_DIR, "..", "data")
OUTPUT_PATH = os.path.join(DATA_DIR, "right_top.json")

TW_TZ      = timezone(timedelta(hours=8))
TODAY      = datetime.now(TW_TZ).strftime("%Y-%m-%d")
# 20 週均量 + 10 週新高 → 至少需要 21 完整週 ≈ 175 個日曆天，取 200 保留緩衝
START_DATE = (datetime.now(TW_TZ) - timedelta(days=200)).strftime("%Y-%m-%d")

HIGH_PERIOD   = 10   # 週新高基準（週數）
VOL_MA_PERIOD = 20   # 均量週數
VOL_MULT      = 1.5
FINMIND_SLEEP = 0.35
FINMIND_API   = "https://api.finmindtrade.com/api/v4/data"


def get_all_stocks(token):
    """取得全市場上市/上櫃一般股清單（排除 ETF、特別股）"""
    try:
        r = requests.get(FINMIND_API, params={
            "dataset": "TaiwanStockInfo",
            "token": token,
        }, timeout=30)
        data = r.json()
        if data.get("status") != 200:
            print(f"⚠️  TaiwanStockInfo 回應異常：{data.get('msg')}")
            return []
        stocks = []
        for s in data["data"]:
            sid = s.get("stock_id", "")
            # 只保留 4 位純數字代號
            if not sid.isdigit() or len(sid) != 4:
                continue
            # 排除 ETF（4 位代號以 00 開頭，如 0050、0056、0062）
            if sid.startswith("00"):
                continue
            # 排除產業分類標記為 ETF 的標的（安全網）
            industry = s.get("industry_category", "")
            if "ETF" in industry:
                continue
            market = s.get("type", "")
            if market not in ("twse", "tpex", "上市", "上櫃", "TWSE", "TPEX"):
                continue
            stocks.append({
                "stock_id": sid,
                "name":     s.get("stock_name", ""),
                "industry": industry,
                "market":   "TWSE" if market in ("twse", "上市", "TWSE") else "TPEX",
            })
        return stocks
    except Exception as e:
        print(f"⚠️  取得股票清單失敗：{e}")
        return []


def to_weekly(df):
    """將日K DataFrame 轉成週K，只保留已完整收盤的週（W-FRI）。"""
    df = df.copy()
    df = df.set_index("date")
    weekly = df.resample("W-FRI").agg({
        "open":        "first",
        "max":         "max",
        "min":         "min",
        "close":       "last",
        "volume_lots": "sum",
    }).dropna(subset=["close"])
    weekly = weekly.reset_index()
    # 若最後一列的週結束日期在今天之後，代表該週尚未收盤，剔除
    today_ts = pd.Timestamp(TODAY)
    if len(weekly) > 0 and weekly.iloc[-1]["date"] > today_ts:
        weekly = weekly.iloc[:-1]
    return weekly.reset_index(drop=True)


def check_signal(stock_id, token):
    df = fetch_stock_price(stock_id, START_DATE, TODAY, token)
    if df is None or df.empty:
        return None

    wk = to_weekly(df)
    # 至少需要 HIGH_PERIOD + 1 週（新高判斷）且 VOL_MA_PERIOD + 1 週（均量判斷）
    min_weeks = max(HIGH_PERIOD, VOL_MA_PERIOD) + 1
    if len(wk) < min_weeks:
        return None

    closes  = wk["close"].tolist()
    volumes = wk["volume_lots"].tolist()

    close_latest = closes[-1]
    high_prev10  = max(closes[-HIGH_PERIOD - 1:-1])  # 前 10 週最高收盤

    # 條件一：最新週收盤突破前 10 週最高價
    if close_latest <= high_prev10:
        return None

    # 條件一b：前 3 週皆未突破10週高（確保為第一根，非強勢延續）
    # i=2：上週，i=3：前2週，i=4：前3週
    if len(closes) >= 14:
        for i in range(2, 5):
            if closes[-i] > max(closes[-i - 10:-i]):
                return None

    # 條件一c：突破前10週價格波動幅度 < 20%（確認橫盤打底）
    base_closes = closes[-11:-1]
    base_low    = min(base_closes)
    base_high   = max(base_closes)
    if base_low == 0 or (base_high - base_low) / base_low >= 0.20:
        return None

    # 條件一d：突破前10週均線斜率 < 5%（排除均線已走揚的趨勢股）
    # ma_now：以上週為基準的10週均線；ma_prev：4週前的10週均線
    if len(closes) >= 15:
        ma_now  = sum(closes[-11:-1]) / 10
        ma_prev = sum(closes[-15:-5]) / 10
        if ma_prev > 0 and (ma_now - ma_prev) / ma_prev * 100 >= 5.0:
            return None

    # 條件二：最新週量能 >= 20 週均量 * 1.5，且週均量 >= 500 張
    vol_latest   = volumes[-1]
    vol_20w_avg  = sum(volumes[-VOL_MA_PERIOD - 1:-1]) / VOL_MA_PERIOD
    if vol_20w_avg < 500:
        return None
    if vol_latest < vol_20w_avg * VOL_MULT:
        return None

    prev_close = closes[-2] if len(closes) >= 2 else close_latest
    change_pct = round((close_latest - prev_close) / prev_close * 100, 2) if prev_close else 0

    # 最新完整週的週五日期
    latest_week_date = wk.iloc[-1]["date"].strftime("%Y-%m-%d")

    return {
        "close":        round(close_latest, 2),
        "high_10w":     round(high_prev10, 2),
        "vol_latest_w": int(vol_latest),
        "vol_20w_avg":  round(vol_20w_avg, 1),
        "vol_ratio":    round(vol_latest / vol_20w_avg, 2),
        "change_pct":   change_pct,
        "week_date":    latest_week_date,
    }


def now_tw():
    return datetime.now(TW_TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def main():
    print("=== 右上角選股掃描器（週K版）===")
    token = os.environ.get("FINMIND_TOKEN", "")
    if not token:
        print("⚠️  FINMIND_TOKEN 未設定")

    stocks = get_all_stocks(token)
    print(f"全市場股票：{len(stocks)} 支")
    if not stocks:
        _write_output([], [])
        return

    results = []
    for i, s in enumerate(stocks, 1):
        sid    = s["stock_id"]
        signal = check_signal(sid, token)
        if signal:
            results.append({
                "stock_id":    sid,
                "name":        s["name"],
                "industry":    s["industry"],
                "market":      s["market"],
                **signal,
                "signal_date": TODAY,
            })
            print(f"  ✅ {sid} {s['name']}  量比={signal['vol_ratio']}x  漲幅={signal['change_pct']}%  週={signal['week_date']}")
        if i % 100 == 0:
            print(f"  掃描進度：{i}/{len(stocks)}，已觸發 {len(results)} 支")
        time.sleep(FINMIND_SLEEP)

    results.sort(key=lambda r: r.get("vol_ratio") or 0, reverse=True)
    print(f"\n觸發訊號：{len(results)} 支")

    # 產業統計
    industry_map = {}
    for r in results:
        ind = r["industry"] or "其他"
        if ind not in industry_map:
            industry_map[ind] = {"industry": ind, "count": 0, "stocks": []}
        industry_map[ind]["count"] += 1
        industry_map[ind]["stocks"].append({"stock_id": r["stock_id"], "name": r["name"]})
    industry_stats = sorted(industry_map.values(), key=lambda x: x["count"], reverse=True)

    _write_output(results, industry_stats)


def _write_output(results, industry_stats):
    output = {
        "strategy_id":    "right_top",
        "updated":        now_tw(),
        "results":        results,
        "industry_stats": industry_stats,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"✅ 已寫入 {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
