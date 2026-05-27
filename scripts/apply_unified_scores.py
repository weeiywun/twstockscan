#!/usr/bin/env python3
"""Apply the shared scoring model to strategy output JSON files."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from unified_scoring import WEIGHTS, clamp, compute_unified_score, grade, source_multiplier

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


def load_feature_map() -> dict[str, dict[str, Any]]:
    data = load_json("candidate_features.json")
    return {
        str(row.get("stock_id") or ""): row
        for row in data.get("results", []) or []
        if isinstance(row, dict) and row.get("stock_id")
    }


def score_row(
    row: dict[str, Any],
    *,
    source: str,
    theme_index: dict[str, dict[str, Any]],
    feature_map: dict[str, dict[str, Any]],
) -> None:
    sid = stock_id_of(row)
    feature = feature_map.get(sid) or {}
    enriched = {**feature, **row}
    enriched["sources"] = sorted(set((feature.get("sources") or []) + (row.get("sources") or []) + [source]))
    enriched["tags"] = sorted(set((feature.get("tags") or []) + (row.get("tags") or []) + (row.get("source_tags") or [])))
    if feature.get("metrics") or row.get("metrics"):
        enriched["metrics"] = {**(feature.get("metrics") or {}), **(row.get("metrics") or {})}

    detail = compute_unified_score(enriched, fallback_source=source, theme_index=theme_index)
    if "legacy_score" not in row and row.get("score") is not None:
        row["legacy_score"] = row.get("score")
    row["unified_score"] = detail["total"]
    row["unified_score_grade"] = detail["grade"]
    row["score_breakdown"] = detail
    row["score"] = detail["total"]


def apply_to_rows(
    data: dict[str, Any],
    keys: list[str],
    source: str,
    theme_index: dict[str, dict[str, Any]],
    feature_map: dict[str, dict[str, Any]],
    row_refs: list[dict[str, Any]],
) -> int:
    count = 0
    for key in keys:
        rows = data.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            score_row(row, source=source, theme_index=theme_index, feature_map=feature_map)
            row_refs.append(row)
            count += 1
    if count:
        data["unified_score_model"] = {
            "version": "unified_score_v1",
            "applied_at": now_tw(),
        }
    return count


def apply_file(
    filename: str,
    keys: list[str],
    source: str,
    theme_index: dict[str, dict[str, Any]],
    feature_map: dict[str, dict[str, Any]],
    row_refs: list[dict[str, Any]],
    datasets: list[tuple[str, dict[str, Any]]],
) -> int:
    data = load_json(filename)
    if not data:
        return 0
    count = apply_to_rows(data, keys, source, theme_index, feature_map, row_refs)
    if count:
        datasets.append((filename, data))
    return count


def enrich_performance(
    theme_index: dict[str, dict[str, Any]],
    feature_map: dict[str, dict[str, Any]],
    row_refs: list[dict[str, Any]],
    datasets: list[tuple[str, dict[str, Any]]],
) -> int:
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
        score_row(row, source="holding", theme_index=theme_index, feature_map=feature_map)
        row_refs.append(row)
        count += 1
    if count:
        data["unified_score_model"] = {
            "version": "unified_score_v1",
            "applied_at": now_tw(),
        }
        datasets.append(("performance.json", data))
    return count


def stock_id_of(row: dict[str, Any]) -> str:
    return str(row.get("stock_id") or row.get("ticker") or "").strip()


def build_stock_score_profiles(row_refs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    for row in row_refs:
        sid = stock_id_of(row)
        detail = row.get("score_breakdown") or {}
        components = detail.get("components") or {}
        if not sid or not components:
            continue
        profile = profiles.setdefault(sid, {
            "components": {key: 0.0 for key in WEIGHTS},
            "sources": set(),
        })
        for key in WEIGHTS:
            profile["components"][key] = max(float(profile["components"].get(key) or 0), float(components.get(key) or 0))
        for source in detail.get("sources") or []:
            profile["sources"].add(str(source))

    output: dict[str, dict[str, Any]] = {}
    for sid, profile in profiles.items():
        components = {key: round(float(value or 0), 1) for key, value in profile["components"].items()}
        sources = sorted(profile["sources"])
        multiplier = source_multiplier(len(sources))
        base = sum(components.get(key, 0.0) * float(WEIGHTS.get(key, 0.0)) for key in WEIGHTS)
        total = round(clamp(base * multiplier), 1)
        output[sid] = {
            "version": "unified_score_v2_momentum_first_stock_level",
            "total": total,
            "grade": grade(total),
            "base": round(base, 1),
            "components": components,
            "source_count": len(sources),
            "source_multiplier": multiplier,
            "sources": sources,
            "aggregation": "max_component_by_stock",
        }
    return output


def apply_stock_score_profiles(row_refs: list[dict[str, Any]], profiles: dict[str, dict[str, Any]]) -> int:
    count = 0
    for row in row_refs:
        sid = stock_id_of(row)
        profile = profiles.get(sid)
        if not profile:
            continue
        row["context_unified_score"] = row.get("unified_score")
        row["context_score_breakdown"] = row.get("score_breakdown")
        row["unified_score"] = profile["total"]
        row["unified_score_grade"] = profile["grade"]
        row["score_breakdown"] = profile
        row["score"] = profile["total"]
        count += 1
    return count


def main() -> int:
    theme_index = build_theme_index()
    feature_map = load_feature_map()
    row_refs: list[dict[str, Any]] = []
    datasets: list[tuple[str, dict[str, Any]]] = []
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
        count = apply_file(filename, keys, source, theme_index, feature_map, row_refs, datasets)
        total += count
        print(f"[unified-score] {filename}: {count}")
    perf_count = enrich_performance(theme_index, feature_map, row_refs, datasets)
    total += perf_count
    print(f"[unified-score] performance.json: {perf_count}")
    profiles = build_stock_score_profiles(row_refs)
    stock_count = apply_stock_score_profiles(row_refs, profiles)
    print(f"[unified-score] stock-level profiles: {len(profiles)} stocks / {stock_count} rows")
    for filename, data in datasets:
        save_json(filename, data)
    print(f"[unified-score] total rows: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
