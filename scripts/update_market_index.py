#!/usr/bin/env python3
"""
更新大盤指數快取。

優先使用 TWSE / TPEx 官方盤後資料；若官方端點暫時不可用，保留 yfinance
備援，避免前端儀表板空白。輸出：data/market_index.json
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
OUTPUT_PATH = os.path.join(DATA_DIR, "market_index.json")

TW_TZ = timezone(timedelta(hours=8))
NOW = datetime.now(TW_TZ)
TODAY = NOW.date()

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json,text/html,*/*",
}
MIS_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        text = str(value).strip().replace(",", "")
        if not text or text in {"--", "-", "NaN"}:
            return None
        return round(float(text), 2)
    except ValueError:
        return None


def _with_change(item: dict[str, Any], previous_close: float | None) -> dict[str, Any]:
    close = _num(item.get("close"))
    if close is None or previous_close is None or previous_close == 0:
        return item
    change = round(close - previous_close, 2)
    item["change"] = change
    item["change_pct"] = round(change / previous_close * 100, 2)
    item["previous_close"] = round(previous_close, 2)
    return item


def _twse_date(date: datetime.date) -> str:
    return date.strftime("%Y%m%d")


def _roc_date(date_text: str) -> str:
    parts = date_text.replace("-", "/").split("/")
    if len(parts) != 3:
        return date_text
    year = int(parts[0])
    if year < 1911:
        year += 1911
    return f"{year:04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"


def _fetch_json(url: str, params: dict[str, str]) -> dict[str, Any] | None:
    try:
        res = requests.get(url, params=params, headers=HEADERS, timeout=20)
        res.raise_for_status()
        return res.json()
    except Exception as exc:
        print(f"  ⚠️  {url} 讀取失敗：{exc}")
        return None


def _previous_weekday(date: datetime.date) -> datetime.date:
    d = date - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _after_market_close() -> bool:
    return NOW.hour > 14 or (NOW.hour == 14 and NOW.minute >= 30)


def fetch_from_mis_indices() -> dict[str, dict[str, Any]]:
    """
    TWSE MIS 大盤代碼備援。

    盤中使用 y（昨收），避免顯示即時價；盤後使用 z（最後成交，等同收盤）。
    """
    data = _fetch_json(
        MIS_URL,
        {"ex_ch": "tse_t00.tw|otc_o00.tw", "json": "1", "delay": "0"},
    )
    if not data:
        return {}
    result: dict[str, dict[str, Any]] = {}
    use_latest = _after_market_close()
    fallback_date = TODAY.isoformat() if use_latest else _previous_weekday(TODAY).isoformat()
    for item in data.get("msgArray", []):
        code = item.get("c")
        key = "TAIEX" if code == "t00" else "TPEX" if code == "o00" else ""
        if not key:
            continue
        previous_close = _num(item.get("y"))
        value = _num(item.get("z") if use_latest else item.get("y"))
        if value is None:
            value = _num(item.get("y") or item.get("z"))
        if value is None:
            continue
        result[key] = _with_change({
            "name": "台灣加權指數" if key == "TAIEX" else "櫃買加權指數",
            "close": value,
            "date": fallback_date,
            "source": "twse_mis",
        }, previous_close if use_latest else None)
    return result


def fetch_taiex_from_twse() -> dict[str, Any] | None:
    """TWSE 發行量加權股價指數歷史資料，往回找最近可用收盤值。"""
    urls = [
        "https://www.twse.com.tw/rwd/zh/TAI/MI_5MINS_HIST",
        "https://www.twse.com.tw/indicesReport/MI_5MINS_HIST",
    ]
    for offset in range(0, 45):
        target = TODAY - timedelta(days=offset)
        if target.weekday() >= 5:
            continue
        for url in urls:
            data = _fetch_json(url, {"date": _twse_date(target), "response": "json"})
            rows = data.get("data") if data else None
            if not rows:
                continue
            valid_rows = [
                row for row in rows
                if isinstance(row, list) and len(row) >= 5 and _num(row[4]) is not None
            ]
            for i in range(len(valid_rows) - 1, -1, -1):
                row = valid_rows[i]
                close = _num(row[4])
                if close is None:
                    continue
                previous_close = _num(valid_rows[i - 1][4]) if i > 0 else None
                return _with_change({
                    "name": "台灣加權指數",
                    "close": close,
                    "date": _roc_date(str(row[0])),
                    "source": "twse",
                }, previous_close)
        time.sleep(0.15)
    return None


def fetch_tpex_from_official() -> dict[str, Any] | None:
    """
    TPEx 櫃買指數歷史資料。

    TPEx 新舊站端點偶有調整，因此保留多組官方候選端點與常見欄位名稱。
    """
    candidates = [
        (
            "https://www.tpex.org.tw/www/zh-tw/afterTrading/otc",
            lambda d: {"date": d.strftime("%Y/%m/%d"), "response": "json"},
        ),
        (
            "https://www.tpex.org.tw/web/stock/aftertrading/index_result/summary_result.php",
            lambda d: {"l": "zh-tw", "d": f"{d.year - 1911}/{d.month:02d}/{d.day:02d}"},
        ),
    ]

    def _rows_from_payload(payload: dict[str, Any]) -> list[Any]:
        rows = payload.get("data") or payload.get("aaData") or []
        if rows:
            return rows
        tables = payload.get("tables") or []
        if isinstance(tables, dict):
            tables = [tables]
        for table in tables:
            if not isinstance(table, dict):
                continue
            rows = table.get("data") or table.get("rows") or []
            if rows:
                return rows
        return []

    for offset in range(0, 45):
        target = TODAY - timedelta(days=offset)
        if target.weekday() >= 5:
            continue
        for url, param_fn in candidates:
            data = _fetch_json(url, param_fn(target))
            if not data:
                continue
            rows = _rows_from_payload(data)
            if rows and isinstance(rows[0], dict):
                valid_rows = [
                    row for row in rows
                    if isinstance(row, dict) and _num(row.get("收市") or row.get("收盤") or row.get("close")) is not None
                ]
                for i in range(len(valid_rows) - 1, -1, -1):
                    row = valid_rows[i]
                    close = _num(row.get("收市") or row.get("收盤") or row.get("close"))
                    raw_date = row.get("資料日期") or row.get("date") or target.isoformat()
                    if close is not None:
                        prev_row = valid_rows[i - 1] if i > 0 else {}
                        previous_close = _num(prev_row.get("收市") or prev_row.get("收盤") or prev_row.get("close"))
                        return _with_change({
                            "name": "櫃買加權指數",
                            "close": close,
                            "date": _roc_date(str(raw_date)),
                            "source": "tpex",
                        }, previous_close)
            elif rows:
                valid_rows = [
                    row for row in rows
                    if isinstance(row, list) and len(row) >= 5 and _num(row[4]) is not None
                ]
                for i in range(len(valid_rows) - 1, -1, -1):
                    row = valid_rows[i]
                    close = _num(row[4])
                    if close is None:
                        continue
                    previous_close = _num(valid_rows[i - 1][4]) if i > 0 else None
                    return _with_change({
                        "name": "櫃買加權指數",
                        "close": close,
                        "date": _roc_date(str(row[0])),
                        "source": "tpex",
                    }, previous_close)
        time.sleep(0.15)
    return None


def fetch_from_yfinance(symbol: str, name: str) -> dict[str, Any] | None:
    try:
        import yfinance as yf

        hist = yf.Ticker(symbol).history(period="2mo", interval="1d", auto_adjust=False)
        if hist.empty:
            return None
        valid = hist.dropna(subset=["Close"])
        last = valid.iloc[-1]
        idx = valid.index[-1]
        previous_close = round(float(valid.iloc[-2]["Close"]), 2) if len(valid) >= 2 else None
        return _with_change({
            "name": name,
            "close": round(float(last["Close"]), 2),
            "date": idx.strftime("%Y-%m-%d"),
            "source": "yfinance",
        }, previous_close)
    except Exception as exc:
        print(f"  ⚠️  yfinance {symbol} 讀取失敗：{exc}")
        return None


def fetch_first_yfinance(symbols: list[str], name: str) -> dict[str, Any] | None:
    for symbol in symbols:
        result = fetch_from_yfinance(symbol, name)
        if result:
            return result
    return None


def main() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    print(f"=== 更新大盤指數 {NOW.strftime('%Y-%m-%d %H:%M')} ===")

    mis_indices = fetch_from_mis_indices()
    taiex = (
        fetch_taiex_from_twse()
        or mis_indices.get("TAIEX")
        or fetch_from_yfinance("^TWII", "台灣加權指數")
    )
    tpex = (
        fetch_tpex_from_official()
        or mis_indices.get("TPEX")
        or fetch_first_yfinance(["^TWOII", "TWOII.TW"], "櫃買加權指數")
    )

    if not taiex and not tpex:
        raise SystemExit("❌ 無法取得任何大盤指數資料")

    dates = [x["date"] for x in (taiex, tpex) if x and x.get("date")]
    out = {
        "date": max(dates) if dates else TODAY.isoformat(),
        "updated": NOW.isoformat(),
        "source": "+".join(sorted({x["source"] for x in (taiex, tpex) if x})),
        "indices": {
            "TAIEX": taiex,
            "TPEX": tpex,
        },
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"  ✅ 已輸出 market_index.json：{out['date']} ({out['source']})")


if __name__ == "__main__":
    main()
