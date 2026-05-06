#!/usr/bin/env python3
"""
手動觸發現價更新（供前端「↑ 更新現價」按鈕使用）

1. 從各 JSON 收集前端顯示的標的
2. 優先從 price_cache.parquet 讀取當日收盤（不消耗 API 配額）
3. 快取無今日資料時，呼叫 FINMIND BYDATE（約 1,800 筆，免費額度內）
4. 輸出 data/current_prices.json → 前端讀取後套用至各頁面
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(SCRIPT_DIR, "..", "data")

TW_TZ = timezone(timedelta(hours=8))
TODAY = datetime.now(TW_TZ).strftime("%Y-%m-%d")


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


def fetch_from_cache(ids: set) -> dict:
    cache_path = os.path.join(DATA_DIR, "price_cache.parquet")
    if not os.path.exists(cache_path):
        return {}
    df = pd.read_parquet(cache_path)
    today_df = df[df["date"] == pd.Timestamp(TODAY)]
    if today_df.empty:
        print("  ℹ️  price_cache 無今日資料")
        return {}
    prices = {}
    for _, row in today_df.iterrows():
        if row["stock_id"] in ids:
            prices[row["stock_id"]] = round(float(row["close"]), 2)
    return prices


def fetch_from_finmind(ids: set, token: str) -> dict:
    sys.path.insert(0, SCRIPT_DIR)
    from finmind_client import fetch_price_bydate

    # 嘗試今日，若空（非交易日）往前找最多 5 天
    for i in range(5):
        date = (datetime.now(TW_TZ) - timedelta(days=i)).strftime("%Y-%m-%d")
        print(f"  → FINMIND BYDATE {date}")
        df = fetch_price_bydate(date, date, token)
        if df is None:
            print("  ❌ FINMIND API 致命錯誤（401/402/網路）")
            return {}
        if df.empty:
            continue
        prices = {}
        for _, row in df.iterrows():
            if row["stock_id"] in ids:
                prices[row["stock_id"]] = round(float(row["close"]), 2)
        if prices:
            return prices
    return {}


def main():
    print(f"=== 現價快速更新 ({TODAY}) ===")

    ids = collect_stock_ids()
    print(f"  需更新標的：{len(ids)} 支：{sorted(ids)}")

    # 1. 優先讀快取
    prices = fetch_from_cache(ids)
    source = "price_cache"

    # 2. 快取無資料 → FINMIND API
    if not prices:
        token = os.environ.get("FINMIND_TOKEN", "")
        if not token:
            print("  ❌ FINMIND_TOKEN 未設定，且快取無今日資料"); sys.exit(1)
        prices = fetch_from_finmind(ids, token)
        source = "finmind_bydate"

    if not prices:
        print("  ❌ 無法取得任何現價"); sys.exit(1)

    out = {
        "date":    TODAY,
        "source":  source,
        "updated": datetime.now(TW_TZ).isoformat(),
        "prices":  prices,
    }
    out_path = os.path.join(DATA_DIR, "current_prices.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"  ✅ 已輸出 {len(prices)} 支現價 → current_prices.json（來源：{source}）")


if __name__ == "__main__":
    main()
