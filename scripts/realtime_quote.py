#!/usr/bin/env python3
"""
Small TWSE MIS quote client for intraday candidate scans.

The endpoint returns TWSE/TPEX realtime quote snapshots. We only query a small
candidate pool, not the full market.
"""

from __future__ import annotations

import time
from typing import Iterable

import requests

TWSE_MIS_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"


def guess_market(stock_id: str) -> str:
    n = int(str(stock_id)[:4])
    if 3000 <= n <= 9999:
        return "otc"
    return "tse"


def _market_prefix(market: str | None, stock_id: str) -> str:
    m = (market or "").strip().upper()
    if m in {"TPEX", "OTC"}:
        return "otc"
    if m == "TWSE":
        return "tse"
    return guess_market(stock_id)


def _num(value) -> float | None:
    if value in (None, "", "-", "--"):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def fetch_twse_mis_quotes(candidates: Iterable[dict], chunk_size: int = 40) -> dict[str, dict]:
    items = list(candidates)
    quotes: dict[str, dict] = {}
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://mis.twse.com.tw/stock/index.jsp",
    })

    for i in range(0, len(items), chunk_size):
        chunk = items[i:i + chunk_size]
        ex_ch = "|".join(
            f"{_market_prefix(item.get('market'), item['stock_id'])}_{item['stock_id']}.tw"
            for item in chunk
        )
        if not ex_ch:
            continue
        params = {"ex_ch": ex_ch, "json": "1", "delay": "0", "_": str(int(time.time() * 1000))}
        try:
            resp = session.get(TWSE_MIS_URL, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            print(f"[realtime] TWSE MIS fetch failed: {exc}")
            continue

        for row in data.get("msgArray", []):
            sid = str(row.get("c") or "").strip()
            if not sid:
                continue
            close = _num(row.get("z"))
            if close is None:
                close = _num(row.get("pz"))
            quote = {
                "stock_id": sid,
                "name": row.get("n", ""),
                "market": "TWSE" if row.get("ex") == "tse" else "TPEX",
                "date": row.get("d", ""),
                "time": row.get("t", ""),
                "open": _num(row.get("o")),
                "high": _num(row.get("h")),
                "low": _num(row.get("l")),
                "close": close,
                "yesterday_close": _num(row.get("y")),
                "volume_lots": int(_num(row.get("v")) or 0),
            }
            quotes[sid] = quote
    return quotes
