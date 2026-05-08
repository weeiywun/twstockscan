#!/usr/bin/env python3
"""
更新 FUTURE DASHBOARD 快取。

資料來源以官方期交所與證交所為主：
- 期交所：三大法人期貨日盤 / 夜盤、期貨每日行情下載
- 期交所 open data：期貨每日行情、臺指選擇權 Put/Call Ratio
- 證交所 BFI82U：三大法人現貨買賣金額
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from bs4 import BeautifulSoup


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
OUTPUT_PATH = os.path.join(DATA_DIR, "futures_dashboard.json")

TW_TZ = timezone(timedelta(hours=8))
NOW = datetime.now(TW_TZ)
TODAY = NOW.date()

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/html,text/csv,application/json,*/*",
}

TAIFEX_BQ = "https://www.bq888.taifex.com.tw"
TAIFEX_WEB = "https://www.taifex.com.tw"
TAIFEX_DATA = "https://www.taifex.com.tw/data_gov/taifex_open_data.asp"
INVESTOR_KEYS = {
    "自營商": "dealer",
    "投信": "investment_trust",
    "外資": "foreign",
}
INVESTOR_LABELS = {
    "dealer": "自營商",
    "investment_trust": "投信",
    "foreign": "外資",
    "total": "三大法人合計",
}


def _num(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("%", "")
    text = text.replace("▲", "").replace("▼", "")
    if not text or text in {"-", "--", "NULL", "NaN"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _int(value: Any) -> int | None:
    n = _num(value)
    return int(round(n)) if n is not None else None


def _date_slash(date: datetime.date) -> str:
    return date.strftime("%Y/%m/%d")


def _date_dash(date_text: str | None) -> str | None:
    if not date_text:
        return None
    text = str(date_text).strip()
    if re.fullmatch(r"\d{8}", text):
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    parts = re.split(r"[/-]", text)
    if len(parts) == 3:
        return f"{int(parts[0]):04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"
    return text


def _request_text(url: str, params: dict[str, str] | None = None, encoding: str = "utf-8") -> str:
    res = requests.get(url, params=params, headers=HEADERS, timeout=25)
    res.raise_for_status()
    if isinstance(res.content, bytes):
        return res.content.decode(encoding, errors="replace")
    return str(res.text)


def _post_text(url: str, data: dict[str, str], encoding: str = "utf-8") -> str:
    res = requests.post(url, data=data, headers=HEADERS, timeout=25)
    res.raise_for_status()
    return res.content.decode(encoding, errors="replace")


def _latest_trading_dates(max_days: int = 10) -> list[datetime.date]:
    dates: list[datetime.date] = []
    for offset in range(0, max_days):
        d = TODAY - timedelta(days=offset)
        if d.weekday() < 5:
            dates.append(d)
    return dates


def _twse_date(date: datetime.date) -> str:
    return date.strftime("%Y%m%d")


def _trend(current: float | int | None, previous: float | int | None) -> str | None:
    if current is None or previous is None:
        return None
    if current > previous:
        return "上升"
    if current < previous:
        return "下降"
    return "持平"


def _parse_taifex_institutional_table(html: str, source: str = "taifex_bq888") -> dict[str, Any] | None:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    m = re.search(r"日期\s*:?\s*(\d{4}/\d{2}/\d{2})", text)
    data_date = _date_dash(m.group(1)) if m else None
    result: dict[str, Any] = {"date": data_date, "contracts": {}, "source": source}
    current_product = ""

    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        cells = [c for c in cells if c]
        if not cells:
            continue
        if cells[0].isdigit() and len(cells) >= 4:
            current_product = cells[1]
            trader = cells[2]
            nums = cells[3:]
        elif current_product and cells[0] in INVESTOR_KEYS:
            trader = cells[0]
            nums = cells[1:]
        else:
            continue
        key = INVESTOR_KEYS.get(trader)
        if not key:
            continue
        values = [_int(x) for x in nums]
        contract = result["contracts"].setdefault(current_product, {"traders": {}})
        item: dict[str, Any] = {
            "label": trader,
            "buy_lots": values[0] if len(values) > 0 else None,
            "sell_lots": values[2] if len(values) > 2 else None,
            "net_lots": values[4] if len(values) > 4 else None,
        }
        if len(values) >= 12:
            item.update({
                "oi_long_lots": values[6],
                "oi_short_lots": values[8],
                "oi_net_lots": values[10],
            })
        contract["traders"][key] = item

    for contract in result["contracts"].values():
        total: dict[str, Any] = {"label": "三大法人合計"}
        for field in ("buy_lots", "sell_lots", "net_lots", "oi_long_lots", "oi_short_lots", "oi_net_lots"):
            vals = [v.get(field) for v in contract["traders"].values() if v.get(field) is not None]
            total[field] = sum(vals) if vals else None
        contract["traders"]["total"] = total
    return result if result["contracts"] else None


def fetch_taifex_institutional(path: str) -> dict[str, Any] | None:
    try:
        html = _request_text(f"{TAIFEX_BQ}/cht/3/{path}", encoding="utf-8")
        return _parse_taifex_institutional_table(html)
    except Exception as exc:
        print(f"  ⚠️  期交所 {path} 讀取失敗：{exc}")
        return None


def fetch_taifex_day_institutional(date_text: str | None = None) -> dict[str, Any] | None:
    try:
        if date_text:
            html = _post_text(
                f"{TAIFEX_WEB}/cht/3/futContractsDate",
                {
                    "queryDate": date_text.replace("-", "/"),
                    "commodityId": "",
                    "queryType": "",
                    "goDay": "",
                    "doQuery": "1",
                    "dateaddcnt": "",
                },
                encoding="utf-8",
            )
        else:
            html = _request_text(f"{TAIFEX_WEB}/cht/3/futContractsDate", encoding="utf-8")
        return _parse_taifex_institutional_table(html, source="taifex_futContractsDate")
    except Exception as exc:
        label = date_text or "latest"
        print(f"  ⚠️  期交所 futContractsDate {label} 讀取失敗：{exc}")
        return None


def fetch_taifex_night_institutional() -> dict[str, Any] | None:
    try:
        html = _request_text(f"{TAIFEX_WEB}/cht/3/futContractsDateAh", encoding="utf-8")
        return _parse_taifex_institutional_table(html, source="taifex_futContractsDateAh")
    except Exception as exc:
        print(f"  ⚠️  期交所 futContractsDateAh 夜盤讀取失敗：{exc}")
        return None


def fetch_futures_daily_market() -> dict[str, Any] | None:
    try:
        text = _request_text(
            TAIFEX_DATA,
            {"data_name": "DailyMarketReportFut"},
            encoding="big5",
        )
        rows = list(csv.reader(io.StringIO(text)))
        if len(rows) < 2:
            return None
        by_symbol: dict[str, dict[str, Any]] = {}
        totals: dict[str, dict[str, Any]] = {}
        for row in rows[1:]:
            if len(row) < 12:
                continue
            trade_date = _date_dash(row[0])
            symbol = row[1].strip()
            month = row[2].strip()
            close = _num(row[6])
            volume = _int(row[9])
            settlement = _num(row[10])
            open_interest = _int(row[11])
            session = row[-1].strip() if row else ""
            if symbol not in {"TX", "MTX", "TMF"} or open_interest is None:
                continue
            total = totals.setdefault(symbol, {"symbol": symbol, "date": trade_date, "open_interest_total": 0})
            total["open_interest_total"] += open_interest
            if symbol not in by_symbol:
                by_symbol[symbol] = {
                    "symbol": symbol,
                    "date": trade_date,
                    "front_month": month,
                    "close": close,
                    "settlement": settlement,
                    "volume": volume,
                    "open_interest": open_interest,
                    "source": "taifex_open_data",
                }
        for symbol, item in totals.items():
            if symbol in by_symbol:
                by_symbol[symbol]["open_interest_total"] = item["open_interest_total"]
            else:
                by_symbol[symbol] = {
                    **item,
                    "source": "taifex_open_data",
                }
        return by_symbol if by_symbol else None
    except Exception as exc:
        print(f"  ⚠️  期貨每日行情讀取失敗：{exc}")
        return None


def fetch_futures_market_history(symbols: tuple[str, ...] = ("MTX", "TMF"), days: int = 5) -> dict[str, list[dict[str, Any]]]:
    start = _latest_trading_dates(14)[-1]
    end = _latest_trading_dates(14)[0]
    history: dict[str, list[dict[str, Any]]] = {symbol: [] for symbol in symbols}
    for symbol in symbols:
        try:
            text = _post_text(
                f"{TAIFEX_WEB}/cht/3/futDataDown",
                {
                    "down_type": "1",
                    "queryStartDate": _date_slash(start),
                    "queryEndDate": _date_slash(end),
                    "commodity_id": symbol,
                    "commodity_id2": "",
                },
                encoding="big5",
            )
            rows = list(csv.reader(io.StringIO(text)))
            by_date: dict[str, dict[str, Any]] = {}
            for row in rows[1:]:
                if len(row) < 12:
                    continue
                date = _date_dash(row[0])
                open_interest = _int(row[11])
                if not date or open_interest is None:
                    continue
                item = by_date.setdefault(date, {
                    "symbol": symbol,
                    "date": date,
                    "open_interest_total": 0,
                    "source": "taifex_futDataDown",
                })
                item["open_interest_total"] += open_interest
            history[symbol] = sorted(by_date.values(), key=lambda x: x["date"], reverse=True)[:days]
        except Exception as exc:
            print(f"  ⚠️  期貨每日行情歷史 {symbol} 讀取失敗：{exc}")
    return history


def fetch_pc_ratio(days: int = 5) -> dict[str, Any] | None:
    try:
        text = _request_text(TAIFEX_DATA, {"data_name": "PutCallRatio"}, encoding="big5")
        rows = list(csv.reader(io.StringIO(text)))
        if len(rows) < 2:
            return None
        history = []
        for row in rows[1:days + 1]:
            history.append({
                "date": _date_dash(row[0]),
                "put_volume": _int(row[1]),
                "call_volume": _int(row[2]),
                "volume_ratio": _num(row[3]),
                "put_open_interest": _int(row[4]),
                "call_open_interest": _int(row[5]),
                "open_interest_ratio": _num(row[6]),
                "ratio": round((_num(row[6]) or 0) / 100, 2) if _num(row[6]) is not None else None,
                "source": "taifex_open_data",
            })
        latest = history[0]
        return {
            **latest,
            "history": history,
            "previous_ratio": history[1]["ratio"] if len(history) > 1 else None,
            "change": round(latest["ratio"] - history[1]["ratio"], 2) if len(history) > 1 and latest["ratio"] is not None and history[1]["ratio"] is not None else None,
            "trend": _trend(latest["ratio"], history[1]["ratio"]) if len(history) > 1 else None,
        }
    except Exception as exc:
        print(f"  ⚠️  Put/Call Ratio 讀取失敗：{exc}")
        return None


def _legacy_pc_ratio(pc_ratio: dict[str, Any] | None) -> dict[str, Any] | None:
    if not pc_ratio:
        return None
    return {
        key: pc_ratio.get(key)
        for key in (
            "date",
            "put_volume",
            "call_volume",
            "volume_ratio",
            "put_open_interest",
            "call_open_interest",
            "open_interest_ratio",
            "source",
        )
        if key in pc_ratio
    }


def fetch_twse_institutional_amount(date: datetime.date) -> dict[str, Any] | None:
    url = "https://www.twse.com.tw/rwd/zh/fund/BFI82U"
    try:
        res = requests.get(url, params={
            "dayDate": _twse_date(date),
            "response": "json",
            "type": "day",
        }, headers=HEADERS, timeout=25)
        res.raise_for_status()
        data = res.json()
        if data.get("stat") != "OK" or not data.get("data"):
            return None
        totals = {
            "foreign": {"label": "外資", "buy_amount": 0, "sell_amount": 0, "net_amount": 0},
            "investment_trust": {"label": "投信", "buy_amount": 0, "sell_amount": 0, "net_amount": 0},
            "dealer": {"label": "自營商", "buy_amount": 0, "sell_amount": 0, "net_amount": 0},
        }
        for row in data.get("data", []):
            name = row[0]
            key = None
            if "外資及陸資" in name:
                key = "foreign"
            elif name == "投信":
                key = "investment_trust"
            elif name.startswith("自營商"):
                key = "dealer"
            if not key:
                continue
            buy = _int(row[1]) or 0
            sell = _int(row[2]) or 0
            net = _int(row[3]) if len(row) > 3 else buy - sell
            totals[key]["buy_amount"] += buy
            totals[key]["sell_amount"] += sell
            totals[key]["net_amount"] += net if net is not None else buy - sell
        total = {"label": "三大法人合計", "buy_amount": 0, "sell_amount": 0, "net_amount": 0}
        for item in totals.values():
            total["buy_amount"] += item["buy_amount"]
            total["sell_amount"] += item["sell_amount"]
            total["net_amount"] += item["net_amount"]
        totals["total"] = total
        return {
            "date": _date_dash(data.get("date")) or date.isoformat(),
            "traders": totals,
            "source": "twse_bfi82u",
            "unit": "TWD",
        }
    except Exception as exc:
        print(f"  ⚠️  TWSE BFI82U {date.isoformat()} 讀取失敗：{exc}")
        return None


def fetch_stock_institutional_amounts(days: int = 5) -> dict[str, Any] | None:
    history: list[dict[str, Any]] = []
    for d in _latest_trading_dates(14):
        item = fetch_twse_institutional_amount(d)
        if item:
            history.append(item)
        if len(history) >= days:
            break
    if not history:
        return None
    return {
        "date": history[0]["date"],
        "history": history,
        "source": "twse_bfi82u",
        "unit": "TWD",
    }
    return None


def _contract_view(data: dict[str, Any] | None, product: str) -> dict[str, Any] | None:
    if not data:
        return None
    contract = (data.get("contracts") or {}).get(product)
    if not contract:
        return None
    return {
        "date": data.get("date"),
        "product": product,
        "traders": contract.get("traders", {}),
        "source": data.get("source"),
    }


def _retail_ratio(contract: dict[str, Any] | None, market_item: dict[str, Any] | None, symbol: str | None = None) -> dict[str, Any] | None:
    if not contract or not market_item:
        return None
    total = (contract.get("traders") or {}).get("total", {})
    oi = market_item.get("open_interest_total") or market_item.get("open_interest")
    inst_net = total.get("oi_net_lots")
    if not oi or inst_net is None:
        return None
    ratio = round(-inst_net / oi * 100, 2)
    return {
        "date": contract.get("date") or market_item.get("date"),
        "symbol": symbol or market_item.get("symbol"),
        "contract": contract.get("product"),
        "institutional_net_open_interest": inst_net,
        "estimated_retail_net_open_interest": -inst_net,
        "market_open_interest": oi,
        "ratio": ratio,
        "definition": "三大法人淨未平倉反向值 / 全市場全月份未沖銷契約數；正值代表散戶相對偏多。",
        "source": "taifex_derived",
    }


def _retail_rows(
    institutional_history: dict[str, dict[str, Any]],
    market_history: dict[str, list[dict[str, Any]]],
    pc_ratio: dict[str, Any] | None,
) -> dict[str, Any] | None:
    products = {
        "MTX": {"label": "小台散戶多空比", "product": "小型臺指期貨"},
        "TMF": {"label": "微台散戶多空比", "product": "微型臺指期貨"},
    }
    rows: list[dict[str, Any]] = []
    dates: list[str] = []
    for symbol, meta in products.items():
        history: list[dict[str, Any]] = []
        for market_item in market_history.get(symbol, []):
            inst = institutional_history.get(market_item["date"])
            contract = _contract_view(inst, meta["product"])
            ratio = _retail_ratio(contract, market_item, symbol)
            if ratio:
                history.append(ratio)
        if not history:
            continue
        current = history[0]
        previous = history[1] if len(history) > 1 else {}
        rows.append({
            "key": symbol.lower(),
            "label": meta["label"],
            "format": "percent",
            "today": current.get("ratio"),
            "previous": previous.get("ratio"),
            "change": round(current["ratio"] - previous["ratio"], 2) if previous.get("ratio") is not None else None,
            "trend": _trend(current.get("ratio"), previous.get("ratio")),
            "date": current.get("date"),
            "previous_date": previous.get("date"),
            "detail": current,
            "history": history,
        })
        if current.get("date"):
            dates.append(current["date"])

    pc_history = pc_ratio.get("history") if pc_ratio else []
    if pc_history:
        current_pc = pc_history[0]
        previous_pc = pc_history[1] if len(pc_history) > 1 else {}
        rows.append({
            "key": "pc_ratio",
            "label": "Put/Call Ratio",
            "format": "decimal",
            "today": current_pc.get("ratio"),
            "previous": previous_pc.get("ratio"),
            "change": round(current_pc["ratio"] - previous_pc["ratio"], 2) if previous_pc.get("ratio") is not None else None,
            "trend": _trend(current_pc.get("ratio"), previous_pc.get("ratio")),
            "date": current_pc.get("date"),
            "previous_date": previous_pc.get("date"),
            "detail": current_pc,
            "history": pc_history,
        })
        if current_pc.get("date"):
            dates.append(current_pc["date"])

    if not rows:
        return None
    return {
        "date": max(dates) if dates else None,
        "rows": rows,
        "source": "taifex_futContractsDate+taifex_futDataDown+taifex_open_data",
        "definition": "散戶多空比採國泰報告呈現邏輯：三大法人未平倉淨額反向值除以同商品全市場未沖銷契約數，並列今日、前一日與增減方向。",
    }


def _bias(data: dict[str, Any]) -> str:
    score = 0
    tx_total = (((data.get("futures") or {}).get("day_session") or {}).get("tx") or {}).get("traders", {}).get("total", {})
    night_total = (((data.get("futures") or {}).get("night_session") or {}).get("tx") or {}).get("traders", {}).get("total", {})
    retail = ((data.get("sentiment") or {}).get("retail_long_short") or {}).get("ratio")
    pc_oi = ((data.get("sentiment") or {}).get("pc_ratio") or {}).get("open_interest_ratio")
    if (tx_total.get("oi_net_lots") or 0) > 0:
        score += 1
    elif (tx_total.get("oi_net_lots") or 0) < 0:
        score -= 1
    if (night_total.get("net_lots") or 0) > 0:
        score += 1
    elif (night_total.get("net_lots") or 0) < 0:
        score -= 1
    if retail is not None:
        score += -1 if retail > 12 else 1 if retail < -12 else 0
    if pc_oi is not None:
        score += 1 if pc_oi > 130 else -1 if pc_oi < 90 else 0
    if score >= 2:
        return "偏多"
    if score <= -2:
        return "偏空"
    return "中性"


def main() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    print(f"=== 更新 FUTURE DASHBOARD {NOW.strftime('%Y-%m-%d %H:%M')} ===")

    day_institutional = fetch_taifex_day_institutional()
    night_institutional = fetch_taifex_night_institutional()
    market = fetch_futures_daily_market()
    pc_ratio = fetch_pc_ratio()
    market_history = fetch_futures_market_history()
    stock_inst = fetch_stock_institutional_amounts()

    institutional_history: dict[str, dict[str, Any]] = {}
    for row in (pc_ratio.get("history", [])[:5] if pc_ratio else []):
        date = row.get("date")
        if not date:
            continue
        if day_institutional and day_institutional.get("date") == date:
            institutional_history[date] = day_institutional
        else:
            inst = fetch_taifex_day_institutional(date)
            if inst:
                institutional_history[date] = inst

    tx_day = _contract_view(day_institutional, "臺股期貨")
    mtx_day = _contract_view(day_institutional, "小型臺指期貨")
    tmf_day = _contract_view(day_institutional, "微型臺指期貨")
    tx_night = _contract_view(night_institutional, "臺股期貨")
    mtx_night = _contract_view(night_institutional, "小型臺指期貨")
    tmf_night = _contract_view(night_institutional, "微型臺指期貨")
    retail_dashboard = _retail_rows(institutional_history, market_history, pc_ratio)
    retail = (retail_dashboard.get("rows", [{}])[0].get("detail") if retail_dashboard else None) or _retail_ratio(mtx_day, (market or {}).get("MTX"), "MTX")

    dates = [
        x.get("date") for x in
        (tx_day, mtx_day, tmf_day, tx_night, mtx_night, tmf_night, retail, pc_ratio, stock_inst)
        if x and x.get("date")
    ]
    out = {
        "date": max(dates) if dates else TODAY.isoformat(),
        "updated": NOW.isoformat(),
        "source": "taifex_futContractsDate+taifex_futContractsDateAh+taifex_futDataDown+taifex_open_data" + ("+twse_bfi82u" if stock_inst else ""),
        "market": market or {},
        "stock_institutional": stock_inst,
        "futures": {
            "day_session": {
                "tx": tx_day,
                "mtx": mtx_day,
                "tmf": tmf_day,
            },
            "night_session": {
                "tx": tx_night,
                "mtx": mtx_night,
                "tmf": tmf_night,
            },
        },
        "sentiment": {
            "retail_long_short": retail,
            "retail_dashboard": retail_dashboard,
            "pc_ratio": pc_ratio,
        },
        "summary": {},
    }
    out["summary"] = {
        "bias": _bias(out),
        "notes": [
            "夜盤法人為期交所三大法人夜盤頁面資料，日期以盤後交易量歸屬日為準。",
            "散戶多空比以三大法人淨未平倉反向值 / 全市場全月份未沖銷契約數估算；正值代表散戶相對偏多。",
        ],
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"  ✅ 已輸出 futures_dashboard.json：{out['date']} ({out['summary']['bias']})")


if __name__ == "__main__":
    main()
