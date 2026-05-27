#!/usr/bin/env python3
"""Apply the shared scoring model to strategy output JSON files."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from unified_scoring import apply_unified_score

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
TW_TZ = timezone(timedelta(hours=8))


def load_json(filename: str) -> dict[str, Any]:
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(filename: str, data: dict[str, Any]) -> None:
    path = os.path.join(DATA_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def now_tw() -> str:
    return datetime.now(TW_TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def build_theme_index() -> dict[str, dict[str, Any]]:
    data = load_json("theme_heat.json")
    index: dict[str, dict[str, Any]] = {}

    def put(stock: dict[str, Any], theme_name: str, score: float) -> None:
        sid = str(stock.get("stock_id") or stock.get("ticker") or "")
        if not sid:
            return
        current = index.get(sid)
        if current and (current.get("score") or 0) >= score:
            return
        index[sid] = {"theme": theme_name, "score": round(score, 1)}

    for theme in data.get("themes", []) or []:
        theme_name = theme.get("theme") or theme.get("name") or theme.get("industry") or "主線"
        theme_base = float(theme.get("score") or theme.get("market_score") or 0)
        for key in ("leaders", "market_leaders", "representatives", "stocks"):
            for idx, stock in enumerate(theme.get(key, []) or []):
                raw = stock.get("theme_score") or stock.get("leader_score") or stock.get("score") or theme_base
                rank_penalty = idx * 4
                put(stock, theme_name, max(0.0, float(raw or 0) - rank_penalty))
    for stock in data.get("leaders", []) or data.get("top_stocks", []) or []:
        raw = stock.get("theme_score") or stock.get("score") or 0
        put(stock, stock.get("theme") or "主線", float(raw or 0))
    return index


def apply_to_rows(data: dict[str, Any], keys: list[str], source: str, theme_index: dict[str, dict[str, Any]]) -> int:
    count = 0
    for key in keys:
        rows = data.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            apply_unified_score(row, fallback_source=source, theme_index=theme_index)
            count += 1
    if count:
        data["unified_score_model"] = {
            "version": "unified_score_v1",
            "applied_at": now_tw(),
        }
    return count


def apply_file(filename: str, keys: list[str], source: str, theme_index: dict[str, dict[str, Any]]) -> int:
    data = load_json(filename)
    if not data:
        return 0
    count = apply_to_rows(data, keys, source, theme_index)
    if count:
        save_json(filename, data)
    return count


def enrich_performance(theme_index: dict[str, dict[str, Any]]) -> int:
    data = load_json("performance.json")
    if not data:
        return 0
    current_prices = (load_json("current_prices.json") or {}).get("prices", {})
    count = 0
    for row in data.get("positions", []) or []:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("stock_id") or "")
        if current_prices.get(sid) is not None and row.get("current_price") is None:
            row["current_price"] = current_prices.get(sid)
        apply_unified_score(row, fallback_source="holding", theme_index=theme_index)
        count += 1
    if count:
        data["unified_score_model"] = {
            "version": "unified_score_v1",
            "applied_at": now_tw(),
        }
        save_json("performance.json", data)
    return count


def main() -> int:
    theme_index = build_theme_index()
    targets = [
        ("ai_analysis.json", ["active", "expired"], "stock_analysis"),
        ("chips_big_holder.json", ["results"], "chips"),
        ("intraday_volume_pullback.json", ["results", "skipped"], "intraday_volume_pullback"),
        ("right_top.json", ["results"], "right_top"),
        ("right_top_track.json", ["active", "expired"], "right_top_track"),
        ("trust_momentum.json", ["results", "trust_results", "foreign_results", "confluence_results"], "institutional_momentum"),
        ("vcp.json", ["results", "potential_results"], "vcp"),
        ("volume_breakout.json", ["results"], "volume_breakout"),
        ("volume_signal.json", ["results"], "volume_signal"),
        ("volume_pullback.json", ["active", "failed", "history"], "volume_pullback"),
        ("momentum_pullback.json", ["results"], "momentum_pullback"),
        ("momentum_candidates.json", ["focus_results", "results"], "momentum_candidates"),
    ]
    total = 0
    for filename, keys, source in targets:
        count = apply_file(filename, keys, source, theme_index)
        total += count
        print(f"[unified-score] {filename}: {count}")
    perf_count = enrich_performance(theme_index)
    total += perf_count
    print(f"[unified-score] performance.json: {perf_count}")
    print(f"[unified-score] total rows: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
