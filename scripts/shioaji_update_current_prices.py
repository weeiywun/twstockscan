#!/usr/bin/env python3
"""Update frontend stock prices from Shioaji snapshots.

This script is intentionally read-only against the broker account:
it logs in, reads stock contracts, calls snapshots, and writes only
data/current_prices.json. It does not import or call any order APIs.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

TW_TZ = timezone(timedelta(hours=8))
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
OUTPUT_PATH = DATA_DIR / "current_prices.json"

DEFAULT_BATCH_SIZE = 100
DEFAULT_BATCH_SLEEP = 0.7

SOURCE_FILES: list[tuple[str, tuple[str, ...]]] = [
    ("momentum_candidates.json", ("focus_results", "results")),
    ("chips_big_holder.json", ("results",)),
    ("big_holder_trend.json", ("results",)),
    ("big_holder_trend_track.json", ("active", "expired", "history")),
    ("right_top.json", ("results",)),
    ("right_top_track.json", ("active", "expired", "history")),
    ("ai_analysis.json", ("active", "expired", "history")),
    ("volume_signal.json", ("results",)),
    ("volume_pullback.json", ("active", "failed", "history")),
    ("performance.json", ("positions",)),
]


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def stock_id_of(row: dict[str, Any]) -> str | None:
    raw = row.get("stock_id") or row.get("ticker") or row.get("code")
    if raw is None:
        return None
    sid = str(raw).strip()
    return sid.zfill(4) if sid.isdigit() else sid


def collect_stock_ids() -> list[str]:
    ids: set[str] = set()
    for filename, keys in SOURCE_FILES:
        data = load_json(DATA_DIR / filename)
        for key in keys:
            rows = data.get(key)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                sid = stock_id_of(row)
                if sid and sid.isdigit() and len(sid) == 4:
                    ids.add(sid)
    return sorted(ids)


def chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def snapshot_price(snapshot: Any) -> float | None:
    for attr in ("close", "buy_price", "sell_price"):
        value = getattr(snapshot, attr, None)
        try:
            if value is not None and float(value) > 0:
                return round(float(value), 2)
        except (TypeError, ValueError):
            continue
    return None


def usage_line(api: Any) -> str:
    try:
        usage = api.usage()
        used = getattr(usage, "bytes", None)
        limit = getattr(usage, "limit_bytes", None)
        remaining = getattr(usage, "remaining_bytes", None)
        connections = getattr(usage, "connections", None)
        if used is None or limit is None or remaining is None:
            return ""
        used_mb = used / 1024 / 1024
        limit_mb = limit / 1024 / 1024
        remain_mb = remaining / 1024 / 1024
        suffix = f" connections={connections}" if connections is not None else ""
        return f"usage={used_mb:.1f}/{limit_mb:.0f}MB remaining={remain_mb:.1f}MB{suffix}"
    except Exception:
        return ""


def build_contracts(api: Any, ids: list[str]) -> tuple[list[Any], list[str]]:
    contracts = []
    missing = []
    stocks = api.Contracts.Stocks
    for sid in ids:
        contract = None
        try:
            contract = stocks[sid]
        except Exception:
            contract = None
        if contract is None:
            missing.append(sid)
        else:
            contracts.append(contract)
    return contracts, missing


def update_prices(*, batch_size: int, batch_sleep: float, dry_run: bool) -> dict[str, Any]:
    ids = collect_stock_ids()
    if not ids:
        raise RuntimeError("No stock ids found from frontend data files.")

    now = datetime.now(TW_TZ)
    print(f"[shioaji-prices] collected {len(ids)} stock ids")
    if dry_run:
        return {
            "date": now.strftime("%Y-%m-%d"),
            "source": "shioaji_snapshots_dry_run",
            "updated": now.isoformat(),
            "prices": {},
            "count": 0,
            "requested": len(ids),
            "missing": ids,
        }

    import shioaji as sj

    api_key = os.environ.get("SHIOAJI_API_KEY", "").strip()
    secret_key = os.environ.get("SHIOAJI_SECRET_KEY", "").strip()
    if not api_key or not secret_key:
        raise RuntimeError("Missing SHIOAJI_API_KEY or SHIOAJI_SECRET_KEY.")

    api = sj.Shioaji(simulation=False)
    api.login(api_key=api_key, secret_key=secret_key)
    print(f"[shioaji-prices] login ok {usage_line(api)}")

    contracts, missing_contracts = build_contracts(api, ids)
    prices: dict[str, float] = {}

    for index, batch in enumerate(chunks(contracts, batch_size), start=1):
        snapshots = api.snapshots(batch)
        for snap in snapshots:
            sid = str(getattr(snap, "code", "")).zfill(4)
            price = snapshot_price(snap)
            if sid and price is not None:
                prices[sid] = price
        print(f"[shioaji-prices] batch {index}: {len(snapshots)} snapshots")
        if index * batch_size < len(contracts):
            time.sleep(batch_sleep)

    missing_prices = sorted(set(ids) - set(prices))
    print(
        f"[shioaji-prices] prices {len(prices)}/{len(ids)} "
        f"missing_contracts={len(missing_contracts)} missing_prices={len(missing_prices)}"
    )
    line = usage_line(api)
    if line:
        print(f"[shioaji-prices] {line}")

    return {
        "date": now.strftime("%Y-%m-%d"),
        "source": "shioaji_snapshots",
        "updated": now.isoformat(),
        "prices": dict(sorted(prices.items())),
        "count": len(prices),
        "requested": len(ids),
        "missing": missing_prices,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--batch-sleep", type=float, default=DEFAULT_BATCH_SLEEP)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    data = update_prices(
        batch_size=max(1, args.batch_size),
        batch_sleep=max(0.0, args.batch_sleep),
        dry_run=args.dry_run,
    )
    if args.dry_run:
        print(json.dumps({k: data[k] for k in ("source", "requested", "count")}, ensure_ascii=False))
        return 0

    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"[shioaji-prices] wrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
