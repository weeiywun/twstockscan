#!/usr/bin/env python3
"""
量增訊號掃描器 (Layer 2 每日盤後)
從 data/chips_big_holder.json 讀取入池標的，
透過 FinMind 抓取近期日線，篩選量增訊號。

觸發條件：
  當日成交量 >= 10日均量 * 1.5
  收盤價 > EMA5

額外工作：
  每日掃描結束後，將各標的最新收盤價與周漲跌
  回寫至 chips_big_holder.json（price_updated 欄位），
  讓籌碼選股頁面的現價維持每日更新。
"""

import json, os, sys, time
from datetime import datetime, timedelta, timezone
from finmind_client import fetch_stock_price, load_price_cache, get_stock_price_from_cache

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = os.path.join(SCRIPT_DIR, "..", "data")
POOL_PATH   = os.path.join(DATA_DIR, "chips_big_holder.json")
OUTPUT_PATH = os.path.join(DATA_DIR, "volume_signal.json")
PERF_PATH   = os.path.join(DATA_DIR, "performance.json")

TW_TZ      = timezone(timedelta(hours=8))
TODAY      = datetime.now(TW_TZ).strftime("%Y-%m-%d")
START_DATE = (datetime.now(TW_TZ) - timedelta(days=40)).strftime("%Y-%m-%d")

VOL_MULT      = 1.5
EMA5_PERIOD   = 5
FINMIND_SLEEP = 0.35


def _require_fresh_cache(cache) -> None:
    if cache is None or cache.empty:
        return
    latest = cache["date"].max().strftime("%Y-%m-%d")
    if latest != TODAY:
        print(f"❌ price_cache.parquet 最新資料為 {latest}，不是 {TODAY}；停止量增訊號掃描，避免用舊價量產生今日訊號")
        sys.exit(1)


def _calc_ema(closes, span):
    if len(closes) < span:
        return None
    k = 2 / (span + 1)
    ema = closes[0]
    for c in closes[1:]:
        ema = c * k + ema * (1 - k)
    return ema


def check_signal(stock_id, token, cache=None):
    """
    回傳 (signal_dict | None, price_info | None)。
    price_info 無論是否觸發訊號都會回傳，供每日現價更新使用。
    """
    if cache is not None:
        df = get_stock_price_from_cache(cache, stock_id, START_DATE, TODAY)
    else:
        df = fetch_stock_price(stock_id, START_DATE, TODAY, token)
    if df is None or len(df) < 11:
        return None, None

    closes  = df["close"].tolist()
    volumes = df["volume_lots"].tolist()

    close_today  = closes[-1]
    vol_today    = volumes[-1]
    vol_10d_avg  = sum(volumes[-11:-1]) / 10

    ema5 = _calc_ema(closes[:-1], EMA5_PERIOD)
    if ema5 is None:
        return None, None

    wago = closes[-6] if len(closes) >= 6 else closes[0]
    week_chg_pct = round((close_today - wago) / wago * 100.0, 2) if wago else None

    price_info = {
        "close":        round(close_today, 2),
        "week_chg_pct": week_chg_pct,
    }

    signal = None
    if vol_today >= vol_10d_avg * VOL_MULT and close_today > ema5:
        signal = {
            "close":       round(close_today, 2),
            "vol_today":   int(vol_today),
            "vol_10d_avg": round(vol_10d_avg, 0),
            "vol_ratio":   round(vol_today / vol_10d_avg, 2) if vol_10d_avg else None,
            "ema5":        round(ema5, 2),
        }

    return signal, price_info


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

    price_cache = load_price_cache()
    if price_cache is not None:
        print(f"  📦 使用 price_cache.parquet")
        _require_fresh_cache(price_cache)
    else:
        print("  ⚠️  price_cache.parquet 不存在，改用 FinMind API")

    results   = []
    price_map: dict[str, dict] = {}

    for i, item in enumerate(pool, 1):
        sid = item["stock_id"]
        signal, price_info = check_signal(sid, finmind_token, cache=price_cache)
        if price_info:
            price_map[sid] = price_info
        if signal:
            results.append({
                "stock_id":      sid,
                "name":          item["name"],
                "industry":      item["industry"],
                "tags":          item.get("tags", []),
                "tag_score":     item.get("tag_score", 0),
                "cumulative_3w": item.get("cumulative_3w"),
                "big_pct_1000":  item.get("big_pct_1000"),
                **signal,
                "signal_date":   TODAY,
            })
            print(f"  ✅ {sid} {item['name']}  量比={signal['vol_ratio']}x  收盤={signal['close']}")
        if i % 20 == 0:
            print(f"  掃描進度：{i}/{len(pool)}")
        if price_cache is None:
            time.sleep(FINMIND_SLEEP)

    results.sort(key=lambda r: r.get("vol_ratio") or 0, reverse=True)
    print(f"\n觸發訊號：{len(results)} 支")
    _write_output(results)

    _update_chips_prices(pool_data, price_map)
    _update_performance_prices(finmind_token, cache=price_cache)


def _update_chips_prices(pool_data: dict, price_map: dict) -> None:
    """將每日最新收盤價與周漲跌寫入 chips_big_holder.json。"""
    if not price_map:
        print("⚠️  無價格資料，略過 chips_big_holder.json 現價更新")
        return

    updated = 0
    for item in pool_data.get("results", []):
        sid = item["stock_id"]
        if sid in price_map:
            item["close"] = price_map[sid]["close"]
            if price_map[sid].get("week_chg_pct") is not None:
                item["week_chg_pct"] = price_map[sid]["week_chg_pct"]
            updated += 1

    pool_data["price_updated"] = TODAY

    with open(POOL_PATH, "w", encoding="utf-8") as f:
        json.dump(pool_data, f, ensure_ascii=False, indent=2)

    print(f"✅ chips_big_holder.json 現價已更新：{updated}/{len(pool_data.get('results', []))} 支")


def _update_performance_prices(token, cache=None):
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
        if cache is not None:
            df = get_stock_price_from_cache(cache, sid, START_DATE, TODAY)
        else:
            df = fetch_stock_price(sid, START_DATE, TODAY, token)
            time.sleep(FINMIND_SLEEP)
        if df is None or len(df) == 0:
            continue
        if sid not in price_history:
            price_history[sid] = {}
        for _, row in df.iterrows():
            d = str(row["date"])[:10]
            price_history[sid][d] = round(float(row["close"]), 2)
        print(f"  ✅ {sid} 收盤價已更新")
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
