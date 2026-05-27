#!/usr/bin/env python3
"""
Update market margin balance cache.

Sources:
- TWSE MI_MARGN official endpoint.
- TPEx mainboard margin balance public report.

The output is intentionally market-level, not per-stock. It is used as a
background leverage gauge in Future Dashboard.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from bs4 import BeautifulSoup


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
OUTPUT_PATH = os.path.join(DATA_DIR, "margin_balance.json")

TW_TZ = timezone(timedelta(hours=8))
NOW = datetime.now(TW_TZ)
TODAY = NOW.date()

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/html,application/json,*/*",
}


def _num(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("%", "")
    if not text or text in {"-", "--", "NULL", "NaN"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _int(value: Any) -> int | None:
    n = _num(value)
    return int(round(n)) if n is not None else None


def _latest_weekdays(max_days: int = 12) -> list[datetime.date]:
    dates: list[datetime.date] = []
    for offset in range(max_days):
        date = TODAY - timedelta(days=offset)
        if date.weekday() < 5:
            dates.append(date)
    return dates


def _roc_date(date: datetime.date) -> str:
    return f"{date.year - 1911}/{date.month:02d}/{date.day:02d}"


def _load_existing() -> dict[str, Any]:
    if not os.path.exists(OUTPUT_PATH):
        return {}
    try:
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _pick_field(fields: list[str], candidates: list[str]) -> int | None:
    clean = [re.sub(r"\s+", "", str(field)) for field in fields]
    for needle in candidates:
        needle_clean = re.sub(r"\s+", "", needle)
        for idx, field in enumerate(clean):
            if field == needle_clean:
                return idx
    for needle in candidates:
        needle_clean = re.sub(r"\s+", "", needle)
        for idx, field in enumerate(clean):
            if needle_clean in field:
                return idx
    return None


def fetch_twse(date: datetime.date) -> dict[str, Any] | None:
    date_text = date.strftime("%Y%m%d")
    urls = [
        "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN",
        "https://www.twse.com.tw/exchangeReport/MI_MARGN",
    ]
    params = {"response": "json", "date": date_text, "selectType": "MS"}
    for url in urls:
        try:
            res = requests.get(url, params=params, headers=HEADERS, timeout=25)
            res.raise_for_status()
            data = res.json()
            tables = data.get("tables") or []
            summary_table = next(
                (table for table in tables if any((row and str(row[0]).startswith("融資")) for row in table.get("data", []))),
                None,
            )
            if summary_table:
                fields = summary_table.get("fields") or []
                rows = summary_table.get("data") or []
                item_idx = _pick_field(fields, ["項目"])
                prev_idx = _pick_field(fields, ["前日餘額"])
                bal_idx = _pick_field(fields, ["今日餘額"])
                buy_idx = _pick_field(fields, ["買進"])
                sell_idx = _pick_field(fields, ["賣出"])
                finance_row = next(
                    (row for row in rows if item_idx is not None and item_idx < len(row) and str(row[item_idx]).startswith("融資(")),
                    None,
                )
                amount_row = next(
                    (row for row in rows if item_idx is not None and item_idx < len(row) and str(row[item_idx]).startswith("融資金額")),
                    None,
                )
                if finance_row and bal_idx is not None:
                    return {
                        "date": data.get("date") or date.isoformat(),
                        "market": "TWSE",
                        "finance_balance_lots": _int(finance_row[bal_idx]),
                        "previous_balance_lots": _int(finance_row[prev_idx]) if prev_idx is not None else None,
                        "finance_buy_lots": _int(finance_row[buy_idx]) if buy_idx is not None else None,
                        "finance_sell_lots": _int(finance_row[sell_idx]) if sell_idx is not None else None,
                        "finance_balance_thousand_twd": _int(amount_row[bal_idx]) if amount_row and bal_idx is not None else None,
                        "previous_balance_thousand_twd": _int(amount_row[prev_idx]) if amount_row and prev_idx is not None else None,
                        "finance_buy_thousand_twd": _int(amount_row[buy_idx]) if amount_row and buy_idx is not None else None,
                        "finance_sell_thousand_twd": _int(amount_row[sell_idx]) if amount_row and sell_idx is not None else None,
                        "stock_count": None,
                        "source": "twse_mi_margn",
                    }

            fields = data.get("fields") or data.get("field") or []
            rows = data.get("data") or []
            if not fields or not rows:
                continue

            code_idx = _pick_field(fields, ["股票代號", "證券代號", "代號"])
            prev_idx = _pick_field(fields, ["前日餘額", "融資前日餘額", "昨日融資餘額"])
            bal_idx = _pick_field(fields, ["今日餘額", "融資今日餘額", "今日融資餘額", "融資餘額"])
            buy_idx = _pick_field(fields, ["買進", "融資買進", "今日融資買進"])
            sell_idx = _pick_field(fields, ["賣出", "融資賣出", "今日融資賣出"])
            if bal_idx is None:
                continue

            total_balance = 0
            total_prev = 0
            total_buy = 0
            total_sell = 0
            count = 0
            for row in rows:
                if code_idx is not None and not re.match(r"^\d{4,6}[A-Z]?$", str(row[code_idx]).strip()):
                    continue
                balance = _int(row[bal_idx] if bal_idx < len(row) else None)
                if balance is None:
                    continue
                total_balance += balance
                total_prev += _int(row[prev_idx] if prev_idx is not None and prev_idx < len(row) else None) or 0
                total_buy += _int(row[buy_idx] if buy_idx is not None and buy_idx < len(row) else None) or 0
                total_sell += _int(row[sell_idx] if sell_idx is not None and sell_idx < len(row) else None) or 0
                count += 1

            if count:
                return {
                    "date": data.get("date") or date.isoformat(),
                    "market": "TWSE",
                    "finance_balance_lots": total_balance,
                    "previous_balance_lots": total_prev or None,
                    "finance_buy_lots": total_buy or None,
                    "finance_sell_lots": total_sell or None,
                    "stock_count": count,
                    "source": "twse_mi_margn",
                }
        except Exception as exc:
            print(f"  warning: TWSE {date_text} failed via {url}: {exc}")
    return None


def fetch_tpex(date: datetime.date) -> dict[str, Any] | None:
    try:
        res = requests.get(
            "https://www.tpex.org.tw/www/zh-tw/margin/balance",
            params={"date": _roc_date(date), "response": "json"},
            headers=HEADERS,
            timeout=25,
        )
        res.raise_for_status()
        data = res.json()
        tables = data.get("tables") or []
        table = tables[0] if tables else {}
        summary = table.get("summary") or []
        if not summary:
            return None
        lots_row = next((row for row in summary if len(row) > 1 and "合計" in str(row[1])), None)
        amount_row = next((row for row in summary if len(row) > 1 and "融資金" in str(row[1])), None)
        if not lots_row:
            return None
        return {
            "date": data.get("date") or date.isoformat(),
            "market": "TPEX",
            "finance_balance_lots": _int(lots_row[6]) if len(lots_row) > 6 else None,
            "previous_balance_lots": _int(lots_row[2]) if len(lots_row) > 2 else None,
            "finance_buy_lots": _int(lots_row[3]) if len(lots_row) > 3 else None,
            "finance_sell_lots": _int(lots_row[4]) if len(lots_row) > 4 else None,
            "finance_balance_thousand_twd": _int(amount_row[6]) if amount_row and len(amount_row) > 6 else None,
            "previous_balance_thousand_twd": _int(amount_row[2]) if amount_row and len(amount_row) > 2 else None,
            "finance_buy_thousand_twd": _int(amount_row[3]) if amount_row and len(amount_row) > 3 else None,
            "finance_sell_thousand_twd": _int(amount_row[4]) if amount_row and len(amount_row) > 4 else None,
            "stock_count": table.get("totalCount"),
            "source": "tpex_margin_balance",
        }
    except Exception as exc:
        print(f"  warning: TPEX {_roc_date(date)} failed: {exc}")
        return None


def merge_history(existing: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_date: dict[str, dict[str, Any]] = {}
    for row in existing.get("history", []):
        if row.get("date"):
            by_date[row["date"]] = row
    for row in rows:
        by_date[row["date"]] = row
    return [by_date[key] for key in sorted(by_date.keys())][-90:]


def main() -> int:
    existing = _load_existing()
    rows: list[dict[str, Any]] = []
    for date in reversed(_latest_weekdays(14)):
        twse = fetch_twse(date)
        tpex = fetch_tpex(date)
        if not twse and not tpex:
            continue
        total = (twse or {}).get("finance_balance_lots", 0) + (tpex or {}).get("finance_balance_lots", 0)
        prev = (twse or {}).get("previous_balance_lots", 0) + (tpex or {}).get("previous_balance_lots", 0)
        amount = (twse or {}).get("finance_balance_thousand_twd", 0) + (tpex or {}).get("finance_balance_thousand_twd", 0)
        amount_prev = (twse or {}).get("previous_balance_thousand_twd", 0) + (tpex or {}).get("previous_balance_thousand_twd", 0)
        rows.append({
            "date": date.isoformat(),
            "total_finance_balance_lots": total or None,
            "total_change_lots": (total - prev) if total and prev else None,
            "total_finance_balance_thousand_twd": amount or None,
            "total_change_thousand_twd": (amount - amount_prev) if amount and amount_prev else None,
            "twse_finance_balance_lots": (twse or {}).get("finance_balance_lots"),
            "tpex_finance_balance_lots": (tpex or {}).get("finance_balance_lots"),
            "twse_finance_balance_thousand_twd": (twse or {}).get("finance_balance_thousand_twd"),
            "tpex_finance_balance_thousand_twd": (tpex or {}).get("finance_balance_thousand_twd"),
            "twse": twse,
            "tpex": tpex,
        })

    history = merge_history(existing, rows)
    latest = history[-1] if history else None
    out = {
        "date": latest.get("date") if latest else None,
        "updated": NOW.isoformat(),
        "source": "twse_mi_margn+tpex_margin_balance",
        "summary": latest or {},
        "history": history,
        "definition": "上市與上櫃市場融資餘額合計；金額單位為仟元，前端換算為億元。用於觀察市場槓桿與情緒是否升溫。",
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"margin balance updated: {out['date']} rows={len(history)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
