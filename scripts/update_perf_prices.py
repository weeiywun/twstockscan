"""
update_perf_prices.py
每個交易日收盤後（14:00 台灣時間）更新 data/performance.json 中
持倉中（confirmed=False）股票的 price_history。

價格來源：
  - 上市：TWSE rwd afterTrading API（當日資料）
  - 上櫃：TPEX openapi mainboard_quotes（當日資料）
日期 key 來自 API 回應，確保與實際交易日一致。
"""

import json
import datetime
from pathlib import Path

import requests

PERF_JSON = Path(__file__).parent.parent / "data" / "performance.json"
HEADERS = {"User-Agent": "Mozilla/5.0", "accept": "application/json"}

TWSE_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL?response=json"
TPEX_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"


def roc_to_iso(roc_date: str) -> str:
    """民國日期字串（1150428）轉 ISO（2026-04-28）。"""
    y = int(roc_date[:3]) + 1911
    m = roc_date[3:5]
    d = roc_date[5:7]
    return f"{y}-{m}-{d}"


def fetch_all_prices() -> tuple[dict[str, float], str | None]:
    """
    回傳 ({stock_id: close_price}, date_str)。
    date_str 為 YYYY-MM-DD，取自 API 回應；兩個 API 日期不同時以 TWSE 為準。
    """
    prices: dict[str, float] = {}
    date_str: str | None = None

    # 上市（TWSE rwd）
    try:
        resp = requests.get(TWSE_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("stat") == "OK":
            raw_date = data.get("date", "")          # e.g. "20260428"
            if raw_date:
                date_str = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
            fields = data.get("fields", [])
            # 欄位順序：證券代號, 名稱, 成交股數, 成交金額, 開盤, 最高, 最低, 收盤, ...
            code_idx  = fields.index("證券代號")  if "證券代號"  in fields else 0
            close_idx = fields.index("收盤價")    if "收盤價"    in fields else 7
            for row in data.get("data", []):
                sid   = row[code_idx].strip()
                close = row[close_idx].replace(",", "").strip()
                if sid and close and close not in ("--", ""):
                    try:
                        prices[sid] = float(close)
                    except ValueError:
                        pass
            print(f"TWSE：{date_str}，取得 {len(prices)} 檔")
        else:
            print(f"TWSE 回應異常：{data.get('stat')}")
    except Exception as e:
        print(f"TWSE 抓取失敗：{e}")

    # 上櫃（TPEX openapi）
    tpex_count = 0
    try:
        resp = requests.get(TPEX_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        rows = resp.json()
        tpex_date = None
        for row in rows:
            raw = row.get("Date", "")              # e.g. "1150428"
            if raw and tpex_date is None:
                tpex_date = roc_to_iso(raw)
                if not date_str:
                    date_str = tpex_date
            sid   = row.get("SecuritiesCompanyCode", "").strip()
            close = row.get("Close", "").replace(",", "").strip()
            if sid and close and close not in ("--", ""):
                try:
                    if sid not in prices:
                        prices[sid] = float(close)
                        tpex_count += 1
                except ValueError:
                    pass
        print(f"TPEX：{tpex_date}，取得 {tpex_count} 檔")
    except Exception as e:
        print(f"TPEX 抓取失敗：{e}")

    return prices, date_str


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

    all_prices, date_str = fetch_all_prices()
    if not all_prices or not date_str:
        print("無法取得市場報價，中止。")
        return

    print(f"使用日期 key：{date_str}")

    if "price_history" not in pd_data:
        pd_data["price_history"] = {}

    updated = False
    for pos in active:
        sid  = pos["stock_id"]
        name = pos.get("name", sid)
        if sid in all_prices:
            price = all_prices[sid]
            if sid not in pd_data["price_history"]:
                pd_data["price_history"][sid] = {}
            pd_data["price_history"][sid][date_str] = price
            print(f"  ✅ {sid} {name}：{price}（{date_str}）")
            updated = True
        else:
            print(f"  ❌ {sid} {name}：報價中找不到此股票")

    if updated:
        pd_data["last_updated"] = date_str
        with open(PERF_JSON, "w", encoding="utf-8") as f:
            json.dump(pd_data, f, ensure_ascii=False, indent=2)
        print(f"\nperformance.json 已更新（{date_str}）")
    else:
        print("\n無任何更新。")


if __name__ == "__main__":
    main()
