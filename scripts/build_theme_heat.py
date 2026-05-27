#!/usr/bin/env python3
"""
Build a lightweight market theme heat map from existing scan outputs.

This deliberately avoids extra market-data requests. It reads the strategy JSON
files already produced by the repo, maps stocks into manually curated trading
themes, and emits data/theme_heat.json for the frontend.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")

CONFIG_PATH = os.path.join(DATA_DIR, "theme_config.json")
OUTPUT_PATH = os.path.join(DATA_DIR, "theme_heat.json")

SOURCE_FILES = {
    "momentum_candidates": os.path.join(DATA_DIR, "momentum_candidates.json"),
    "momentum_pullback": os.path.join(DATA_DIR, "momentum_pullback.json"),
    "right_top": os.path.join(DATA_DIR, "right_top.json"),
    "chips": os.path.join(DATA_DIR, "chips_big_holder.json"),
    "volume_pullback": os.path.join(DATA_DIR, "volume_pullback.json"),
    "volume_signal": os.path.join(DATA_DIR, "volume_signal.json"),
}

SOURCE_LABELS = {
    "momentum_candidates": "精選候選",
    "momentum_pullback": "動能回測",
    "right_top": "價格突破",
    "chips": "大戶",
    "volume_pullback": "量增回測",
    "volume_signal": "量增",
}

SOURCE_WEIGHTS = {
    "momentum_candidates": 14,
    "momentum_pullback": 16,
    "right_top": 12,
    "chips": 10,
    "volume_pullback": 14,
    "volume_signal": 8,
}

TW_TZ = timezone(timedelta(hours=8))


def load_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def round_or_none(value: Any, digits: int = 2) -> float | None:
    try:
        if value is None:
            return None
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def now_tw() -> str:
    return datetime.now(TW_TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def normalize_row(item: dict[str, Any], source: str) -> dict[str, Any] | None:
    sid = str(item.get("stock_id") or item.get("ticker") or "").strip()
    if not sid:
        return None

    metrics = item.get("metrics") or {}
    tags = item.get("tags") or item.get("source_tags") or []
    sources = item.get("sources") or [source]
    volume_ratio = (
        metrics.get("ignition_vol_ratio")
        or metrics.get("today_vol_ratio")
        or metrics.get("track_vol_ratio")
        or item.get("vol_ratio")
        or item.get("volume_ratio")
        or item.get("ignition_vol_ratio")
    )
    week_chg = metrics.get("week_chg_pct") or item.get("week_chg_pct")
    score = item.get("score") or item.get("quality_score") or item.get("pullback_score")
    source_count = item.get("source_count") or len(sources)

    return {
        "stock_id": sid,
        "name": item.get("name") or "",
        "industry": item.get("industry") or "",
        "market": item.get("market") or "",
        "close": item.get("close") or item.get("current_price"),
        "score": round_or_none(score, 1) or 0,
        "source_count": int(num(source_count, 1)),
        "sources": sorted({str(s) for s in sources if s}),
        "source_labels": sorted({SOURCE_LABELS.get(str(s), str(s)) for s in sources if s}),
        "status": item.get("status_label") or item.get("status") or "",
        "priority_level": item.get("priority_level") or "",
        "tags": tags if isinstance(tags, list) else [],
        "volume_ratio": round_or_none(volume_ratio, 2),
        "week_chg_pct": round_or_none(week_chg, 2),
        "track_pnl_pct": round_or_none(metrics.get("track_pnl_pct") or item.get("pnl_pct"), 2),
    }


def source_rows(name: str, data: dict[str, Any]) -> list[dict[str, Any]]:
    if name == "momentum_candidates":
        return list(data.get("results") or [])
    if name == "momentum_pullback":
        return list(data.get("results") or [])
    if name == "right_top":
        return list(data.get("results") or [])
    if name == "chips":
        return list(data.get("results") or [])
    if name == "volume_pullback":
        return list(data.get("active") or [])
    if name == "volume_signal":
        return list(data.get("results") or [])
    return []


def merge_stock(base: dict[str, Any], row: dict[str, Any], source: str) -> None:
    base["name"] = base["name"] or row.get("name", "")
    base["industry"] = base["industry"] or row.get("industry", "")
    base["market"] = base["market"] or row.get("market", "")
    base["close"] = row.get("close") or base.get("close")
    base["score"] = max(num(base.get("score")), num(row.get("score")))
    base["source_count"] = max(int(num(base.get("source_count"), 1)), int(num(row.get("source_count"), 1)))
    base["sources"] = sorted(set(base.get("sources", [])) | set(row.get("sources", [])) | {source})
    base["source_labels"] = sorted(
        set(base.get("source_labels", []))
        | set(row.get("source_labels", []))
        | {SOURCE_LABELS.get(source, source)}
    )
    base["tags"] = sorted(set(base.get("tags", [])) | set(row.get("tags", [])))

    for key in ("volume_ratio", "week_chg_pct", "track_pnl_pct"):
        current = row.get(key)
        if current is not None:
            existing = base.get(key)
            base[key] = current if existing is None else max(num(existing), num(current))

    statuses = [s for s in [base.get("status"), row.get("status")] if s]
    base["status"] = statuses[0] if statuses else ""
    if row.get("priority_level") == "A" or not base.get("priority_level"):
        base["priority_level"] = row.get("priority_level") or base.get("priority_level", "")


def is_excluded(industry: str, excluded: list[str]) -> bool:
    return any(key and key in industry for key in excluded)


def match_themes(row: dict[str, Any], config: dict[str, Any]) -> list[str]:
    sid = row.get("stock_id", "")
    text = " ".join([
        row.get("name", ""),
        row.get("industry", ""),
        " ".join(row.get("tags", [])),
        row.get("status", ""),
    ])
    matched = []
    for theme in config.get("themes", []):
        if sid in set(theme.get("stock_ids") or []):
            matched.append(theme["name"])
            continue
        if any(key and key in row.get("industry", "") for key in theme.get("industry_keywords", [])):
            matched.append(theme["name"])
            continue
        if any(key and key.lower() in text.lower() for key in theme.get("keywords", [])):
            matched.append(theme["name"])
    return matched[:3]


def broad_theme_names(config: dict[str, Any]) -> set[str]:
    return {theme["name"] for theme in config.get("themes", []) if theme.get("broad")}


def stock_theme_score(row: dict[str, Any]) -> float:
    score = 0.0
    for source in row.get("sources", []):
        score += SOURCE_WEIGHTS.get(source, 4)
    score += min(num(row.get("score")) / 8, 14)
    score += min(num(row.get("source_count")) * 4, 12)
    score += min(num(row.get("volume_ratio")) * 3, 15)
    week_chg = num(row.get("week_chg_pct"))
    if 0 < week_chg <= 18:
        score += min(week_chg / 2, 8)
    if row.get("priority_level") == "A":
        score += 8
    if "momentum_pullback" in row.get("sources", []) or "volume_pullback" in row.get("sources", []):
        score += 6
    return round(score, 1)


def build() -> dict[str, Any]:
    config = load_json(CONFIG_PATH, {"themes": [], "excluded_industries": []})
    stocks: dict[str, dict[str, Any]] = {}
    source_counts: dict[str, int] = {}
    source_dates: list[str] = []

    for source, path in SOURCE_FILES.items():
        data = load_json(path, {})
        source_dates.append(str(data.get("source_date") or data.get("updated") or "")[:10])
        count = 0
        for item in source_rows(source, data):
            row = normalize_row(item, source)
            if not row:
                continue
            sid = row["stock_id"]
            if sid not in stocks:
                stocks[sid] = {
                    "stock_id": sid,
                    "name": "",
                    "industry": "",
                    "market": "",
                    "close": None,
                    "score": 0,
                    "source_count": 1,
                    "sources": [],
                    "source_labels": [],
                    "tags": [],
                    "status": "",
                    "priority_level": "",
                    "volume_ratio": None,
                    "week_chg_pct": None,
                    "track_pnl_pct": None,
                }
            merge_stock(stocks[sid], row, source)
            count += 1
        source_counts[source] = count

    excluded = list(config.get("excluded_industries") or [])
    themes: dict[str, dict[str, Any]] = {}
    broad_themes = broad_theme_names(config)
    excluded_rows = []
    unclassified_rows = []

    for row in stocks.values():
        row["theme_score"] = stock_theme_score(row)
        row["themes"] = match_themes(row, config)
        if not row["themes"] and is_excluded(row.get("industry", ""), excluded):
            row["excluded_by_industry"] = True
            excluded_rows.append(row)
            continue
        if not row["themes"]:
            row["unclassified_theme"] = True
            unclassified_rows.append(row)
            continue
        for theme_name in row["themes"]:
            bucket = themes.setdefault(theme_name, {
                "theme": theme_name,
                "stocks": [],
                "count": 0,
                "avg_volume_ratio": None,
                "avg_week_chg_pct": None,
                "score": 0,
            })
            bucket["stocks"].append(row)

    theme_rows = []
    for bucket in themes.values():
        stocks_in_theme = sorted(bucket["stocks"], key=lambda r: (-num(r.get("theme_score")), r["stock_id"]))
        ratios = [num(r.get("volume_ratio")) for r in stocks_in_theme if r.get("volume_ratio") is not None]
        week = [num(r.get("week_chg_pct")) for r in stocks_in_theme if r.get("week_chg_pct") is not None]
        count = len(stocks_in_theme)
        pullback_count = sum(
            1 for r in stocks_in_theme
            if "momentum_pullback" in r.get("sources", []) or "volume_pullback" in r.get("sources", [])
        )
        breakout_count = sum(1 for r in stocks_in_theme if "right_top" in r.get("sources", []))
        chips_count = sum(1 for r in stocks_in_theme if "chips" in r.get("sources", []))
        score = (
            count * 10
            + min(sum(num(r.get("theme_score")) for r in stocks_in_theme[:5]) / 5, 70)
            + pullback_count * 5
            + breakout_count * 4
            + chips_count * 3
        )
        if bucket["theme"] in broad_themes:
            score *= 0.45
        theme_rows.append({
            "theme": bucket["theme"],
            "score": round(score, 1),
            "count": count,
            "pullback_count": pullback_count,
            "breakout_count": breakout_count,
            "chips_count": chips_count,
            "avg_volume_ratio": round(sum(ratios) / len(ratios), 2) if ratios else None,
            "avg_week_chg_pct": round(sum(week) / len(week), 2) if week else None,
            "representatives": [
                {
                    "stock_id": r["stock_id"],
                    "name": r["name"],
                    "industry": r["industry"],
                    "close": r["close"],
                    "theme_score": r["theme_score"],
                    "source_labels": r["source_labels"][:4],
                    "status": r["status"],
                    "volume_ratio": r["volume_ratio"],
                    "week_chg_pct": r["week_chg_pct"],
                }
                for r in stocks_in_theme[:5]
            ],
        })

    theme_rows.sort(key=lambda r: (-num(r.get("score")), -num(r.get("count")), r["theme"]))
    top_theme_names = {r["theme"] for r in theme_rows[:5]}
    selected = [
        r for r in sorted(stocks.values(), key=lambda x: (-num(x.get("theme_score")), x["stock_id"]))
        if any(t in top_theme_names for t in r.get("themes", [])) and not r.get("excluded_by_industry")
    ][:30]

    valid_dates = [d for d in source_dates if d]
    latest_date = sorted(valid_dates)[-1] if valid_dates else ""
    return {
        "strategy_id": "theme_heat",
        "updated": now_tw(),
        "source_date": latest_date,
        "model": {
            "definition": "Use existing scan outputs only; no extra quote or FinMind requests.",
            "excluded_industries": excluded,
            "source_weights": SOURCE_WEIGHTS,
        },
        "summary": {
            "themes": len(theme_rows),
            "stocks": len(stocks),
            "selected": len(selected),
            "excluded_by_industry": len(excluded_rows),
            "unclassified": len(unclassified_rows),
            "source_counts": source_counts,
        },
        "themes": theme_rows,
        "selected": selected,
    }


def main() -> int:
    output = build()
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"theme heat updated: themes={output['summary']['themes']} selected={output['summary']['selected']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
