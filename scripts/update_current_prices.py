#!/usr/bin/env python3
"""
手動觸發現價更新（供前端「↑ 更新現價」按鈕使用）

1. 從各 JSON 收集前端顯示的標的
2. 優先從 price_cache.parquet 讀取最新收盤（不消耗 API 配額）
3. 快取無資料時，呼叫 FINMIND BYDATE（約 1,800 筆，免費額度內）
4. 輸出 data/current_prices.json → 前端讀取後套用至各頁面

注意：15:35 前台股尚未收盤，FINMIND 無今日資料，
     此時自動改取最近一個交易日的收盤價。
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(SCRIPT_DIR, "..", "data")

TW_TZ = timezone(timedelta(hours=8))
NOW   = datetime.now(TW_TZ)
TODAY = NOW.strftime("%Y-%m-%d")

# 15:35 前（尚未收盤 + 資料發布緩衝），從昨日開始找
MARKET_CLOSE = NOW.replace(hour=15, minute=35, second=0, microsecond=0)
START_OFFSET = 0 if NOW >= MARKET_CLOSE else 1


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
    _load(os.path.join(DATA_DIR, "right_top_track.json"),  "active", "history")
    _load(os.path.join(DATA_DIR, "performance.json"),      "positions")
    _load(os.path.join(DATA_DIR, "ai_analysis.json"),      "active", "history")
    return ids


def fetch_from_cache(ids: set) -> tuple[dict, str]:
    """從 price_cache.parquet 取最新一日的收盤價，回傳 (prices, date)。"""
    cache_path = os.path.join(DATA_DIR, "price_cache.parquet")
    if not os.path.exists(cache_path):
        return {}, ""
    df = pd.read_parquet(cache_path)
    if df.empty:
        return {}, ""

    # 取快取中最新的交易日
    latest_date = df["date"].max()
    latest_str  = str(latest_date)[:10]

    # 若 15:35 前，最新日必須是昨日以前；若已收盤，最新日可以是今日
    if NOW < MARKET_CLOSE and latest_str >= TODAY:
        print(f"  ℹ️  price_cache 最新為 {latest_str}，但尚未收盤，略過今日資料")
        cutoff = pd.Timestamp(TODAY)
        df = df[df["date"] < cutoff]
        if df.empty:
            return {}, ""
        latest_date = df["date"].max()
        latest_str  = str(latest_date)[:10]

    day_df = df[df["date"] == latest_date]
    prices = {}
    for _, row in day_df.iterrows():
        if row["stock_id"] in ids:
            prices[row["stock_id"]] = round(float(row["close"]), 2)

    if prices:
        print(f"  📦 price_cache 取得 {latest_str} 收盤（{len(prices)} 支）")
    else:
        print(f"  ℹ️  price_cache 無符合標的")
    return prices, latest_str


def fetch_from_finmind(ids: set, token: str) -> tuple[dict, str]:
    """呼叫 FINMIND BYDATE，回傳 (prices, actual_date)。"""
    sys.path.insert(0, SCRIPT_DIR)
    from finmind_client import fetch_price_bydate

    for i in range(START_OFFSET, START_OFFSET + 6):
        date = (NOW - timedelta(days=i)).strftime("%Y-%m-%d")
        print(f"  → FINMIND BYDATE {date}")
        df = fetch_price_bydate(date, date, token)
        if df is None:
            print("  ❌ FINMIND API 致命錯誤（401/402/網路）")
            return {}, ""
        if df.empty:
            print(f"     {date} 無資料（可能為假日），往前一天")
            continue

        # 取回傳資料的實際日期（FINMIND 可能調整）
        actual_date = str(df["date"].max())[:10]
        prices = {}
        for _, row in df.iterrows():
            if row["stock_id"] in ids:
                prices[row["stock_id"]] = round(float(row["close"]), 2)
        if prices:
            print(f"     實際資料日期：{actual_date}，符合標的 {len(prices)}/{len(ids)} 支")
            return prices, actual_date
    return {}, ""


def main():
    if NOW < MARKET_CLOSE:
        print(f"=== 現價快速更新 ({TODAY} {NOW.strftime('%H:%M')}，盤中→取前一交易日收盤) ===")
    else:
        print(f"=== 現價快速更新 ({TODAY} {NOW.strftime('%H:%M')}，已收盤) ===")

    ids = collect_stock_ids()
    print(f"  需更新標的：{len(ids)} 支")

    # 1. 優先讀快取
    prices, data_date = fetch_from_cache(ids)
    source = "price_cache"

    # 2. 快取無資料 → FINMIND API
    if not prices:
        token = os.environ.get("FINMIND_TOKEN", "")
        if not token:
            print("  ❌ FINMIND_TOKEN 未設定，且快取無可用資料"); sys.exit(1)
        prices, data_date = fetch_from_finmind(ids, token)
        source = "finmind_bydate"

    if not prices:
        print("  ❌ 無法取得任何現價"); sys.exit(1)

    out = {
        "date":    data_date,          # 資料實際日期（非執行日）
        "source":  source,
        "updated": NOW.isoformat(),
        "prices":  prices,
    }
    out_path = os.path.join(DATA_DIR, "current_prices.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"  ✅ 已輸出 {len(prices)} 支收盤價（{data_date}）→ current_prices.json（來源：{source}）")


if __name__ == "__main__":
    main()
