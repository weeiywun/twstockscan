#!/usr/bin/env python3
"""
更新 FUTURE DASHBOARD 快取。

資料來源以官方期交所與證交所為主：
- 期交所：三大法人期貨日盤 / 夜盤、期貨每日行情下載
- 期交所 open data：期貨每日行情、臺指選擇權 Put/Call Ratio
- 證交所 BFI82U：三大法人現貨買賣金額
- CNN Fear & Greed：美股市場情緒
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
CNN_HEADERS = {
    **HEADERS,
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://edition.cnn.com",
    "Referer": "https://edition.cnn.com/markets/fear-and-greed",
}

TAIFEX_BQ = "https://www.bq888.taifex.com.tw"
TAIFEX_WEB = "https://www.taifex.com.tw"
TAIFEX_DATA = "https://www.taifex.com.tw/data_gov/taifex_open_data.asp"
CNN_FEAR_GREED = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
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


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _trend(current: float | int | None, previous: float | int | None) -> str | None:
    if current is None or previous is None:
        return None
    if current > previous:
        return "上升"
    if current < previous:
        return "下降"
    return "持平"


def _rating_zh(rating: str | None) -> str:
    mapping = {
        "extreme fear": "極度恐懼",
        "fear": "恐懼",
        "neutral": "中性",
        "greed": "貪婪",
        "extreme greed": "極度貪婪",
    }
    return mapping.get(str(rating or "").lower(), rating or "未知")


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


def fetch_vix(days: int = 5) -> dict[str, Any] | None:
    """從 stooq.com 取得 VIX 收盤價（不需 API key）。"""
    try:
        text = _request_text("https://stooq.com/q/d/l/?s=^vix&i=d")
        rows = list(csv.reader(io.StringIO(text)))
        # stooq CSV 格式：Date,Open,High,Low,Close,Volume（降序）
        history = []
        for row in rows[1:days + 1]:
            if len(row) < 5:
                continue
            close = _num(row[4])
            if close is None:
                continue
            history.append({"date": row[0], "close": close})
        if not history:
            return None
        latest = history[0]
        prev_close = history[1]["close"] if len(history) > 1 else None
        return {
            "date": latest["date"],
            "close": latest["close"],
            "change": round(latest["close"] - prev_close, 2) if prev_close is not None else None,
            "history": history,
            "source": "stooq",
        }
    except Exception as exc:
        print(f"  ⚠️  VIX 讀取失敗：{exc}")
        return None


def fetch_cnn_fear_greed() -> dict[str, Any] | None:
    try:
        utc_today = datetime.now(timezone.utc).date()
        dates = []
        for candidate in (
            TODAY,
            utc_today,
            TODAY - timedelta(days=1),
            utc_today - timedelta(days=1),
            TODAY - timedelta(days=7),
        ):
            if candidate not in dates:
                dates.append(candidate)
        urls = [f"{CNN_FEAR_GREED}/{d.isoformat()}" for d in dates] + [CNN_FEAR_GREED]
        data: dict[str, Any] | None = None
        last_error: Exception | None = None
        for url in urls:
            try:
                res = requests.get(url, headers=CNN_HEADERS, timeout=25)
                res.raise_for_status()
                payload = res.json()
                if isinstance(payload, dict):
                    data = payload
                    break
            except Exception as exc:
                last_error = exc
        if data is None:
            if last_error:
                raise last_error
            return None
        fg = data.get("fear_and_greed") or {}
        historical = data.get("fear_and_greed_historical") or {}
        score = _num(fg.get("score"))
        if score is None:
            score = _num(historical.get("score"))
        if score is None:
            return None
        rating = str(fg.get("rating") or historical.get("rating") or "")
        history = {}
        for key, source_key in (
            ("previous_close", "previous_close"),
            ("1w", "previous_1_week"),
            ("1m", "previous_1_month"),
            ("1y", "previous_1_year"),
        ):
            val = _num(fg.get(source_key))
            if val is not None:
                history[key] = round(val, 2)
        indicators: dict[str, dict[str, Any]] = {}
        indicator_labels = {
            "market_momentum_sp500": "Market Momentum",
            "stock_price_strength": "Stock Price Strength",
            "stock_price_breadth": "Stock Price Breadth",
            "put_call_options": "Put/Call Options",
            "market_volatility_vix": "Market Volatility",
            "junk_bond_demand": "Junk Bond Demand",
            "safe_haven_demand": "Safe Haven Demand",
        }
        for key, label in indicator_labels.items():
            item = data.get(key)
            if not isinstance(item, dict):
                continue
            item_score = _num(item.get("score"))
            if item_score is None:
                continue
            item_rating = str(item.get("rating") or "")
            indicators[key] = {
                "label": label,
                "score": round(item_score, 2),
                "rating": item_rating,
                "rating_zh": _rating_zh(item_rating),
            }
        return {
            "score": round(score, 2),
            "rating": rating,
            "rating_zh": _rating_zh(rating),
            "timestamp": fg.get("timestamp") or historical.get("timestamp"),
            "history": history,
            "indicators": indicators,
            "source": "cnn_fear_greed",
            "url": "https://edition.cnn.com/markets/fear-and-greed",
        }
    except Exception as exc:
        print(f"  ⚠️  CNN Fear & Greed 讀取失敗：{exc}")
        return None


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
            # TWSE 曾使用「外資及陸資」，後改為「外資」；
            # 同時排除「外資自營商」（屬自營商分類，非外資合計列）。
            if "外資及陸資" in name or (name.startswith("外資") and "自營商" not in name):
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


def fetch_stock_institutional_amounts(days: int = 4) -> dict[str, Any] | None:
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


def _add_trader_oi_changes(
    contract: dict[str, Any] | None,
    previous_contract: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not contract or not previous_contract:
        return contract
    previous_traders = previous_contract.get("traders") or {}
    changes: dict[str, dict[str, Any]] = {}
    for key, item in (contract.get("traders") or {}).items():
        current_oi = item.get("oi_net_lots")
        previous_oi = (previous_traders.get(key) or {}).get("oi_net_lots")
        if current_oi is None or previous_oi is None:
            continue
        changes[key] = {
            "oi_net_lots": current_oi - previous_oi,
            "previous_oi_net_lots": previous_oi,
            "previous_date": previous_contract.get("date"),
        }
    if changes:
        contract["trader_changes"] = changes
    return contract


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


def _component_score(value: float | int | None, scale: float, invert: bool = False) -> float | None:
    if value is None:
        return None
    score = _clamp(float(value) / scale * 100, -100, 100)
    return -score if invert else score


def _stock_flow_score(net_amount_twd: float | int | None) -> float | None:
    """外資現貨買賣超指數評分。
    ±100億以內近中性（≈4分），±500億以上強烈訊號（100分），採平方曲線加速。
    """
    if net_amount_twd is None:
        return None
    value_yi = net_amount_twd / 1e8
    sign = 1 if value_yi >= 0 else -1
    ratio = min(abs(value_yi) / 500, 1.0)
    return round(sign * ratio ** 2 * 100, 1)


def _vix_score(vix_close: float | None, vix_change: float | None) -> float | None:
    """VIX 行情狀態評分（非逆向，直接反映市場壓力）。
    水位：VIX 20 為中性，每偏離 10 點得 ±100 分。
    日變化：VIX 漲為負分，跌為正分，每 3 點對應 ±100 分。
    兩者各佔 50%。
    """
    if vix_close is None:
        return None
    level_score = _component_score(20.0 - vix_close, scale=10)
    if vix_change is not None:
        change_score = _component_score(-vix_change, scale=3)
        return round(0.5 * level_score + 0.5 * change_score, 1)
    return round(level_score, 1)


def _market_bias(data: dict[str, Any]) -> dict[str, Any]:
    # ── 期貨日盤 ──
    tx_day_contract = ((data.get("futures") or {}).get("day_session") or {}).get("tx") or {}
    night_total = (((data.get("futures") or {}).get("night_session") or {}).get("tx") or {}).get("traders", {}).get("total", {})
    tx_foreign_oi_change = (tx_day_contract.get("trader_changes") or {}).get("foreign", {}).get("oi_net_lots")
    tx_total_oi_change = (tx_day_contract.get("trader_changes") or {}).get("total", {}).get("oi_net_lots")

    # ── 散戶多空比：偏離近期均值（消除結構性偏多）──
    retail_rows = ((data.get("sentiment") or {}).get("retail_dashboard") or {}).get("rows") or []
    mtx_row = next((r for r in retail_rows if r.get("key") == "mtx"), None)
    retail_deviation: float | None = None
    retail_today: float | None = None
    retail_baseline: float | None = None
    if mtx_row:
        retail_today = mtx_row.get("today")
        prev_ratios = [h.get("ratio") for h in (mtx_row.get("history") or [])[1:] if h.get("ratio") is not None]
        if prev_ratios and retail_today is not None:
            retail_baseline = round(sum(prev_ratios) / len(prev_ratios), 2)
            retail_deviation = round(retail_today - retail_baseline, 2)
        else:
            retail_deviation = retail_today

    # ── PC Ratio（動態基準 + 行情方向）──
    pc_data = (data.get("sentiment") or {}).get("pc_ratio") or {}
    pc_history = pc_data.get("history") or []
    pc_oi = pc_data.get("open_interest_ratio")
    pc_oi_baseline: float | None = None
    pc_oi_deviation: float | None = None
    if pc_oi is not None and pc_history:
        hist_vals = [h.get("open_interest_ratio") for h in pc_history[1:] if h.get("open_interest_ratio") is not None]
        if hist_vals:
            pc_oi_baseline = round(sum(hist_vals) / len(hist_vals), 1)
            pc_oi_deviation = round(pc_oi - pc_oi_baseline, 1)

    # ── 外資現貨 / 美股情緒 / VIX ──
    stock_history = (data.get("stock_institutional") or {}).get("history") or []
    foreign_stock_net = (stock_history[0].get("traders") or {}).get("foreign", {}).get("net_amount") if stock_history else None
    fg_score = ((data.get("us_sentiment") or {}).get("fear_greed") or {}).get("score")
    vix_data = (data.get("us_sentiment") or {}).get("vix") or {}
    vix_close = vix_data.get("close")
    vix_change = vix_data.get("change")

    # PC Ratio 評分：偏離 5 日均值為正（今日比近期更防禦）→ 負分；無歷史時退回絕對水位
    if pc_oi_deviation is not None:
        pc_score = _component_score(pc_oi_deviation, 15, invert=True)
        pc_note = (
            f"今日 {pc_oi}%，近期均值 {pc_oi_baseline}%，偏差 {pc_oi_deviation:+.1f}%；"
            "Put 部位高於近期均值代表防禦氣氛偏濃，市場動能偏弱。"
        )
    else:
        pc_score = _component_score((100.0 - pc_oi) if pc_oi is not None else None, 30)
        pc_note = f"今日 {pc_oi}%；Put 未平倉比率偏高代表市場處於防禦狀態（無歷史基準，採絕對值）。"

    components = [
        {
            "key": "retail_ratio",
            "label": "散戶多空比偏差",
            "value": retail_deviation,
            "unit": "%",
            "weight": 25,
            "score": _component_score(retail_deviation, 10, invert=True),
            "note": f"小台今日 {retail_today}%，近期均值 {retail_baseline}%；散戶部位偏多超出均值，市場籌碼集中、易受賣壓。",
        },
        {
            "key": "pc_ratio",
            "label": "選擇權未平倉 P/C",
            "value": pc_oi,
            "unit": "%",
            "weight": 18,
            "score": pc_score,
            "note": pc_note,
        },
        {
            "key": "foreign_stock_flow",
            "label": "外資現貨買賣超",
            "value": round(foreign_stock_net / 1e8, 1) if foreign_stock_net is not None else None,
            "unit": "億",
            "weight": 15,
            "score": _stock_flow_score(foreign_stock_net),
            "note": "±100億以內中性，±500億以上強烈訊號，指數曲線計分。",
        },
        {
            "key": "cnn_fear_greed",
            "label": "CNN Fear & Greed",
            "value": fg_score,
            "unit": "分",
            "weight": 12,
            "score": _component_score((fg_score - 50) if fg_score is not None else None, 50),
            "note": "美股風險偏好；高分代表市場處於貪婪／風險偏好狀態，低分代表恐慌收縮。",
        },
        {
            "key": "foreign_tx_oi_change",
            "label": "外資台指期未平倉變化",
            "value": tx_foreign_oi_change,
            "unit": "口",
            "weight": 12,
            "score": _component_score(tx_foreign_oi_change, 5000),
            "note": "日變化量（非存量）；正值為減空/加多，反映外資對台股的即時方向。",
        },
        {
            "key": "night_session",
            "label": "夜盤三大法人買賣超",
            "value": night_total.get("net_lots"),
            "unit": "口",
            "weight": 10,
            "score": _component_score(night_total.get("net_lots"), 5000),
            "note": "夜盤反映美股時段後的短線部位變化。",
        },
        {
            "key": "vix",
            "label": "VIX 恐慌指數",
            "value": vix_close,
            "unit": "",
            "weight": 8,
            "score": _vix_score(vix_close, vix_change),
            "note": (
                f"VIX {vix_close}（{'↑' if (vix_change or 0) > 0 else '↓' if (vix_change or 0) < 0 else '—'}"
                f"{abs(vix_change):.2f}）；20 為中性點，高於 20 代表市場壓力升溫，低於 15 代表過度樂觀。"
            ) if vix_close is not None else "VIX 資料暫無法取得。",
        },
    ]
    valid = [c for c in components if c["score"] is not None]
    total_weight = sum(c["weight"] for c in valid)
    weighted_score = (
        sum(c["score"] * c["weight"] for c in valid) / total_weight
        if total_weight else 0
    )
    weighted_score = round(_clamp(weighted_score, -100, 100), 1)
    label = "偏多" if weighted_score >= 25 else "偏空" if weighted_score <= -25 else "中性"
    return {
        "label": label,
        "score": weighted_score,
        "gauge": round((weighted_score + 100) / 2, 1),
        "confidence": round(abs(weighted_score), 1),
        "components": valid,
        "definition": "散戶籌碼 25% + 選擇權P/C 18% + 外資現貨 15% + CNN情緒 12% + 外資期貨 12% + 夜盤 10% + VIX 8%；門檻 ±25。",
    }


def _generate_commentary(market_bias: dict[str, Any]) -> str | None:
    """呼叫 Gemini 生成市場溫度計的 AI 行情講評（60~90字）。無 API Key 時直接略過。"""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None

    score = market_bias.get("score", 0)
    label = market_bias.get("label", "中性")
    components = market_bias.get("components") or []

    comp_lines = "\n".join(
        f"- {c['label']}：{c['value']} {c.get('unit', '')}（評分 {round(c['score'], 1):+.1f}）"
        for c in components
        if c.get("score") is not None and c.get("value") is not None
    )

    prompt = (
        "你是台股盤前分析師。以下是今日台股市場溫度計的量化數據，"
        "請用繁體中文寫一段 60～90 字的行情講評，"
        "說明當前市場情緒與主要驅動因素，語氣客觀簡潔，直接說重點，不要廢話。\n\n"
        f"市場偏向：{label}（綜合分數 {score:+.1f}）\n"
        f"各項指標：\n{comp_lines}\n\n"
        "直接輸出講評文字，不加標題、不加引號。"
    )

    try:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 180},
        }
        res = requests.post(
            GEMINI_URL,
            params={"key": api_key},
            json=payload,
            headers=HEADERS,
            timeout=30,
        )
        res.raise_for_status()
        text = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        return text
    except Exception as exc:
        print(f"  ⚠️  AI 講評生成失敗：{exc}")
        return None


def _bias(data: dict[str, Any]) -> str:
    return _market_bias(data)["label"]


def main() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    print(f"=== 更新 FUTURE DASHBOARD {NOW.strftime('%Y-%m-%d %H:%M')} ===")

    day_institutional = fetch_taifex_day_institutional()
    night_institutional = fetch_taifex_night_institutional()
    market = fetch_futures_daily_market()
    pc_ratio = fetch_pc_ratio()
    market_history = fetch_futures_market_history()
    stock_inst = fetch_stock_institutional_amounts()
    fear_greed = fetch_cnn_fear_greed()
    vix = fetch_vix()

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
    previous_day = None
    if day_institutional and day_institutional.get("date"):
        previous_dates = sorted(
            [d for d in institutional_history if d < day_institutional["date"]],
            reverse=True,
        )
        previous_day = institutional_history.get(previous_dates[0]) if previous_dates else None
    tx_day = _add_trader_oi_changes(tx_day, _contract_view(previous_day, "臺股期貨"))
    mtx_day = _add_trader_oi_changes(mtx_day, _contract_view(previous_day, "小型臺指期貨"))
    tmf_day = _add_trader_oi_changes(tmf_day, _contract_view(previous_day, "微型臺指期貨"))
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
        "source": "taifex_futContractsDate+taifex_futContractsDateAh+taifex_futDataDown+taifex_open_data" + ("+twse_bfi82u" if stock_inst else "") + ("+cnn_fear_greed" if fear_greed else "") + ("+stooq_vix" if vix else ""),
        "market": market or {},
        "stock_institutional": stock_inst,
        "us_sentiment": {
            "fear_greed": fear_greed,
            "vix": vix,
        },
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
    market_bias = _market_bias(out)
    commentary = _generate_commentary(market_bias)
    if commentary:
        market_bias["commentary"] = commentary
    out["summary"] = {
        "bias": market_bias["label"],
        "market_bias": market_bias,
        "notes": [
            "夜盤法人為期交所三大法人夜盤頁面資料，日期以盤後交易量歸屬日為準。",
            "散戶多空比以三大法人淨未平倉反向值 / 全市場全月份未沖銷契約數估算；正值代表散戶相對偏多。",
            "Market Bias 反映當前市場動能狀態，非逆向操作建議；各指標均以順勢方向計分。",
        ],
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"  ✅ 已輸出 futures_dashboard.json：{out['date']} ({out['summary']['bias']})")


if __name__ == "__main__":
    main()
