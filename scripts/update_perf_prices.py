"""
update_perf_prices.py
每個交易日收盤後（14:00 台灣時間）更新 data/performance.json 中
持倉中（confirmed=False）股票的 price_history。

價格來源：Yahoo Finance（免 API key，支援上市 .TW / 上櫃 .TWO）
"""

import json
import time
import datetime
from pathlib import Path

import requests

PERF_JSON = Path(__file__).parent.parent / "data" / "performance.json"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5d"


def fetch_close(stock_id: str) -> tuple[str, float] | None:
    """
    嘗試 .TW（上市）再試 .TWO（上櫃），回傳 (YYYY-MM-DD, close_price) 或 None。
    """
    for suffix in (".TW", ".TWO"):
        ticker = stock_id + suffix
        try:
            resp = requests.get(YAHOO_URL.format(ticker=ticker), headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                continue
            data = resp.json()
            result = data.get("chart", {}).get("result")
            if not result:
                continue
            chart = result[0]
            timestamps = chart.get("timestamp", [])
            closes = chart.get("indicators", {}).get("quote", [{}])[0].get("close", [])
            if not timestamps or not closes:
                continue
            # 取最後一筆非 None 的收盤價
            for ts, cl in zip(reversed(timestamps), reversed(closes)):
                if cl is None:
                    continue
                date_str = datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
                return date_str, round(cl, 2)
        except Exception as e:
            print(f"  [{ticker}] 例外：{e}")
    return None


def main():
    if not PERF_JSON.exists():
        print("找不到 data/performance.json，略過。")
        return

    with open(PERF_JSON, encoding="utf-8") as f:
        pd = json.load(f)

    positions = pd.get("positions", [])
    active = [p for p in positions if not p.get("confirmed", False)]

    if not active:
        print("目前無持倉中的部位，略過。")
        return

    print(f"共 {len(active)} 檔持倉中，開始更新收盤價…")

    if "price_history" not in pd:
        pd["price_history"] = {}

    updated = False
    for pos in active:
        sid = pos["stock_id"]
        print(f"  查詢 {sid} ({pos.get('name', '')})…", end=" ", flush=True)
        result = fetch_close(sid)
        if result is None:
            print("❌ 無法取得價格")
            continue
        date_str, price = result
        if sid not in pd["price_history"]:
            pd["price_history"][sid] = {}
        pd["price_history"][sid][date_str] = price
        print(f"✅ {date_str} = {price}")
        updated = True
        time.sleep(0.3)  # 避免過快觸發限速

    if updated:
        today = datetime.date.today().isoformat()
        pd["last_updated"] = today
        with open(PERF_JSON, "w", encoding="utf-8") as f:
            json.dump(pd, f, ensure_ascii=False, indent=2)
        print(f"\nperformance.json 已更新（{today}）")
    else:
        print("\n無任何更新。")


if __name__ == "__main__":
    main()
