#!/usr/bin/env python3
"""Shared 0-100 scoring model for stock candidates.

The model is intentionally transparent and easy to tune. Each row receives five
component scores, a bounded source multiplier, and a capped final score.
"""

from __future__ import annotations

import json
import os
from typing import Any

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
CONFIG_PATH = os.path.join(DATA_DIR, "unified_score_config.json")

DEFAULT_CONFIG = {
    "version": "unified_score_v1",
    "weights": {"chip": 0.25, "momentum": 0.25, "volume": 0.20, "structure": 0.20, "theme": 0.10},
    "source_multiplier": {"1": 1.0, "2": 1.05, "3": 1.10, "4": 1.15, "max": 1.15},
}


def load_config() -> dict[str, Any]:
    if not os.path.exists(CONFIG_PATH):
        return DEFAULT_CONFIG
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    return {**DEFAULT_CONFIG, **config}


CONFIG = load_config()
WEIGHTS = CONFIG["weights"]


def num(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def scale(value: Any, low: float, high: float, out_low: float = 0.0, out_high: float = 100.0) -> float:
    n = num(value)
    if n is None:
        return 0.0
    if high == low:
        return out_high if n >= high else out_low
    ratio = (n - low) / (high - low)
    return clamp(out_low + ratio * (out_high - out_low), min(out_low, out_high), max(out_low, out_high))


def first_num(row: dict[str, Any], *keys: str) -> float | None:
    metrics = row.get("metrics") or {}
    for key in keys:
        if key in row:
            n = num(row.get(key))
            if n is not None:
                return n
        if key in metrics:
            n = num(metrics.get(key))
            if n is not None:
                return n
    return None


def merge_sources(row: dict[str, Any], fallback: str | None = None) -> list[str]:
    sources = row.get("sources") or row.get("strategies") or []
    if isinstance(sources, str):
        sources = [sources]
    sources = [str(s) for s in sources if s]
    if fallback and fallback not in sources:
        sources.append(fallback)
    return sorted(set(sources))


def grade(score: float) -> str:
    if score >= 85:
        return "A+"
    if score >= 75:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    return "D"


def source_multiplier(source_count: int) -> float:
    table = CONFIG.get("source_multiplier") or {}
    if source_count >= 4:
        return float(table.get("4", table.get("max", 1.15)))
    return float(table.get(str(max(source_count, 1)), 1.0))


def chip_score(row: dict[str, Any]) -> tuple[float, list[str]]:
    tags = set(row.get("tags") or row.get("source_tags") or [])
    parts: list[float] = []
    reasons: list[str] = []

    big1000 = first_num(row, "big_pct_1000")
    big400 = first_num(row, "big_pct_400")
    chg1000 = first_num(row, "chg_1w_1000", "cumulative_3w", "big_1000_chg_3w", "chg_4w_1000")
    chg400 = first_num(row, "chg_1w_400", "cumulative_3w_400", "big_400_chg_3w", "chg_4w_400")
    tag_score = first_num(row, "tag_score")

    if big1000 is not None:
        parts.append(scale(big1000, 20, 55, 25, 90))
        if big1000 >= 35:
            reasons.append(f"大戶占比 {big1000:.1f}%")
    if big400 is not None:
        parts.append(scale(big400, 35, 70, 30, 90))
    if chg1000 is not None:
        parts.append(scale(chg1000, -2, 8, 10, 95))
        if chg1000 > 0:
            reasons.append(f"千張增 {chg1000:+.1f}%")
    if chg400 is not None:
        parts.append(scale(chg400, -2, 8, 10, 90))
    if tag_score is not None:
        parts.append(scale(tag_score, 0, 10, 15, 90))

    tag_text = " ".join(str(t) for t in tags)
    if any(k in tag_text for k in ("持續成長", "連續", "單周增幅", "外資連買", "投信連買", "雙軌")):
        parts.append(82)
        reasons.append("籌碼標籤加分")

    if not parts and first_num(row, "chip_score") is not None:
        parts.append(scale(first_num(row, "chip_score"), 0, 10, 0, 100))

    return (round(sum(parts) / len(parts), 1) if parts else 0.0, reasons[:3])


def momentum_score(row: dict[str, Any]) -> tuple[float, list[str]]:
    parts: list[float] = []
    reasons: list[str] = []

    week_chg = first_num(row, "week_chg_pct")
    change_pct = first_num(row, "change_pct")
    advance_pct = first_num(row, "advance_pct")
    pnl_pct = first_num(row, "track_pnl_pct", "pnl_pct")
    bias20 = first_num(row, "price_bias_ema20", "bias_ema20")
    bias120 = first_num(row, "price_bias_ema120", "deviation")
    close = first_num(row, "close", "current_price")
    ema20 = first_num(row, "ema20")
    ema60 = first_num(row, "ema60")
    ema120 = first_num(row, "ema120")

    for value, label in ((week_chg, "週漲"), (change_pct, "日漲"), (advance_pct, "波段"), (pnl_pct, "追蹤")):
        if value is not None:
            parts.append(scale(value, -5, 18, 10, 95))
            if value > 0:
                reasons.append(f"{label} {value:+.1f}%")

    if close is not None and ema120:
        parts.append(82 if close > ema120 else 25)
        if close > ema120:
            reasons.append("收盤站上 EMA120")
    if close is not None and ema20:
        parts.append(72 if close > ema20 else 35)
    if ema20 and ema60 and ema120:
        parts.append(90 if ema20 >= ema60 >= ema120 else 45)
    if bias120 is not None:
        parts.append(scale(bias120, -5, 35, 20, 90))

    if row.get("is_price_breakout") or row.get("daily_breakout_60d") or row.get("is_momentum_breakout"):
        parts.append(88)
        reasons.append("突破訊號")

    base = sum(parts) / len(parts) if parts else 0.0
    if bias20 is not None and bias20 > 25:
        base -= 12
        reasons.append("EMA20 乖離偏高")
    if pnl_pct is not None and pnl_pct > 20:
        base -= 10
        reasons.append("追蹤漲幅偏高")

    return round(clamp(base), 1), reasons[:3]


def volume_score(row: dict[str, Any]) -> tuple[float, list[str]]:
    parts: list[float] = []
    reasons: list[str] = []

    ratio = first_num(
        row,
        "vol_ratio",
        "today_vol_ratio",
        "ignition_vol_ratio",
        "track_vol_ratio",
        "price_vol_ratio",
        "daily_vol_ratio",
        "volume_ratio",
    )
    if ratio is not None:
        parts.append(scale(ratio, 0.8, 5.0, 15, 95))
        reasons.append(f"量比 {ratio:.2f}x")

    vol5 = first_num(row, "vol_5d_avg")
    vol20 = first_num(row, "vol_20d_avg", "vol20")
    if vol5 and vol20:
        v = vol5 / vol20
        parts.append(scale(v, 0.8, 2.0, 20, 90))
        reasons.append(f"5/20 均量 {v:.2f}x")

    cooldown = first_num(row, "volume_cooldown_pct")
    if cooldown is not None:
        parts.append(scale(cooldown, 20, 70, 45, 92))
        reasons.append(f"回測量縮 {cooldown:.0f}%")

    if row.get("volume_cools") is True:
        parts.append(82)
        reasons.append("回測量縮")

    return (round(sum(parts) / len(parts), 1) if parts else 0.0, reasons[:3])


def structure_score(row: dict[str, Any]) -> tuple[float, list[str]]:
    parts: list[float] = []
    reasons: list[str] = []
    status = str(row.get("status") or first_metric(row, "pullback_status") or "")

    status_scores = {
        "reentry": 92,
        "pullback": 78,
        "ignition": 68,
        "watch": 48,
        "點火首日": 68,
        "再啟動": 92,
        "回穩觀察": 78,
    }
    for key, value in status_scores.items():
        if key in status:
            parts.append(value)
            reasons.append(status)
            break

    fib_zone = row.get("fib_zone")
    if fib_zone == "23.6%-38.2%":
        parts.append(90)
        reasons.append("強勢回測區")
    elif fib_zone == "38.2%-50%":
        parts.append(82)
        reasons.append("健康回測區")
    elif fib_zone == "50%-61.8%":
        parts.append(62)
        reasons.append("深回測區")

    ma_dist = first_num(row, "ma_distance_pct")
    if ma_dist is not None:
        parts.append(scale(8 - abs(ma_dist), 0, 8, 25, 90))
        reasons.append(f"均線距離 {ma_dist:+.1f}%")

    risk = first_num(row, "risk_to_support_pct")
    if risk is not None:
        parts.append(scale(10 - risk, 0, 10, 25, 92))
        reasons.append(f"防守距離 {risk:.1f}%")

    pullback_pct = first_num(row, "pullback_from_ignition_close_pct", "pullback_from_high_pct")
    if pullback_pct is not None:
        parts.append(scale(18 - abs(pullback_pct), 0, 18, 25, 88))

    if row.get("support_ok") is True:
        parts.append(86)
        reasons.append("支撐守住")

    return (round(sum(parts) / len(parts), 1) if parts else 0.0, reasons[:3])


def first_metric(row: dict[str, Any], key: str) -> Any:
    if key in row:
        return row.get(key)
    return (row.get("metrics") or {}).get(key)


def theme_score(row: dict[str, Any], theme_index: dict[str, dict[str, Any]] | None = None) -> tuple[float, list[str]]:
    sid = str(row.get("stock_id") or row.get("ticker") or "")
    if not theme_index or sid not in theme_index:
        return 0.0, []
    theme = theme_index[sid]
    score = clamp(num(theme.get("score"), 0) or 0)
    name = theme.get("theme") or theme.get("name") or "主線"
    return round(score, 1), [f"{name} {score:.1f}"]


def compute_unified_score(
    row: dict[str, Any],
    *,
    fallback_source: str | None = None,
    theme_index: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    sources = merge_sources(row, fallback_source)
    components: dict[str, float] = {}
    reasons: dict[str, list[str]] = {}

    scorers = {
        "chip": chip_score,
        "momentum": momentum_score,
        "volume": volume_score,
        "structure": structure_score,
    }
    for key, scorer in scorers.items():
        value, why = scorer(row)
        components[key] = value
        reasons[key] = why
    value, why = theme_score(row, theme_index)
    components["theme"] = value
    reasons["theme"] = why

    base = sum(components.get(key, 0.0) * float(WEIGHTS.get(key, 0.0)) for key in WEIGHTS)
    multiplier = source_multiplier(len(sources))
    total = round(clamp(base * multiplier), 1)

    return {
        "version": CONFIG.get("version", "unified_score_v1"),
        "total": total,
        "grade": grade(total),
        "base": round(base, 1),
        "components": {k: round(v, 1) for k, v in components.items()},
        "source_count": len(sources),
        "source_multiplier": multiplier,
        "sources": sources,
        "reasons": reasons,
    }


def apply_unified_score(
    row: dict[str, Any],
    *,
    fallback_source: str | None = None,
    theme_index: dict[str, dict[str, Any]] | None = None,
    replace_score: bool = True,
) -> dict[str, Any]:
    detail = compute_unified_score(row, fallback_source=fallback_source, theme_index=theme_index)
    if "legacy_score" not in row and row.get("score") is not None:
        row["legacy_score"] = row.get("score")
    row["unified_score"] = detail["total"]
    row["unified_score_grade"] = detail["grade"]
    row["score_breakdown"] = detail
    if replace_score:
        row["score"] = detail["total"]
    return row
