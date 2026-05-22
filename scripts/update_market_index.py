#!/usr/bin/env python3
"""
更新大盤指數快取。

優先使用 TWSE / TPEx 官方盤後資料；若官方端點暫時不可用，保留 yfinance
備援，避免前端儀表板空白。輸出：data/market_index.json
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
OUTPUT_PATH = os.path.join(DATA_DIR, "market_index.json")
PERFORMANCE_PATH = os.path.join(DATA_DIR, "performance.json")
HISTORY_LIMIT = 520

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


def _parse_date(value: Any) -> datetime.date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None


def _month_starts(start: datetime.date, end: datetime.date) -> list[datetime.date]:
    current = start.replace(day=1)
    months = []
    while current <= end:
        months.append(current)
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    return months


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


def fetch_txf_near_from_yahoo() -> dict[str, Any] | None:
    """
    Yahoo 台指期近一報價。

    這個頁面在夜盤收盤後會保留 05:00 左右的近月台指期成交價，
    適合放在行情儀錶板補足台股開盤前的夜盤結果。
    """
    url = "https://tw.stock.yahoo.com/future/futures.html?fumr=futurefull"
    try:
        from bs4 import BeautifulSoup

        res = requests.get(url, headers=HEADERS, timeout=20)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        text = soup.get_text("\n")
        tokens = [line.strip() for line in text.splitlines() if line.strip()]
        date_match = re.search(r"資料時間[:：]\s*(\d{4}/\d{1,2}/\d{1,2})", text)
        quote_date = _roc_date(date_match.group(1)) if date_match else TODAY.isoformat()

        for idx, token in enumerate(tokens):
            if token != "台指期近一":
                continue
            row = tokens[idx + 1:idx + 16]
            if not row or row[0] != "WTX&":
                continue
            close = _num(row[3] if len(row) > 3 else None)
            change = _num(row[4] if len(row) > 4 else None)
            change_pct = _num(str(row[5]).replace("%", "") if len(row) > 5 else None)
            if close is None:
                continue
            item: dict[str, Any] = {
                "name": "台指近全",
                "close": close,
                "date": quote_date,
                "source": "yahoo_futures",
            }
            if change is not None:
                item["change"] = change
            if change_pct is not None:
                item["change_pct"] = change_pct
            if len(row) > 13:
                item["time"] = row[13]
            return item
    except Exception as exc:
        print(f"  ⚠️  Yahoo 台指期近一讀取失敗：{exc}")
    return None


def fetch_taiex_history_from_twse(start_date: datetime.date) -> dict[str, float]:
    """Fetch TAIEX daily closes from TWSE monthly history, starting at start_date."""
    urls = [
        "https://www.twse.com.tw/rwd/zh/TAI/MI_5MINS_HIST",
        "https://www.twse.com.tw/indicesReport/MI_5MINS_HIST",
    ]
    history: dict[str, float] = {}
    for month_start in _month_starts(start_date, TODAY):
        for url in urls:
            data = _fetch_json(url, {"date": _twse_date(month_start), "response": "json"})
            rows = data.get("data") if data else None
            if not rows:
                continue
            for row in rows:
                if not isinstance(row, list) or len(row) < 5:
                    continue
                date = _parse_date(_roc_date(str(row[0])))
                close = _num(row[4])
                if date is None or close is None or date < start_date or date > TODAY:
                    continue
                history[date.isoformat()] = close
            break
        time.sleep(0.12)
    return history


def fetch_taiex_history_from_yfinance(start_date: datetime.date) -> dict[str, float]:
    try:
        import yfinance as yf

        hist = yf.Ticker("^TWII").history(
            start=start_date.isoformat(),
            end=(TODAY + timedelta(days=1)).isoformat(),
            interval="1d",
            auto_adjust=False,
        )
        if hist.empty:
            return {}
        result: dict[str, float] = {}
        valid = hist.dropna(subset=["Close"])
        for idx, row in valid.iterrows():
            result[idx.strftime("%Y-%m-%d")] = round(float(row["Close"]), 2)
        return result
    except Exception as exc:
        print(f"  ⚠️  yfinance ^TWII history 讀取失敗：{exc}")
        return {}


def fetch_first_yfinance(symbols: list[str], name: str) -> dict[str, Any] | None:
    for symbol in symbols:
        result = fetch_from_yfinance(symbol, name)
        if result:
            return result
    return None


def load_existing_history() -> dict[str, dict[str, float]]:
    if not os.path.exists(OUTPUT_PATH):
        return {}
    try:
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            data = json.load(f)
        history = data.get("history") or {}
        if isinstance(history, dict):
            return history
    except Exception:
        return {}
    return {}


def benchmark_start_date() -> datetime.date:
    dates: list[datetime.date] = []
    if os.path.exists(PERFORMANCE_PATH):
        try:
            with open(PERFORMANCE_PATH, encoding="utf-8") as f:
                data = json.load(f)
            for position in data.get("positions", []):
                for key in ("entry_date", "exit_date"):
                    d = _parse_date(position.get(key))
                    if d:
                        dates.append(d)
                for ex in position.get("exits", []) or []:
                    d = _parse_date(ex.get("date"))
                    if d:
                        dates.append(d)
            for hist in (data.get("price_history") or {}).values():
                if isinstance(hist, dict):
                    for d in hist:
                        parsed = _parse_date(d)
                        if parsed:
                            dates.append(parsed)
        except Exception as exc:
            print(f"  ⚠️  performance 起始日期讀取失敗：{exc}")
    if dates:
        return min(dates)
    return TODAY - timedelta(days=90)


def update_history(indices: dict[str, dict[str, Any]]) -> dict[str, dict[str, float]]:
    history = load_existing_history()
    start_date = benchmark_start_date()
    taiex_history = fetch_taiex_history_from_twse(start_date)
    if not taiex_history:
        taiex_history = fetch_taiex_history_from_yfinance(start_date)
    if taiex_history:
        series = history.setdefault("TAIEX", {})
        series.update(taiex_history)
        print(f"  ✅ TAIEX history：{len(taiex_history)} 筆（from {start_date.isoformat()}）")
    for key in ("TAIEX", "TPEX"):
        item = indices.get(key) or {}
        date = item.get("date")
        close = _num(item.get("close"))
        if not date or close is None:
            continue
        series = history.setdefault(key, {})
        series[str(date)[:10]] = close
        kept_dates = sorted(series)[-HISTORY_LIMIT:]
        history[key] = {d: series[d] for d in kept_dates}
    return history


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
    txf_near = fetch_txf_near_from_yahoo()
    nasdaq = fetch_from_yfinance("^IXIC", "那斯達克")
    dow = fetch_from_yfinance("^DJI", "道瓊")
    sox = fetch_from_yfinance("^SOX", "費半")

    market_items = {
        "TAIEX": taiex,
        "TPEX": tpex,
        "TXF_NEAR": txf_near,
        "NASDAQ": nasdaq,
        "DOW": dow,
        "SOX": sox,
    }
    indices = {key: value for key, value in market_items.items() if value}

    if not indices:
        raise SystemExit("❌ 無法取得任何大盤指數資料")

    dates = [x["date"] for x in indices.values() if x.get("date")]
    out = {
        "date": max(dates) if dates else TODAY.isoformat(),
        "updated": NOW.isoformat(),
        "source": "+".join(sorted({x["source"] for x in indices.values()})),
        "indices": indices,
        "history": update_history(indices),
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"  ✅ 已輸出 market_index.json：{out['date']} ({out['source']})")


if __name__ == "__main__":
    main()
