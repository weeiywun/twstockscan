#!/usr/bin/env python3
"""
法人動能掃描器

用既有 price_cache 取得交易日與價量，再查 TWSE/TPEx 官方盤後法人買賣超。
同時產出投信動能、外資動能、雙法人共振；不逐檔打 FinMind。
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
import requests

from finmind_client import load_price_cache

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
OUTPUT_PATH = os.path.join(DATA_DIR, "trust_momentum.json")
STOCK_LIST_PATH = os.path.join(DATA_DIR, "stock_list_cache.json")

TW_TZ = timezone(timedelta(hours=8))
TODAY = datetime.now(TW_TZ).strftime("%Y-%m-%d")

PRICE_LOOKBACK_DAYS = 260
OFFICIAL_LOOKBACK_TRADING_DAYS = 12
SIGNAL_TRADING_DAYS = 10
MAX_RESULTS = 100
MIN_AVG_VOL_20D = 500
MIN_INST_VOL_RATIO_5D = 0.08
MIN_EMA120_LOOKBACK = 130

ACTORS = {
    "trust": {"label": "投信", "tag": "投信動能", "strong": "投信強買", "buy": "投信買盤"},
    "foreign": {"label": "外資", "tag": "外資動能", "strong": "外資強買", "buy": "外資買盤"},
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept": "application/json,text/html,*/*",
}


def now_tw() -> str:
    return datetime.now(TW_TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def _write_output(
    trust_results: list[dict],
    foreign_results: list[dict],
    confluence_results: list[dict],
    industry_stats: dict[str, list[dict]],
    source_date: str = "",
) -> None:
    output = {
        "strategy_id": "institutional_momentum",
        "updated": now_tw(),
        "source_date": source_date,
        "results": trust_results,
        "trust_results": trust_results,
        "foreign_results": foreign_results,
        "confluence_results": confluence_results,
        "industry_stats": industry_stats.get("trust", []),
        "trust_industry_stats": industry_stats.get("trust", []),
        "foreign_industry_stats": industry_stats.get("foreign", []),
        "confluence_industry_stats": industry_stats.get("confluence", []),
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(
        f"已寫入 {OUTPUT_PATH}，投信 {len(trust_results)} 檔 / "
        f"外資 {len(foreign_results)} 檔 / 共振 {len(confluence_results)} 檔"
    )


def _preserve_existing_output(source_date: str) -> None:
    if os.path.exists(OUTPUT_PATH):
        print(f"官方法人資料暫時無法取得，保留既有 {OUTPUT_PATH}")
        return
    _write_output([], [], [], {}, source_date)


def _require_fresh_cache(price_cache: pd.DataFrame) -> str:
    latest = price_cache["date"].max().strftime("%Y-%m-%d")
    if latest != TODAY:
        print(f"price_cache.parquet 最新資料為 {latest}，不是 {TODAY}；停止掃描，避免舊資料產生訊號")
        sys.exit(1)
    return latest


def _stock_map() -> dict[str, dict[str, str]]:
    if not os.path.exists(STOCK_LIST_PATH):
        return {}
    with open(STOCK_LIST_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    stocks: dict[str, dict[str, str]] = {}
    for item in raw:
        sid = str(item.get("stock_id") or "").strip()
        if not sid or sid in stocks:
            continue
        stocks[sid] = {
            "name": item.get("name", ""),
            "industry": item.get("industry", ""),
            "market": item.get("market", ""),
        }
    return stocks


def _num(value: Any) -> float:
    if value is None:
        return 0.0
    text = str(value).replace(",", "").replace("--", "0").strip()
    if text in {"", "-", "X", "x"}:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _stock_id(value: Any) -> str:
    match = re.search(r"\d{4,6}", str(value or ""))
    return match.group(0) if match else ""


def _roc_date(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return f"{dt.year - 1911}/{dt.month:02d}/{dt.day:02d}"


def _find_field(fields: list[Any], keywords: list[str]) -> int | None:
    for idx, field in enumerate(fields):
        text = re.sub(r"\s+", "", str(field))
        if all(keyword in text for keyword in keywords):
            return idx
    return None


def _row_values(row: Any) -> list[Any]:
    if isinstance(row, list):
        return row
    if isinstance(row, dict):
        value = row.get("value")
        if isinstance(value, list):
            return value
    return []


def _price_slice(price_cache: pd.DataFrame, sid: str, start_date: str) -> pd.DataFrame:
    df = price_cache[price_cache["stock_id"].astype(str) == sid].copy()
    df = df[df["date"] >= pd.Timestamp(start_date)]
    return df.sort_values("date").reset_index(drop=True)


def _recent_trade_dates(price_cache: pd.DataFrame, limit: int) -> list[str]:
    dates = sorted({d.strftime("%Y-%m-%d") for d in price_cache["date"].dropna()})
    return dates[-limit:]


def fetch_twse_institutional(date_str: str) -> dict[str, dict[str, float]]:
    ymd = date_str.replace("-", "")
    url = "https://www.twse.com.tw/rwd/zh/fund/T86"
    params = {"date": ymd, "selectType": "ALLBUT0999", "response": "json"}
    empty = {"trust": {}, "foreign": {}}
    try:
        res = requests.get(url, params=params, headers=HEADERS, timeout=30)
        res.raise_for_status()
        payload = res.json()
    except Exception as exc:
        print(f"  [WARN] TWSE T86 {date_str} 取得失敗：{exc}")
        return empty

    rows = payload.get("data") or []
    fields = payload.get("fields") or []
    if not rows or not fields:
        return empty

    code_idx = _find_field(fields, ["證券代號"])
    foreign_idx = _find_field(fields, ["外陸資買賣超股數", "不含外資自營商"])
    foreign_dealer_idx = _find_field(fields, ["外資自營商買賣超股數"])
    trust_idx = _find_field(fields, ["投信買賣超股數"])
    if code_idx is None or foreign_idx is None or trust_idx is None:
        print(f"  [WARN] TWSE T86 {date_str} 欄位格式不符")
        return empty

    result = {"trust": {}, "foreign": {}}
    for raw in rows:
        row = _row_values(raw)
        sid = _stock_id(row[code_idx] if code_idx < len(row) else "")
        if not sid:
            continue
        foreign_net = _num(row[foreign_idx]) if foreign_idx < len(row) else 0.0
        if foreign_dealer_idx is not None and foreign_dealer_idx < len(row):
            foreign_net += _num(row[foreign_dealer_idx])
        trust_net = _num(row[trust_idx]) if trust_idx < len(row) else 0.0
        result["foreign"][sid] = foreign_net / 1000
        result["trust"][sid] = trust_net / 1000
    return result


def fetch_tpex_institutional(date_str: str) -> dict[str, dict[str, float]]:
    url = "https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php"
    params = {"d": _roc_date(date_str), "t": "D", "se": "EW", "l": "zh-tw", "o": "json"}
    empty = {"trust": {}, "foreign": {}}
    try:
        res = requests.get(url, params=params, headers=HEADERS, timeout=30)
        res.raise_for_status()
        payload = res.json()
    except Exception as exc:
        print(f"  [WARN] TPEx 三大法人 {date_str} 取得失敗：{exc}")
        return empty

    tables = payload.get("tables")
    if not isinstance(tables, list) or not tables:
        return empty

    result = {"trust": {}, "foreign": {}}
    for table in tables:
        rows = table.get("data") if isinstance(table, dict) else None
        if not isinstance(rows, list):
            continue
        for raw in rows:
            row = _row_values(raw)
            if len(row) < 14:
                continue
            sid = _stock_id(row[0])
            if not sid:
                continue
            # TPEx 欄位順序：0代號 1名稱，2-4外資不含自營，5-7外資自營，8-10外資合計，11-13投信。
            result["foreign"][sid] = _num(row[10]) / 1000
            result["trust"][sid] = _num(row[13]) / 1000
    return result


def fetch_official_inst_maps(trade_dates: list[str]) -> dict[str, dict[str, dict[str, float]]]:
    by_actor: dict[str, dict[str, dict[str, float]]] = {
        "trust": defaultdict(dict),
        "foreign": defaultdict(dict),
    }
    for date_str in trade_dates:
        twse = fetch_twse_institutional(date_str)
        tpex = fetch_tpex_institutional(date_str)
        for actor in ACTORS:
            merged = {**twse[actor], **tpex[actor]}
            for sid, net_lots in merged.items():
                by_actor[actor][sid][date_str] = net_lots
        print(
            f"官方法人買賣超 {date_str}："
            f"TWSE 投信 {len(twse['trust']):,}/外資 {len(twse['foreign']):,}，"
            f"TPEx 投信 {len(tpex['trust']):,}/外資 {len(tpex['foreign']):,}"
        )
    return {actor: {sid: dict(dates) for sid, dates in stock_map.items()} for actor, stock_map in by_actor.items()}


def _pct(a: float, b: float) -> float | None:
    if b == 0:
        return None
    return (a - b) / b * 100


def _flow_regime(row: dict) -> str:
    if row["inst_net_5d"] <= 0:
        return "neutral"
    attack = (
        (row["price_chg_5d"] or 0) > 0
        and (row["bias_ma20"] or -999) > 0
        and row["range_pos_20d"] >= 70
        and row["vol_ratio_5d"] >= 1.1
    )
    absorption = (
        (row["price_chg_5d"] or 0) < 0
        or (row["bias_ma20"] is not None and row["bias_ma20"] < 0)
        or row["range_pos_20d"] <= 35
    )
    if attack:
        return "attack"
    if absorption:
        return "absorption"
    return "accumulation"


def _score(row: dict) -> int:
    score = 0
    score += row["inst_buy_days_5d"] * 7
    score += max(row["inst_buy_days_10d"] - 5, 0) * 3
    score += min(max(row["inst_vol_ratio_5d"], 0) * 75, 24)
    score += min(max(row["range_pos_20d"], 0) / 100 * 12, 12)
    if row["flow_regime"] == "attack":
        score += 22
    elif row["flow_regime"] == "accumulation":
        score += 10
    elif row["flow_regime"] == "absorption":
        score -= 8
    if row["price_chg_5d"] is not None and row["price_chg_5d"] >= 25:
        score -= 8
    if row["bias_ma20"] is not None and row["bias_ma20"] >= 25:
        score -= 8
    return max(0, min(round(score), 100))


def _tags(row: dict) -> list[str]:
    meta = ACTORS[row["actor"]]
    tags = [meta["tag"]]
    if row["flow_regime"] == "attack":
        tags.append(f"{meta['label']}攻擊")
    elif row["flow_regime"] == "absorption":
        tags.append(f"{meta['label']}承接")
    else:
        tags.append(f"{meta['label']}佈局")
    if row["inst_buy_days_10d"] >= 8:
        tags.append(meta["strong"])
    elif row["inst_buy_days_10d"] >= 6:
        tags.append(meta["buy"])
    if row["inst_vol_ratio_5d"] >= 0.20:
        tags.append("買超占量高")
    elif row["inst_vol_ratio_5d"] >= 0.10:
        tags.append("買超占量增")
    if row["range_pos_20d"] >= 90:
        tags.append("區間高檔")
    if row["range_pos_20d"] <= 35:
        tags.append("區間低檔")
    if row.get("bias_ema120") is not None and row["bias_ema120"] > 0:
        tags.append("站上EMA120")
    if row["price_chg_5d"] is not None and row["price_chg_5d"] >= 25:
        tags.append("短線過熱")
    return tags


def build_actor_results(
    actor: str,
    inst_map: dict[str, dict[str, float]],
    price_cache: pd.DataFrame,
    stock_map: dict[str, dict[str, str]],
    price_start: str,
    signal_date: str,
) -> list[dict]:
    results: list[dict] = []
    for sid, date_map in inst_map.items():
        meta = stock_map.get(sid)
        if not meta:
            continue
        daily = _price_slice(price_cache, sid, price_start)
        if len(daily) < MIN_EMA120_LOOKBACK:
            continue

        daily = daily.copy()
        daily["ma20"] = daily["close"].rolling(20).mean()
        daily["ema120"] = daily["close"].ewm(span=120, adjust=False).mean()
        latest = daily.iloc[-1]
        close = float(latest["close"])
        ma20 = None if pd.isna(latest["ma20"]) else float(latest["ma20"])
        ema120 = None if pd.isna(latest["ema120"]) else float(latest["ema120"])
        if not ema120 or close <= ema120:
            continue
        avg_vol_20d = float(daily["volume_lots"].tail(20).mean())
        if avg_vol_20d < MIN_AVG_VOL_20D:
            continue

        trade_dates = [d.strftime("%Y-%m-%d") for d in daily["date"].tail(SIGNAL_TRADING_DAYS)]
        vals_10 = [float(date_map.get(d, 0)) for d in trade_dates]
        vals_5 = vals_10[-5:]
        inst_net_5d = sum(vals_5)
        inst_net_10d = sum(vals_10)
        inst_buy_days_5d = sum(1 for v in vals_5 if v > 0)
        inst_buy_days_10d = sum(1 for v in vals_10 if v > 0)
        inst_vol_ratio_5d = inst_net_5d / max(avg_vol_20d * 5, 1)

        if inst_buy_days_5d < 3 and inst_buy_days_10d < 6:
            continue
        if inst_net_5d <= 0 or inst_net_10d <= 0:
            continue
        if inst_vol_ratio_5d < MIN_INST_VOL_RATIO_5D:
            continue

        price_5d_ago = float(daily.iloc[-6]["close"]) if len(daily) >= 6 else close
        price_chg_5d = _pct(close, price_5d_ago)
        bias_ma20 = _pct(close, ma20) if ma20 else None
        bias_ema120 = _pct(close, ema120)
        high_20d = float(daily["close"].tail(20).max())
        low_20d = float(daily["close"].tail(20).min())
        range_pos_20d = 50.0 if high_20d == low_20d else (close - low_20d) / (high_20d - low_20d) * 100
        vol_ratio_5d = float(daily["volume_lots"].tail(5).mean()) / max(avg_vol_20d, 1)

        row = {
            "stock_id": sid,
            "name": meta.get("name", ""),
            "industry": meta.get("industry", ""),
            "market": meta.get("market", ""),
            "actor": actor,
            "actor_label": ACTORS[actor]["label"],
            "close": round(close, 2),
            "ma20": round(ma20, 2) if ma20 else None,
            "ema120": round(ema120, 2),
            "bias_ma20": round(bias_ma20, 2) if bias_ma20 is not None else None,
            "bias_ema120": round(bias_ema120, 2) if bias_ema120 is not None else None,
            "price_chg_5d": round(price_chg_5d, 2) if price_chg_5d is not None else None,
            "avg_vol_20d": round(avg_vol_20d, 1),
            "vol_ratio_5d": round(vol_ratio_5d, 2),
            "range_pos_20d": round(range_pos_20d, 1),
            "inst_net_5d": round(inst_net_5d, 1),
            "inst_net_10d": round(inst_net_10d, 1),
            "inst_buy_days_5d": inst_buy_days_5d,
            "inst_buy_days_10d": inst_buy_days_10d,
            "inst_vol_ratio_5d": round(inst_vol_ratio_5d, 3),
            "inst_series_10d": [{"date": d, "net": round(v, 1)} for d, v in zip(trade_dates, vals_10)],
            "is_new_20d_high": close >= high_20d,
            "signal_date": signal_date,
        }
        row["flow_regime"] = _flow_regime(row)
        row["quality_score"] = _score(row)
        row["tags"] = _tags(row)

        prefix = "trust" if actor == "trust" else "foreign"
        for key in ("net_5d", "net_10d", "buy_days_5d", "buy_days_10d", "vol_ratio_5d", "series_10d"):
            row[f"{prefix}_{key}"] = row[f"inst_{key}"]
        results.append(row)

    results.sort(
        key=lambda r: (
            r.get("flow_regime") == "attack",
            r.get("quality_score", 0),
            r.get("inst_vol_ratio_5d", 0),
            r.get("inst_net_5d", 0),
        ),
        reverse=True,
    )
    return results[:MAX_RESULTS]


def build_confluence_results(trust_results: list[dict], foreign_results: list[dict]) -> list[dict]:
    trust_by_sid = {row["stock_id"]: row for row in trust_results}
    rows: list[dict] = []
    for foreign in foreign_results:
        trust = trust_by_sid.get(foreign["stock_id"])
        if not trust:
            continue
        row = dict(foreign)
        row["actor"] = "confluence"
        row["actor_label"] = "雙法人"
        row["trust"] = {k: trust.get(k) for k in ("inst_net_5d", "inst_net_10d", "inst_buy_days_10d", "inst_vol_ratio_5d", "flow_regime")}
        row["foreign"] = {k: foreign.get(k) for k in ("inst_net_5d", "inst_net_10d", "inst_buy_days_10d", "inst_vol_ratio_5d", "flow_regime")}
        row["trust_net_5d"] = trust["inst_net_5d"]
        row["foreign_net_5d"] = foreign["inst_net_5d"]
        row["inst_net_5d"] = trust["inst_net_5d"] + foreign["inst_net_5d"]
        row["quality_score"] = min(100, round((trust["quality_score"] + foreign["quality_score"]) / 2 + 10))
        row["tags"] = ["雙法人共振"]
        if trust["flow_regime"] == "attack" and foreign["flow_regime"] == "attack":
            row["tags"].append("雙法人攻擊")
        elif trust["flow_regime"] == "absorption" or foreign["flow_regime"] == "absorption":
            row["tags"].append("法人承接")
        else:
            row["tags"].append("雙法人佈局")
        rows.append(row)
    rows.sort(key=lambda r: (r.get("quality_score", 0), r.get("inst_net_5d", 0)), reverse=True)
    return rows[:MAX_RESULTS]


def build_industry_stats(results: list[dict]) -> list[dict]:
    industry_map: dict[str, dict] = {}
    for row in results:
        industry = row.get("industry") or "其他"
        if industry not in industry_map:
            industry_map[industry] = {"industry": industry, "count": 0, "stocks": []}
        industry_map[industry]["count"] += 1
        industry_map[industry]["stocks"].append({"stock_id": row["stock_id"], "name": row["name"]})
    return sorted(industry_map.values(), key=lambda x: x["count"], reverse=True)


def main() -> None:
    print("=== 法人動能掃描器 ===")
    allow_stale = "--allow-stale" in sys.argv

    stock_map = _stock_map()
    if not stock_map:
        print("stock_list_cache.json 不存在或為空")
        _write_output([], [], [], {})
        return

    price_cache = load_price_cache()
    if price_cache is None or price_cache.empty:
        print("price_cache.parquet 不存在或為空")
        _write_output([], [], [], {})
        return

    price_cache["date"] = pd.to_datetime(price_cache["date"])
    if allow_stale:
        signal_date = price_cache["date"].max().strftime("%Y-%m-%d")
        print(f"--allow-stale：使用快取最新交易日 {signal_date}")
    else:
        signal_date = _require_fresh_cache(price_cache)

    price_start = (price_cache["date"].max() - pd.Timedelta(days=PRICE_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    official_dates = _recent_trade_dates(price_cache, OFFICIAL_LOOKBACK_TRADING_DAYS)
    signal_dates = official_dates[-SIGNAL_TRADING_DAYS:]
    print(f"使用 price_cache 交易日：{signal_dates[0]} ~ {signal_dates[-1]}")

    inst_maps = fetch_official_inst_maps(official_dates)
    if not inst_maps["trust"] and not inst_maps["foreign"]:
        print("沒有取得官方法人買賣超資料")
        _preserve_existing_output(signal_date)
        return

    trust_results = build_actor_results("trust", inst_maps["trust"], price_cache, stock_map, price_start, signal_date)
    foreign_results = build_actor_results("foreign", inst_maps["foreign"], price_cache, stock_map, price_start, signal_date)
    confluence_results = build_confluence_results(trust_results, foreign_results)
    industry_stats = {
        "trust": build_industry_stats(trust_results),
        "foreign": build_industry_stats(foreign_results),
        "confluence": build_industry_stats(confluence_results),
    }
    print(f"完成：投信 {len(trust_results)} / 外資 {len(foreign_results)} / 共振 {len(confluence_results)}")
    _write_output(trust_results, foreign_results, confluence_results, industry_stats, signal_date)


if __name__ == "__main__":
    main()
