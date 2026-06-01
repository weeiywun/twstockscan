#!/usr/bin/env python3
"""Apply pattern_score as the only score field on frontend JSON files."""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from typing import Any

from finmind_client import get_stock_price_from_cache, load_price_cache
import pattern_detect

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
LOOKBACK_DAYS = 220

TARGETS = [
    ("chips_big_holder.json", ["results"]),
    ("big_holder_trend.json", ["results"]),
    ("right_top.json", ["results"]),
    ("right_top_track.json", ["active", "expired"]),
    ("volume_signal.json", ["results"]),
    ("volume_pullback.json", ["active", "failed", "history"]),
    ("momentum_candidates.json", ["focus_results", "results"]),
    ("ai_analysis.json", ["active", "expired"]),
    ("big_holder_trend_track.json", ["active", "expired"]),
    ("performance.json", ["positions"]),
]

LEGACY_SCORE_FIELDS = {
    "unified_score",
    "unified_score_grade",
    "score_breakdown",
    "legacy_score",
    "context_unified_score",
    "context_score_breakdown",
    "context_score",
    "score_parts",
    "priority_level",
    "priority_rank",
    "priority_reason",
    "quant_scores",
    "quality_score",
    "tag_score",
}


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


def stock_id_of(row: dict[str, Any]) -> str:
    return str(row.get("stock_id") or row.get("ticker") or "").strip()


def source_count(row: dict[str, Any], fallback: str) -> int:
    sources = row.get("sources")
    if isinstance(sources, list) and sources:
        return len(sources)
    return 1 if fallback else 0


def clean_legacy_fields(row: dict[str, Any]) -> None:
    for key in LEGACY_SCORE_FIELDS:
        row.pop(key, None)


def apply_pattern(row: dict[str, Any], *, cache: Any, start_date: str, source: str) -> bool:
    sid = stock_id_of(row)
    if not sid:
        return False

    clean_legacy_fields(row)
    result = None
    if cache is not None:
        df = get_stock_price_from_cache(cache, sid, start_date)
        if df is not None:
            tags = set(row.get("tags", []) or row.get("source_tags", []) or [])
            sources = set(row.get("sources", []) or [source])
            result = pattern_detect.analyze(
                df,
                stock_id=sid,
                track_pnl_pct=row.get("pnl_pct") or row.get("since_entry_pct"),
                big_trend_up=bool({"chips", "big_holder_trend"} & sources),
                inst_buying=any("外資" in str(tag) or "投信" in str(tag) for tag in tags),
                source_count=source_count(row, source),
            )

    if result:
        row.update(result.as_dict())
    else:
        row.update({
            "pattern_state": "先觀察",
            "pattern_score": 0.0,
            "pattern_subs": {},
            "pattern_tags": [],
            "patterns": [],
            "key_level": None,
            "invalidation": None,
            "pattern_confidence": 1.0,
        })

    row["score"] = row["pattern_score"]
    row["score_model"] = "pattern_score_only_v1"
    return True


def apply_file(filename: str, keys: list[str], cache: Any, start_date: str) -> int:
    data = load_json(filename)
    if not data:
        return 0

    source = filename.removesuffix(".json")
    count = 0
    seen: set[str] = set()
    for key in keys:
        rows = data.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            identity = f"{key}:{stock_id_of(row)}"
            if filename == "momentum_candidates.json" and identity in seen:
                clean_legacy_fields(row)
                continue
            if apply_pattern(row, cache=cache, start_date=start_date, source=source):
                count += 1
                seen.add(identity)

    if count:
        data.pop("unified_score_model", None)
        data["score_model"] = "pattern_score_only_v1"
        save_json(filename, data)
    return count


def main() -> int:
    cache = load_price_cache()
    start_date = (date.today() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    total = 0
    for filename, keys in TARGETS:
        count = apply_file(filename, keys, cache, start_date)
        total += count
        print(f"[pattern-score] {filename}: {count}")
    print(f"[pattern-score] total rows: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
