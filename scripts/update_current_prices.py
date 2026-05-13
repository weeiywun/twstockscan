#!/usr/bin/env python3
"""
手動觸發現價更新（供前端「↑ 更新現價」按鈕使用）

資料來源優先順序：
  1. TWSE MIS 即時 API（免費、無需 Token）
       盤中 09:00-15:30 → 即時成交價
       盤後 / 次日開盤前 → 最後成交收盤價
  2. price_cache.parquet（FINMIND 每日掃描快取）
  3. FINMIND BYDATE（僅在前兩者皆失敗時使用）

輸出：data/current_prices.json
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(SCRIPT_DIR, "..", "data")
PERF_PATH  = os.path.join(DATA_DIR, "performance.json")

TW_TZ = timezone(timedelta(hours=8))
NOW   = datetime.now(TW_TZ)
TODAY = NOW.strftime("%Y-%m-%d")

MIS_URL     = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
MIS_BATCH   = 80   # 每次查詢筆數上限（保守值）
MIS_HEADERS = {"User-Agent": "Mozilla/5.0"}


def collect_stock_ids() -> set:
    ids: set[str] = set()

    def _load(path, *keys):
        if not os.path.exists(path):
            return
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        for key in keys:
            for item in d.get(key, []):
                sid = item.get("stock_id") or item.get("ticker")
                if sid:
                    ids.add(sid)

    _load(os.path.join(DATA_DIR, "chips_big_holder.json"), "results")
    _load(os.path.join(DATA_DIR, "volume_signal.json"),     "results")
    _load(os.path.join(DATA_DIR, "right_top.json"),         "results")
    _load(os.path.join(DATA_DIR, "right_top_track.json"),  "active", "history")
    _load(os.path.join(DATA_DIR, "vcp.json"),              "results")
    _load(os.path.join(DATA_DIR, "performance.json"),      "positions")
    _load(os.path.join(DATA_DIR, "ai_analysis.json"),      "active", "history")
    return ids


def _load_market_map() -> dict:
    """從 stock_list_cache.json 取得 stock_id → 'tse' / 'otc' 對照表。"""
    path = os.path.join(DATA_DIR, "stock_list_cache.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        stocks = json.load(f)
    return {
        s["stock_id"]: "tse" if s.get("market") == "TWSE" else "otc"
        for s in stocks
    }


def fetch_from_mis(ids: set) -> tuple[dict, str]:
    """
    TWSE MIS 即時 API。
    回傳 (prices_dict, data_date)。
    盤中取 z（成交價），無成交時取 y（昨收）。
    """
    market_map = _load_market_map()
    parts = [f"{market_map.get(sid, 'tse')}_{sid}.tw" for sid in sorted(ids)]

    prices: dict[str, float] = {}
    got_z = False  # 是否有取到今日成交價

    for i in range(0, len(parts), MIS_BATCH):
        batch = parts[i:i + MIS_BATCH]
        ex_ch = "|".join(batch)
        try:
            r = requests.get(
                MIS_URL,
                params={"ex_ch": ex_ch, "json": "1", "delay": "0"},
                headers=MIS_HEADERS,
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"  ⚠️  MIS 批次失敗（{i//MIS_BATCH + 1}）：{e}")
            continue

        for item in data.get("msgArray", []):
            sid = item.get("c", "")
            if sid not in ids:
                continue
            z = item.get("z", "-")
            if z and z != "-":
                prices[sid] = round(float(z), 2)
                got_z = True
            else:
                # 尚未開盤或無成交，改用昨收
                y = item.get("y", "-")
                if y and y != "-":
                    prices[sid] = round(float(y), 2)

        if i + MIS_BATCH < len(parts):
            time.sleep(0.3)

    if not prices:
        return {}, ""

    # 有今日成交 → 日期為今日；全為昨收 → 日期為昨日
    if got_z:
        data_date = TODAY
    else:
        data_date = (NOW - timedelta(days=1)).strftime("%Y-%m-%d")

    return prices, data_date


def fetch_from_cache(ids: set) -> tuple[dict, str]:
    """從 price_cache.parquet 取最新可用收盤，回傳 (prices, date)。"""
    cache_path = os.path.join(DATA_DIR, "price_cache.parquet")
    if not os.path.exists(cache_path):
        return {}, ""
    df = pd.read_parquet(cache_path)
    if df.empty:
        return {}, ""

    latest_date = df["date"].max()
    latest_str  = str(latest_date)[:10]
    day_df = df[df["date"] == latest_date]
    prices = {
        row["stock_id"]: round(float(row["close"]), 2)
        for _, row in day_df.iterrows()
        if row["stock_id"] in ids
    }
    if prices:
        print(f"  📦 price_cache 取得 {latest_str} 收盤（{len(prices)} 支）")
    return prices, latest_str


def fetch_from_finmind(ids: set, token: str) -> tuple[dict, str]:
    """FINMIND BYDATE fallback，回傳 (prices, actual_date)。"""
    sys.path.insert(0, SCRIPT_DIR)
    from finmind_client import fetch_price_bydate

    for i in range(6):
        date = (NOW - timedelta(days=i)).strftime("%Y-%m-%d")
        print(f"  → FINMIND BYDATE {date}")
        df = fetch_price_bydate(date, date, token)
        if df is None:
            print("  ❌ FINMIND API 致命錯誤（401/402/網路）")
            return {}, ""
        if df.empty:
            continue
        actual_date = str(df["date"].max())[:10]
        prices = {
            row["stock_id"]: round(float(row["close"]), 2)
            for _, row in df.iterrows()
            if row["stock_id"] in ids
        }
        if prices:
            print(f"     實際資料日期：{actual_date}，符合標的 {len(prices)}/{len(ids)} 支")
            return prices, actual_date
    return {}, ""


def update_performance_prices(prices: dict, data_date: str) -> None:
    """將現價快照同步進績效頁使用的 price_history。"""
    if not prices or not data_date or not os.path.exists(PERF_PATH):
        return
    with open(PERF_PATH, encoding="utf-8") as f:
        perf = json.load(f)

    positions = perf.get("positions", [])
    open_ids = {p.get("stock_id") for p in positions if not p.get("confirmed", False)}
    open_ids.discard(None)
    if not open_ids:
        return

    price_history = perf.get("price_history") or {}
    updated = 0
    for sid in sorted(open_ids):
        if sid not in prices:
            continue
        price_history.setdefault(sid, {})[data_date] = round(float(prices[sid]), 2)
        updated += 1

    if not updated:
        return

    perf["price_history"] = price_history
    perf["last_updated"] = data_date
    with open(PERF_PATH, "w", encoding="utf-8") as f:
        json.dump(perf, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"  ✅ performance.json 持倉現價已同步：{updated}/{len(open_ids)} 支（{data_date}）")


def main():
    print(f"=== 現價快速更新 {TODAY} {NOW.strftime('%H:%M')} ===")

    ids = collect_stock_ids()
    print(f"  需更新標的：{len(ids)} 支")
    if not ids:
        print("  ℹ️  無標的，結束"); return

    # ── 1. TWSE MIS 即時 API（優先）──
    print("  [1] TWSE MIS 即時 API...")
    prices, data_date = fetch_from_mis(ids)
    sources = []
    if prices:
        print(f"  ✅ MIS 取得 {len(prices)}/{len(ids)} 支（資料日期：{data_date}）")
        sources.append("twse_mis")

    # ── 2. price_cache fallback（補 MIS 缺漏）──
    missing = ids - set(prices)
    if missing:
        print(f"  [2] 使用 price_cache 補缺漏（{len(missing)} 支）...")
        cache_prices, cache_date = fetch_from_cache(missing)
        if cache_prices:
            prices.update(cache_prices)
            data_date = data_date or cache_date
            sources.append("price_cache")
            print(f"  ✅ price_cache 補到 {len(cache_prices)}/{len(missing)} 支")

    # ── 3. FINMIND BYDATE fallback（補剩餘缺漏）──
    missing = ids - set(prices)
    if missing:
        token = os.environ.get("FINMIND_TOKEN", "")
        if not token:
            print(f"  ⚠️  FINMIND_TOKEN 未設定，仍缺 {len(missing)} 支")
        else:
            print(f"  [3] 使用 FINMIND BYDATE 補剩餘缺漏（{len(missing)} 支）...")
            finmind_prices, finmind_date = fetch_from_finmind(missing, token)
            if finmind_prices:
                prices.update(finmind_prices)
                data_date = data_date or finmind_date
                sources.append("finmind_bydate")
                print(f"  ✅ FINMIND 補到 {len(finmind_prices)}/{len(missing)} 支")

    if not prices:
        print("  ❌ 三種來源皆失敗，無法取得現價"); sys.exit(1)

    missing = ids - set(prices)
    if missing:
        print(f"  ⚠️  仍有 {len(missing)} 支無現價：{', '.join(sorted(missing))}")

    out = {
        "date":    data_date,
        "source":  "+".join(sources) if sources else "unknown",
        "updated": NOW.isoformat(),
        "prices":  prices,
    }
    out_path = os.path.join(DATA_DIR, "current_prices.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    update_performance_prices(prices, data_date)

    print(f"  ✅ 已輸出 {len(prices)}/{len(ids)} 支現價（{data_date}）→ current_prices.json（來源：{out['source']}）")


if __name__ == "__main__":
    main()
