#!/usr/bin/env python3
"""
量增訊號掃描器 (Layer 2 每日盤後)
從 data/chips_big_holder.json 讀取入池標的，
透過 FinMind 抓取近期日線，篩選量增訊號。

觸發條件：
  當日成交量 >= 10日均量 * 1.5
  收盤價 > EMA5
"""

import json, os, time
from datetime import datetime, timedelta, timezone
from finmind_client import fetch_stock_price

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = os.path.join(SCRIPT_DIR, "..", "data")
POOL_PATH   = os.path.join(DATA_DIR, "chips_big_holder.json")
OUTPUT_PATH = os.path.join(DATA_DIR, "volume_signal.json")
PERF_PATH   = os.path.join(DATA_DIR, "performance.json")

TW_TZ      = timezone(timedelta(hours=8))
TODAY      = datetime.now(TW_TZ).strftime("%Y-%m-%d")
START_DATE = (datetime.now(TW_TZ) - timedelta(days=40)).strftime("%Y-%m-%d")

VOL_MULT      = 1.5   # 當日量 >= 10日均量 * 1.5
EMA5_PERIOD   = 5
FINMIND_SLEEP = 0.35


def _calc_ema(closes, span):
    if len(closes) < span:
        return None
    k = 2 / (span + 1)
    ema = closes[0]
    for c in closes[1:]:
        ema = c * k + ema * (1 - k)
    return ema


def check_signal(stock_id, token):
    df = fetch_stock_price(stock_id, START_DATE, TODAY, token)
    if df is None or len(df) < 11:
        return None

    closes  = df["close"].tolist()
    volumes = df["volume_lots"].tolist()

    close_today  = closes[-1]
    vol_today    = volumes[-1]
    vol_10d_avg  = sum(volumes[-11:-1]) / 10

    ema5 = _calc_ema(closes[:-1], EMA5_PERIOD)  # EMA5 from previous closes
    if ema5 is None:
        return None

    if vol_today >= vol_10d_avg * VOL_MULT and close_today > ema5:
        return {
            "close":       round(close_today, 2),
            "vol_today":   int(vol_today),
            "vol_10d_avg": round(vol_10d_avg, 0),
            "vol_ratio":   round(vol_today / vol_10d_avg, 2) if vol_10d_avg else None,
            "ema5":        round(ema5, 2),
        }
    return None


def now_tw():
    return datetime.now(TW_TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def main():
    print("=== 量增訊號掃描器 (Layer 2) ===")
    finmind_token = os.environ.get("FINMIND_TOKEN", "")
    if not finmind_token:
        print("⚠️  FINMIND_TOKEN 未設定")

    if not os.path.exists(POOL_PATH):
        print(f"⚠️  找不到 {POOL_PATH}，請先執行 Layer 1")
        return

    with open(POOL_PATH, encoding="utf-8") as f:
        pool_data = json.load(f)

    pool = pool_data.get("results", [])
    print(f"入池標的：{len(pool)} 支")
    if not pool:
        print("池為空，結束")
        _write_output([])
        return

    results = []
    for i, item in enumerate(pool, 1):
        sid   = item["stock_id"]
        price = check_signal(sid, finmind_token)
        if price:
            results.append({
                "stock_id":    sid,
                "name":        item["name"],
                "industry":    item["industry"],
                "tags":        item.get("tags", []),
                "tag_score":   item.get("tag_score", 0),
                "cumulative_3w": item.get("cumulative_3w"),
                "big_pct_1000":  item.get("big_pct_1000"),
                **price,
                "signal_date": TODAY,
            })
            print(f"  ✅ {sid} {item['name']}  量比={price['vol_ratio']}x  收盤={price['close']}")
        if i % 20 == 0:
            print(f"  掃描進度：{i}/{len(pool)}")
        time.sleep(FINMIND_SLEEP)

    results.sort(key=lambda r: r.get("vol_ratio") or 0, reverse=True)
    print(f"\n觸發訊號：{len(results)} 支")
    _write_output(results)

    # 更新績效持倉的收盤價
    _update_performance_prices(finmind_token)


def _update_performance_prices(token):
    if not os.path.exists(PERF_PATH):
        return
    with open(PERF_PATH, encoding="utf-8") as f:
        perf = json.load(f)
    positions = perf.get("positions", [])
    open_ids = list({p["stock_id"] for p in positions if not p.get("confirmed", False)})
    if not open_ids:
        return
    print(f"\n📊 更新績效持倉收盤價：{len(open_ids)} 支")
    price_history = perf.get("price_history", {})
    for sid in open_ids:
        df = fetch_stock_price(sid, START_DATE, TODAY, token)
        if df is None or len(df) == 0:
            continue
        if sid not in price_history:
            price_history[sid] = {}
        for _, row in df.iterrows():
            d = str(row["date"])[:10]
            price_history[sid][d] = round(float(row["close"]), 2)
        print(f"  ✅ {sid} 收盤價已更新")
        time.sleep(FINMIND_SLEEP)
    perf["price_history"] = price_history
    perf["last_updated"] = TODAY
    with open(PERF_PATH, "w", encoding="utf-8") as f:
        json.dump(perf, f, ensure_ascii=False, indent=2)
    print(f"✅ performance.json 已更新")


def _write_output(results):
    output = {"strategy_id": "volume_signal", "updated": now_tw(), "results": results}
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"✅ 已寫入 {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
