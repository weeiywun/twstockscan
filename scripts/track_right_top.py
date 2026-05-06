#!/usr/bin/env python3
"""
右上角策略標的追蹤
- 讀取 right_top.json 新訊號 → 加入追蹤池（entry_price = 訊號當週收盤）
- 每日更新現價 / P&L / 剩餘天數
- 到期（10 個交易日）移入歷史，未釘選保留 5 個交易日
"""

import json
import os
import time
from datetime import date, datetime, timedelta, timezone

from finmind_client import fetch_stock_price, load_price_cache, get_stock_price_from_cache

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(SCRIPT_DIR, "..", "data")
RT_PATH    = os.path.join(DATA_DIR, "right_top.json")
TRACK_PATH = os.path.join(DATA_DIR, "right_top_track.json")

TW_TZ = timezone(timedelta(hours=8))
TODAY = datetime.now(TW_TZ).strftime("%Y-%m-%d")

OBSERVE_TRADING_DAYS = 10
HISTORY_KEEP_TRADING_DAYS = 5


def add_trading_days(start: date, n: int) -> date:
    d, added = start, 0
    while added < n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d


def trading_days_remaining(expire: date, today: date) -> int:
    if today > expire:
        return 0
    d, count = today, 0
    while d <= expire:
        if d.weekday() < 5:
            count += 1
        d += timedelta(days=1)
    return count


def keep_history_item(item: dict, today: date) -> bool:
    if item.get("pinned"):
        return True
    remove_date = item.get("remove_date")
    return bool(remove_date) and date.fromisoformat(remove_date) >= today


def normalize_history_retention(items: list[dict], today: date) -> None:
    keep_until = add_trading_days(today, HISTORY_KEEP_TRADING_DAYS).isoformat()
    for item in items:
        if item.get("pinned"):
            continue
        remove_date = item.get("remove_date")
        if not remove_date or date.fromisoformat(remove_date) > date.fromisoformat(keep_until):
            item["remove_date"] = keep_until


def fetch_close(stock_id: str, token: str, price_cache=None) -> float | None:
    start = (datetime.now(TW_TZ) - timedelta(days=5)).strftime("%Y-%m-%d")
    if price_cache is not None:
        df = get_stock_price_from_cache(price_cache, stock_id, start)
        if df is not None and len(df) > 0:
            return round(float(df.iloc[-1]["close"]), 2)
    df = fetch_stock_price(stock_id, start, TODAY, token)
    if df is None or len(df) == 0:
        return None
    return round(float(df.iloc[-1]["close"]), 2)


def load_json(path: str) -> dict:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_json(path: str, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    print("=== 右上角標的追蹤 ===")
    finmind_token = os.environ.get("FINMIND_TOKEN", "")
    if not finmind_token:
        print("⚠️  FINMIND_TOKEN 未設定，無法更新現價")

    price_cache = load_price_cache()
    if price_cache is not None:
        print(f"  price_cache.parquet 已載入：{price_cache['stock_id'].nunique()} 支")

    rt_data    = load_json(RT_PATH)
    track_data = load_json(TRACK_PATH)

    rt_results   = rt_data.get("results", [])
    active_list  = track_data.get("active", [])
    expired_list = track_data.get("expired", [])
    today_obj    = date.fromisoformat(TODAY)

    active_ids = {s["stock_id"] for s in active_list}

    print(f"右上角本週訊號：{len(rt_results)} 支　現有追蹤：{len(active_list)} 支")

    # ── 新標的入池 ────────────────────────────────────
    new_stocks = [s for s in rt_results if s["stock_id"] not in active_ids]
    print(f"新進標的：{len(new_stocks)} 支")

    for s in new_stocks:
        sid        = s["stock_id"]
        expire_obj = add_trading_days(today_obj, OBSERVE_TRADING_DAYS)
        entry = {
            "stock_id":       sid,
            "name":           s.get("name", ""),
            "industry":       s.get("industry", ""),
            "market":         s.get("market", ""),
            "trigger_date":   TODAY,
            "week_date":      s.get("week_date", ""),
            "expire_date":    expire_obj.isoformat(),
            "days_remaining": OBSERVE_TRADING_DAYS,
            "entry_price":    s.get("close", 0),
            "current_price":  s.get("close", 0),
            "pnl_pct":        0.0,
            "vol_ratio":      s.get("vol_ratio", 0),
            "high_10w":       s.get("high_10w", 0),
            "pinned":         False,
        }
        active_list.append(entry)
        print(f"  ✅ {sid} {s.get('name','')} 入池，到期 {expire_obj}")

    # ── 每日更新現價 & P&L & 剩餘天數 ───────────────
    print(f"\n更新 active 現價（{len(active_list)} 支）...")
    still_active, newly_expired = [], []

    for item in active_list:
        sid = item["stock_id"]

        expire_obj  = date.fromisoformat(item["expire_date"])
        days_remain = trading_days_remaining(expire_obj, today_obj)
        item["days_remaining"] = days_remain

        if finmind_token:
            price = fetch_close(sid, finmind_token, price_cache)
            if price:
                item["current_price"] = price
                ep = item.get("entry_price") or price
                item["pnl_pct"] = round((price - ep) / ep * 100, 2) if ep else 0.0
            if price_cache is None:
                time.sleep(0.35)

        if days_remain <= 0:
            remove_date = add_trading_days(today_obj, HISTORY_KEEP_TRADING_DAYS).isoformat()
            expired_list.append({
                "stock_id":       item["stock_id"],
                "name":           item["name"],
                "industry":       item.get("industry", ""),
                "market":         item.get("market", ""),
                "trigger_date":   item["trigger_date"],
                "week_date":      item.get("week_date", ""),
                "entry_price":    item["entry_price"],
                "current_price":  item["current_price"],
                "pnl_pct":        item["pnl_pct"],
                "vol_ratio":      item.get("vol_ratio", 0),
                "high_10w":       item.get("high_10w", 0),
                "remove_date":    remove_date,
                "pinned":         bool(item.get("pinned", False)),
            })
            print(f"  📦 {sid} 到期 → 移入歷史")
        else:
            still_active.append(item)

    normalize_history_retention(expired_list, today_obj)

    # ── 清除未釘選且超過保留期限的歷史 ─────────────────
    expired_list = [
        e for e in expired_list
        if keep_history_item(e, today_obj)
    ]

    # ── 歷史現價也更新 ────────────────────────────────
    if finmind_token and expired_list:
        print(f"更新 expired 現價（{len(expired_list)} 支）...")
        for item in expired_list:
            price = fetch_close(item["stock_id"], finmind_token, price_cache)
            if price:
                item["current_price"] = price
                ep = item.get("entry_price") or price
                item["pnl_pct"] = round((price - ep) / ep * 100, 2) if ep else 0.0
            if price_cache is None:
                time.sleep(0.35)

    save_json(TRACK_PATH, {
        "last_updated": TODAY,
        "active":       still_active,
        "expired":      expired_list,
    })
    print(f"\n✅ right_top_track.json 已更新　active={len(still_active)}　expired={len(expired_list)}")


if __name__ == "__main__":
    main()
