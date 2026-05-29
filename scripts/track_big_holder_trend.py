#!/usr/bin/env python3
"""趨勢大戶標的追蹤

- 從 big_holder_trend.json 讀取當週入選標的 → 新標的加入追蹤池
- 到期（14 曆日 = 2週）且未釘選 → 移入 expired
- 每次執行更新現價 / P&L / 剩餘天數
- expired 保留 7 曆日後清除（釘選不清除）
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

from finmind_client import load_price_cache, get_stock_price_from_cache

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
SOURCE_PATH = os.path.join(DATA_DIR, "big_holder_trend.json")
TRACK_PATH = os.path.join(DATA_DIR, "big_holder_trend_track.json")

TW_TZ = timezone(timedelta(hours=8))
TODAY = datetime.now(TW_TZ).strftime("%Y-%m-%d")

OBSERVE_CALENDAR_DAYS = 14
HISTORY_KEEP_CALENDAR_DAYS = 7


def load_json(path: str) -> dict[str, Any]:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_json(path: str, data: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def calendar_days_remaining(expire: date, today: date) -> int:
    return max((expire - today).days, 0)


def fetch_current_price(stock_id: str, price_cache) -> float | None:
    if price_cache is None:
        return None
    start = (datetime.now(TW_TZ) - timedelta(days=7)).strftime("%Y-%m-%d")
    df = get_stock_price_from_cache(price_cache, stock_id, start)
    if df is None or len(df) == 0:
        return None
    return round(float(df.iloc[-1]["close"]), 2)


def main() -> int:
    print("=== 趨勢大戶標的追蹤 ===")
    price_cache = load_price_cache()
    if price_cache is not None:
        print(f"  price_cache 已載入：{price_cache['stock_id'].nunique()} 支")

    source = load_json(SOURCE_PATH)
    track = load_json(TRACK_PATH)

    source_results = source.get("results", [])
    active_list: list[dict] = track.get("active", [])
    expired_list: list[dict] = track.get("expired", [])
    today_obj = date.fromisoformat(TODAY)

    active_ids = {s["stock_id"] for s in active_list}
    source_map = {s["stock_id"]: s for s in source_results}

    print(f"趨勢大戶本週入選：{len(source_results)} 支　現有追蹤：{len(active_list)} 支")

    # ── 新標的入池 ─────────────────────────────────────────
    new_stocks = [s for s in source_results if s["stock_id"] not in active_ids]
    print(f"新進標的：{len(new_stocks)} 支")

    for s in new_stocks:
        sid = s["stock_id"]
        expire_obj = today_obj + timedelta(days=OBSERVE_CALENDAR_DAYS)
        entry_price = float(s.get("close") or s.get("entry_close") or 0)
        active_list.append({
            "stock_id": sid,
            "name": s.get("name", ""),
            "industry": s.get("industry", ""),
            "entry_date": TODAY,
            "expire_date": expire_obj.isoformat(),
            "days_remaining": OBSERVE_CALENDAR_DAYS,
            "entry_price": entry_price,
            "current_price": entry_price,
            "pnl_pct": 0.0,
            "vol_20d_avg": s.get("vol_20d_avg"),
            "big_pct_1000": s.get("big_pct_1000"),
            "big_pct_400": s.get("big_pct_400"),
            "tags": s.get("tags", []),
            "pinned": False,
        })
        print(f"  ✅ {sid} {s.get('name', '')} 入池，到期 {expire_obj}")

    # ── 更新現價 & P&L & 剩餘天數 ────────────────────────
    print(f"\n更新 active 現價（{len(active_list)} 支）...")
    still_active: list[dict] = []

    for item in active_list:
        sid = item["stock_id"]
        expire_obj = date.fromisoformat(item["expire_date"])
        days_remain = calendar_days_remaining(expire_obj, today_obj)
        item["days_remaining"] = days_remain

        # 同步本週仍入選的籌碼欄位
        if sid in source_map:
            s = source_map[sid]
            item["vol_20d_avg"] = s.get("vol_20d_avg", item.get("vol_20d_avg"))
            item["big_pct_1000"] = s.get("big_pct_1000", item.get("big_pct_1000"))
            item["big_pct_400"] = s.get("big_pct_400", item.get("big_pct_400"))
            item["tags"] = s.get("tags", item.get("tags", []))

        price = fetch_current_price(sid, price_cache)
        if price:
            item["current_price"] = price
            ep = item.get("entry_price") or price
            item["pnl_pct"] = round((price - ep) / ep * 100, 2) if ep else 0.0

        # 釘選：永遠留在 active；未釘選且到期 → 移入 expired
        if days_remain <= 0 and not item.get("pinned"):
            remove_date = (today_obj + timedelta(days=HISTORY_KEEP_CALENDAR_DAYS)).isoformat()
            expired_list.append({**item, "exit_date": TODAY, "remove_date": remove_date})
            print(f"  📦 {sid} 到期 → 移入歷史")
        else:
            still_active.append(item)

    # ── 更新歷史現價 ──────────────────────────────────────
    if expired_list:
        print(f"更新 expired 現價（{len(expired_list)} 支）...")
        for item in expired_list:
            price = fetch_current_price(item["stock_id"], price_cache)
            if price:
                item["current_price"] = price
                ep = item.get("entry_price") or price
                item["pnl_pct"] = round((price - ep) / ep * 100, 2) if ep else 0.0

    # ── 清除過期歷史（釘選不清除）─────────────────────────
    expired_list = [
        e for e in expired_list
        if e.get("pinned") or date.fromisoformat(e["remove_date"]) >= today_obj
    ]

    save_json(TRACK_PATH, {
        "last_updated": TODAY,
        "active": still_active,
        "expired": expired_list,
    })
    print(f"\n✅ big_holder_trend_track.json　active={len(still_active)}　expired={len(expired_list)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
