#!/usr/bin/env python3
"""
短線強勢雷達

整合目前仍啟用的策略輸出，將籌碼集中、量增訊號、突破追蹤、
量增回測與量增標的追蹤彙整成單一候選清單。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")

CHIPS_PATH = os.path.join(DATA_DIR, "chips_big_holder.json")
VOLUME_SIGNAL_PATH = os.path.join(DATA_DIR, "volume_signal.json")
VOLUME_PULLBACK_PATH = os.path.join(DATA_DIR, "volume_pullback.json")
RIGHT_TOP_TRACK_PATH = os.path.join(DATA_DIR, "right_top_track.json")
AI_ANALYSIS_PATH = os.path.join(DATA_DIR, "ai_analysis.json")
CURRENT_PRICES_PATH = os.path.join(DATA_DIR, "current_prices.json")
OUTPUT_PATH = os.path.join(DATA_DIR, "momentum_candidates.json")

TW_TZ = timezone(timedelta(hours=8))
HOT_INDUSTRY_KEYWORDS = (
    "電子零組件",
    "電子工業",
    "電腦",
    "電腦及週邊",
    "光電",
    "半導體",
    "其他電子",
    "機電",
    "電機",
    "通信",
)
MAX_EXTENDED_PCT = 15.0
PRIORITY_RANK = {"A": 1, "B": 2, "C": 3}


def load_json(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def now_tw() -> str:
    return datetime.now(TW_TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")


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


def ensure_row(rows: dict[str, dict[str, Any]], stock_id: str, name: str = "") -> dict[str, Any]:
    stock_id = str(stock_id or "").strip()
    if stock_id not in rows:
        rows[stock_id] = {
            "stock_id": stock_id,
            "name": name,
            "industry": "",
            "market": "",
            "close": None,
            "status": "",
            "status_rank": 9,
            "sources": [],
            "tags": [],
            "score_parts": {},
            "metrics": {},
        }
    if name and not rows[stock_id]["name"]:
        rows[stock_id]["name"] = name
    return rows[stock_id]


def merge_base(row: dict[str, Any], item: dict[str, Any], source: str) -> None:
    row["name"] = row["name"] or item.get("name", "")
    row["industry"] = row["industry"] or item.get("industry", "")
    row["market"] = row["market"] or item.get("market", "")
    row["close"] = item.get("current_price") or item.get("close") or row.get("close")
    if source not in row["sources"]:
        row["sources"].append(source)
    for tag in item.get("tags", []) or item.get("source_tags", []) or []:
        if tag not in row["tags"]:
            row["tags"].append(tag)


def set_status(row: dict[str, Any], label: str, rank: int) -> None:
    if rank < row.get("status_rank", 9):
        row["status"] = label
        row["status_rank"] = rank


def add_score(row: dict[str, Any], key: str, score: float) -> None:
    row["score_parts"][key] = max(num(row["score_parts"].get(key)), score)


def set_priority(row: dict[str, Any]) -> None:
    metrics = row.get("metrics", {})
    sources = set(row.get("sources", []))
    rev_score = num(metrics.get("rev_score"))
    chip_score = num(metrics.get("chip_score"))
    today_vol_ratio = num(metrics.get("today_vol_ratio"))
    ignition_vol_ratio = num(metrics.get("ignition_vol_ratio"))
    pullback_status = metrics.get("pullback_status")
    source_count = len(sources)
    reasons: list[str] = []

    if rev_score >= 8 and chip_score >= 6:
        reasons.extend(["大戶營收>=8", "籌碼>=6"])
        level = "A"
    elif pullback_status == "reentry":
        reasons.append("量增回測再啟動")
        level = "A"
    elif today_vol_ratio >= 3 and {"chips", "volume_signal"}.issubset(sources):
        reasons.append("大戶池放量>=3x")
        level = "A"
    elif source_count >= 3 and ignition_vol_ratio >= 3:
        reasons.append("多策略共振且點火量>=3x")
        level = "A"
    elif rev_score >= 6 or chip_score >= 6 or today_vol_ratio >= 1.5 or pullback_status in ("pullback", "ignition"):
        reasons.append("達觀察條件")
        level = "B"
    else:
        reasons.append("低優先觀察")
        level = "C"

    row["priority_level"] = level
    row["priority_rank"] = PRIORITY_RANK.get(level, 9)
    row["priority_reason"] = reasons


def scan() -> dict[str, Any]:
    rows: dict[str, dict[str, Any]] = {}
    prices = load_json(CURRENT_PRICES_PATH).get("prices", {})

    for item in load_json(CHIPS_PATH).get("results", []):
        sid = str(item.get("stock_id") or "")
        if not sid:
            continue
        row = ensure_row(rows, sid, item.get("name", ""))
        merge_base(row, item, "chips")
        row["metrics"].update({
            "market_cap": round_or_none(item.get("market_cap"), 1),
            "bbw": round_or_none(item.get("bbw"), 2),
            "week_chg_pct": round_or_none(item.get("week_chg_pct"), 2),
            "big_pct_1000": round_or_none(item.get("big_pct_1000"), 2),
            "big_pct_400": round_or_none(item.get("big_pct_400"), 2),
        })
        score = 0
        market_cap = num(item.get("market_cap"), 9999)
        bbw = num(item.get("bbw"), 999)
        week_chg = num(item.get("week_chg_pct"))
        tags = item.get("tags", []) or []
        if 20 <= market_cap <= 120:
            score += 8
        if bbw <= 12:
            score += 8
        elif bbw <= 15:
            score += 4
        if 0 < week_chg <= 15:
            score += 5
        if "持續成長" in tags:
            score += 5
        if "單周增幅" in tags:
            score += 5
        if "外資連買" in tags or "投信連買" in tags:
            score += 4
        add_score(row, "chips", score)
        set_status(row, "籌碼蓄勢", 5)

    for item in load_json(VOLUME_SIGNAL_PATH).get("results", []):
        sid = str(item.get("stock_id") or "")
        if not sid:
            continue
        row = ensure_row(rows, sid, item.get("name", ""))
        merge_base(row, item, "volume_signal")
        vol_ratio = num(item.get("vol_ratio"))
        row["metrics"].update({
            "today_vol_ratio": round_or_none(vol_ratio, 2),
            "vol_today": item.get("vol_today"),
            "vol_10d_avg": round_or_none(item.get("vol_10d_avg"), 0),
        })
        score = 18
        if vol_ratio >= 5:
            score += 16
        elif vol_ratio >= 3:
            score += 10
        elif vol_ratio >= 1.5:
            score += 5
        if "持續成長" in (item.get("tags", []) or []):
            score += 5
        if "外資連買" in (item.get("tags", []) or []):
            score += 4
        add_score(row, "ignition", score)
        set_status(row, "點火首日", 2)

    for item in load_json(RIGHT_TOP_TRACK_PATH).get("active", []):
        sid = str(item.get("stock_id") or "")
        if not sid:
            continue
        row = ensure_row(rows, sid, item.get("name", ""))
        merge_base(row, item, "right_top_track")
        pnl = num(item.get("pnl_pct"))
        vol_ratio = num(item.get("vol_ratio"))
        row["metrics"].update({
            "track_pnl_pct": round_or_none(pnl, 2),
            "track_vol_ratio": round_or_none(vol_ratio, 2),
            "entry_price": round_or_none(item.get("entry_price"), 2),
            "days_remaining": item.get("days_remaining"),
        })
        score = 12
        if pnl >= 30:
            score += 20
        elif pnl >= 15:
            score += 14
        elif pnl >= 5:
            score += 8
        if vol_ratio >= 3:
            score += 8
        if num(item.get("days_remaining")) >= 5:
            score += 3
        add_score(row, "breakout_track", score)
        set_status(row, "突破延伸", 4)

    for item in load_json(VOLUME_PULLBACK_PATH).get("active", []):
        sid = str(item.get("stock_id") or "")
        if not sid:
            continue
        row = ensure_row(rows, sid, item.get("name", ""))
        merge_base(row, item, "volume_pullback")
        status = item.get("status", "")
        status_label = item.get("status_label") or status
        rank = {"reentry": 1, "ignition": 2, "pullback": 3, "watch": 6}.get(status, 6)
        set_status(row, status_label, rank)
        ignition_vol = num(item.get("ignition_vol_ratio"))
        pullback_pct = num(item.get("pullback_from_ignition_close_pct"))
        row["metrics"].update({
            "pullback_status": status,
            "pullback_score": item.get("score"),
            "ignition_vol_ratio": round_or_none(ignition_vol, 2),
            "pullback_from_ignition_close_pct": round_or_none(pullback_pct, 2),
            "days_since_ignition": item.get("days_since_ignition"),
            "support_ok": item.get("support_ok"),
            "volume_cools": item.get("volume_cools"),
        })
        score = 8
        if status == "reentry":
            score = 35
        elif status == "pullback":
            score = 24
        elif status == "ignition":
            score = 22
        if ignition_vol >= 5:
            score += 12
        elif ignition_vol >= 3:
            score += 7
        if item.get("support_ok"):
            score += 6
        if item.get("volume_cools") and num(item.get("days_since_ignition")) >= 1:
            score += 5
        if pullback_pct > 25:
            score -= 10
        add_score(row, "pullback", score)

    for item in load_json(AI_ANALYSIS_PATH).get("active", []):
        sid = str(item.get("ticker") or item.get("stock_id") or "")
        if not sid:
            continue
        row = ensure_row(rows, sid, item.get("name", ""))
        merge_base(row, {"stock_id": sid, **item}, "stock_analysis")
        pnl = num(item.get("pnl_pct"))
        row["metrics"].update({
            "ai_pnl_pct": round_or_none(pnl, 2),
            "rev_score": round_or_none(item.get("quant_scores", {}).get("rev_score"), 1),
            "chip_score": round_or_none(item.get("quant_scores", {}).get("chip_score"), 1),
            "trend_score": round_or_none(item.get("quant_scores", {}).get("trend_score"), 1),
        })
        score = 0
        if pnl >= 10:
            score += 8
        add_score(row, "follow", score)

    candidates = []
    for sid, row in rows.items():
        row["close"] = row.get("close") or prices.get(sid)
        industry = row.get("industry", "")
        source_bonus = min(12, max(0, len(row["sources"]) - 1) * 5)
        industry_bonus = 6 if any(key in industry for key in HOT_INDUSTRY_KEYWORDS) else 0
        track_pnl = num(row["metrics"].get("track_pnl_pct"))
        pullback_pct = num(row["metrics"].get("pullback_from_ignition_close_pct"))
        ai_pnl = num(row["metrics"].get("ai_pnl_pct"))
        extended = max(track_pnl, pullback_pct, ai_pnl) > MAX_EXTENDED_PCT
        if extended:
            continue
        score = sum(num(v) for v in row["score_parts"].values()) + source_bonus + industry_bonus
        if score < 35:
            continue
        row["score"] = round(score, 1)
        row["source_count"] = len(row["sources"])
        row["risk_flags"] = []
        set_priority(row)
        candidates.append(row)

    candidates.sort(key=lambda r: (r.get("priority_rank", 9), -num(r["score"]), r.get("status_rank", 9), r["stock_id"]))
    return {
        "strategy_id": "momentum_candidates",
        "updated": now_tw(),
        "model": {
            "sources": [
                "chips_big_holder",
                "volume_signal",
                "right_top_track",
                "volume_pullback",
                "ai_analysis",
            ],
            "disabled_sources": ["vcp", "trust_momentum"],
            "score_min": 35,
            "max_extended_pct": MAX_EXTENDED_PCT,
            "priority_rules": {
                "A": [
                    "rev_score >= 8 and chip_score >= 6",
                    "volume pullback reentry",
                    "chips + volume signal with volume ratio >= 3",
                    "3+ sources with ignition volume ratio >= 3",
                ],
                "B": ["single quality or ignition/pullback observation condition"],
            },
        },
        "summary": {
            "total": len(candidates),
            "top10": len(candidates[:10]),
            "priority_a": sum(1 for r in candidates if r.get("priority_level") == "A"),
            "priority_b": sum(1 for r in candidates if r.get("priority_level") == "B"),
            "priority_c": sum(1 for r in candidates if r.get("priority_level") == "C"),
            "reentry": sum(1 for r in candidates if r.get("status") == "再啟動"),
            "ignition": sum(1 for r in candidates if r.get("status") == "點火首日"),
            "pullback": sum(1 for r in candidates if r.get("status") == "回穩觀察"),
        },
        "results": candidates,
    }


def main() -> int:
    output = scan()
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"短線強勢雷達：{output['summary']['total']} 檔")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
