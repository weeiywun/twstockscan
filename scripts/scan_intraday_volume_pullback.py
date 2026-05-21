#!/usr/bin/env python3
"""
10:00 盤中量增回測預警

只掃 volume_pullback.json 的 active 名單，避免全市場即時請求。
條件：
- 盤中累積量 >= 10日均量 * 0.45
- 盤中累積量 >= 200 張
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from realtime_quote import fetch_twse_mis_quotes

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
POOL_PATH = os.path.join(DATA_DIR, "volume_pullback.json")
STOCK_LIST_PATH = os.path.join(DATA_DIR, "stock_list_cache.json")
OUTPUT_PATH = os.path.join(DATA_DIR, "intraday_volume_pullback.json")

TW_TZ = timezone(timedelta(hours=8))
TODAY = datetime.now(TW_TZ).strftime("%Y-%m-%d")
SCAN_TIME = "10:00"
INTRADAY_VOL_RATIO_MIN = 0.45
INTRADAY_VOL_MIN_LOTS = 200


def now_tw() -> str:
    return datetime.now(TW_TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def load_pool() -> list[dict]:
    if not os.path.exists(POOL_PATH):
        return []
    with open(POOL_PATH, encoding="utf-8") as f:
        data = json.load(f)
    stock_meta = load_stock_meta()
    rows = [
        row for row in data.get("active", [])
        if row.get("status") in {"pullback", "reentry", "watch", "ignition"}
    ]
    for row in rows:
        meta = stock_meta.get(str(row.get("stock_id")))
        if not meta:
            continue
        row["market"] = row.get("market") or meta.get("market", "")
        row["name"] = row.get("name") or meta.get("name", "")
        row["industry"] = row.get("industry") or meta.get("industry", "")
    return rows


def load_stock_meta() -> dict[str, dict]:
    if not os.path.exists(STOCK_LIST_PATH):
        return {}
    with open(STOCK_LIST_PATH, encoding="utf-8") as f:
        rows = json.load(f)
    return {str(row.get("stock_id")): row for row in rows if row.get("stock_id")}


def main() -> int:
    print("=== 10:00 盤中量增回測預警 ===")
    pool = load_pool()
    print(f"觀察池：{len(pool)} 檔")
    if not pool:
        write_output([], [], "empty_pool")
        return 0

    quotes = fetch_twse_mis_quotes(pool)
    print(f"取得即時報價：{len(quotes)} 檔")

    alerts, skipped = [], []
    for item in pool:
        sid = item["stock_id"]
        q = quotes.get(sid)
        vol10 = item.get("vol_10d_avg")
        if not q or not vol10:
            skipped.append({**item, "skip_reason": "no_quote_or_vol10"})
            continue
        intraday_vol = q.get("volume_lots") or 0
        trigger_vol = max(INTRADAY_VOL_MIN_LOTS, vol10 * INTRADAY_VOL_RATIO_MIN)
        intraday_ratio = intraday_vol / vol10 if vol10 else None
        row = {
            **item,
            "intraday_date": TODAY,
            "intraday_time": q.get("time") or SCAN_TIME,
            "intraday_close": q.get("close"),
            "intraday_high": q.get("high"),
            "intraday_low": q.get("low"),
            "intraday_volume_lots": intraday_vol,
            "intraday_vol_ratio_to_10d": round(intraday_ratio, 2) if intraday_ratio is not None else None,
            "intraday_trigger_volume": int(round(trigger_vol, 0)),
            "yesterday_close": q.get("yesterday_close"),
            "quote_source": "TWSE_MIS",
        }
        if intraday_vol >= trigger_vol:
            alerts.append(row)
        else:
            skipped.append({**row, "skip_reason": "volume_below_threshold"})

    alerts.sort(key=lambda r: (r.get("intraday_vol_ratio_to_10d") or 0), reverse=True)
    write_output(alerts, skipped, "ok")
    for row in alerts[:10]:
        print(f"  {row['stock_id']} {row['name']} intraday={row['intraday_vol_ratio_to_10d']} vol={row['intraday_volume_lots']}")
    return 0


def write_output(alerts: list[dict], skipped: list[dict], status: str) -> None:
    output = {
        "strategy_id": "intraday_volume_pullback",
        "updated": now_tw(),
        "scan_time": SCAN_TIME,
        "source": "TWSE_MIS",
        "status": status,
        "rule": {
            "intraday_volume_vs_10d_avg": INTRADAY_VOL_RATIO_MIN,
            "min_volume_lots": INTRADAY_VOL_MIN_LOTS,
        },
        "results": alerts,
        "skipped": skipped[:50],
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"完成：alerts={len(alerts)} -> {OUTPUT_PATH}")


if __name__ == "__main__":
    raise SystemExit(main())
