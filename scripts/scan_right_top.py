#!/usr/bin/env python3
"""
右上角選股掃描器
掃描全市場，篩選同時滿足：
  1. 今日收盤價創 90 個交易日新高
  2. 當日成交量 >= 10 日均量 * 1.5
並統計各產業觸發數量。
"""

import json, os, time, requests
from datetime import datetime, timedelta, timezone
from finmind_client import fetch_stock_price

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = os.path.join(SCRIPT_DIR, "..", "data")
OUTPUT_PATH = os.path.join(DATA_DIR, "right_top.json")

TW_TZ      = timezone(timedelta(hours=8))
TODAY      = datetime.now(TW_TZ).strftime("%Y-%m-%d")
# 90 個交易日 ≈ 130 個日曆天
START_DATE = (datetime.now(TW_TZ) - timedelta(days=130)).strftime("%Y-%m-%d")

HIGH_PERIOD   = 90    # 取最近幾個交易日作為新高基準
VOL_MA_PERIOD = 10
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
            # 只保留 4 位純數字代號（一般股）
            if not sid.isdigit() or len(sid) != 4:
                continue
            market = s.get("type", "")
            if market not in ("twse", "tpex", "上市", "上櫃", "TWSE", "TPEX"):
                continue
            stocks.append({
                "stock_id": sid,
                "name":     s.get("stock_name", ""),
                "industry": s.get("industry_category", ""),
                "market":   "TWSE" if market in ("twse", "上市", "TWSE") else "TPEX",
            })
        return stocks
    except Exception as e:
        print(f"⚠️  取得股票清單失敗：{e}")
        return []


def check_signal(stock_id, token):
    df = fetch_stock_price(stock_id, START_DATE, TODAY, token)
    if df is None or len(df) < HIGH_PERIOD + 1:
        return None

    df_tail = df.tail(HIGH_PERIOD + 1).reset_index(drop=True)
    closes  = df_tail["close"].tolist()
    volumes = df_tail["volume_lots"].tolist()

    close_today = closes[-1]
    high_prev   = max(closes[:-1])  # 前 90 個交易日的最高收盤價

    # 條件一：今日收盤突破前 90 交易日最高價
    if close_today <= high_prev:
        return None

    # 條件二：量能放大
    if len(volumes) < VOL_MA_PERIOD + 1:
        return None
    vol_today   = volumes[-1]
    vol_10d_avg = sum(volumes[-VOL_MA_PERIOD - 1:-1]) / VOL_MA_PERIOD
    if vol_10d_avg == 0 or vol_today < vol_10d_avg * VOL_MULT:
        return None

    prev_close = closes[-2] if len(closes) >= 2 else close_today
    change_pct = round((close_today - prev_close) / prev_close * 100, 2) if prev_close else 0

    return {
        "close":       round(close_today, 2),
        "high_90d":    round(high_prev, 2),
        "vol_today":   int(vol_today),
        "vol_10d_avg": round(vol_10d_avg, 1),
        "vol_ratio":   round(vol_today / vol_10d_avg, 2),
        "change_pct":  change_pct,
    }


def now_tw():
    return datetime.now(TW_TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def main():
    print("=== 右上角選股掃描器 ===")
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
            print(f"  ✅ {sid} {s['name']}  量比={signal['vol_ratio']}x  漲幅={signal['change_pct']}%")
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
