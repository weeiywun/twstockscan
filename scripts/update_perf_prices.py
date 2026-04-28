"""
update_perf_prices.py
每個交易日收盤後（14:00 台灣時間）更新 data/performance.json 中
持倉中（confirmed=False）股票的 price_history。

價格來源：
  - 上市：TWSE Open API (openapi.twse.com.tw)
  - 上櫃：TPEX Open API (tpex.org.tw)
一次批次抓全市場，不依賴 Yahoo Finance。
"""

import json
import datetime
from pathlib import Path

import requests

PERF_JSON = Path(__file__).parent.parent / "data" / "performance.json"
HEADERS = {"accept": "application/json"}

TWSE_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"


def fetch_all_prices() -> dict[str, float]:
    """回傳 {stock_id: close_price}，涵蓋上市 + 上櫃。"""
    prices: dict[str, float] = {}

    # 上市（TWSE）
    try:
        resp = requests.get(TWSE_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        for row in resp.json():
            sid = row.get("Code", "").strip()
            close_str = row.get("ClosingPrice", "").replace(",", "").strip()
            if sid and close_str and close_str not in ("--", ""):
                try:
                    prices[sid] = float(close_str)
                except ValueError:
                    pass
        print(f"TWSE：取得 {len(prices)} 檔")
    except Exception as e:
        print(f"TWSE 抓取失敗：{e}")

    # 上櫃（TPEX）
    tpex_count = 0
    try:
        resp = requests.get(TPEX_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        for row in resp.json():
            sid = row.get("SecuritiesCompanyCode", "").strip()
            close_str = row.get("Close", "").replace(",", "").strip()
            if sid and close_str and close_str not in ("--", ""):
                try:
                    if sid not in prices:   # 上市優先，避免重複
                        prices[sid] = float(close_str)
                        tpex_count += 1
                except ValueError:
                    pass
        print(f"TPEX：取得 {tpex_count} 檔")
    except Exception as e:
        print(f"TPEX 抓取失敗：{e}")

    return prices


def main():
    if not PERF_JSON.exists():
        print("找不到 data/performance.json，略過。")
        return

    with open(PERF_JSON, encoding="utf-8") as f:
        pd_data = json.load(f)

    positions = pd_data.get("positions", [])
    active = [p for p in positions if not p.get("confirmed", False)]

    if not active:
        print("目前無持倉中的部位，略過。")
        return

    print(f"共 {len(active)} 檔持倉中，開始更新收盤價…")

    all_prices = fetch_all_prices()
    if not all_prices:
        print("無法取得市場報價，中止。")
        return

    today = datetime.date.today().isoformat()
    if "price_history" not in pd_data:
        pd_data["price_history"] = {}

    updated = False
    for pos in active:
        sid = pos["stock_id"]
        name = pos.get("name", sid)
        if sid in all_prices:
            price = all_prices[sid]
            if sid not in pd_data["price_history"]:
                pd_data["price_history"][sid] = {}
            pd_data["price_history"][sid][today] = price
            print(f"  ✅ {sid} {name}：{price}")
            updated = True
        else:
            print(f"  ❌ {sid} {name}：報價中找不到此股票")

    if updated:
        pd_data["last_updated"] = today
        with open(PERF_JSON, "w", encoding="utf-8") as f:
            json.dump(pd_data, f, ensure_ascii=False, indent=2)
        print(f"\nperformance.json 已更新（{today}）")
    else:
        print("\n無任何更新。")


if __name__ == "__main__":
    main()
