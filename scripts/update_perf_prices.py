"""
update_perf_prices.py
每個交易日收盤後（14:00 台灣時間）批次更新三個 JSON 的收盤價：

  1. data/performance.json  → price_history（持倉追蹤用）
  2. data/chips_big_holder.json → results[].close
  3. data/right_top.json        → results[].close

價格來源：
  - 上市：TWSE rwd afterTrading API（當日資料）
  - 上櫃：TPEX openapi mainboard_quotes（當日資料）
日期 key 來自 API 回應，確保與實際交易日一致。
"""

import json
import time
from pathlib import Path

import requests

TPEX_RETRIES = 3
TPEX_BACKOFF = [2, 5, 10]  # 秒

DATA_DIR      = Path(__file__).parent.parent / "data"
PERF_JSON     = DATA_DIR / "performance.json"
CHIPS_JSON    = DATA_DIR / "chips_big_holder.json"
RIGHT_TOP_JSON = DATA_DIR / "right_top.json"

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
    date_str 為 YYYY-MM-DD，取自 API 回應；以 TWSE 日期為準。
    """
    prices: dict[str, float] = {}
    date_str: str | None = None

    # 上市（TWSE rwd）
    try:
        resp = requests.get(TWSE_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("stat") == "OK":
            raw_date = data.get("date", "")
            if raw_date:
                date_str = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
            fields    = data.get("fields", [])
            code_idx  = fields.index("證券代號") if "證券代號" in fields else 0
            close_idx = fields.index("收盤價")   if "收盤價"   in fields else 7
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

    # 上櫃（TPEX openapi），失敗時最多重試 TPEX_RETRIES 次
    tpex_count = 0
    for attempt in range(1, TPEX_RETRIES + 1):
        try:
            resp = requests.get(TPEX_URL, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            rows      = resp.json()
            tpex_date = None
            for row in rows:
                raw = row.get("Date", "")
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
            break  # 成功，跳出重試
        except Exception as e:
            wait = TPEX_BACKOFF[attempt - 1]
            if attempt < TPEX_RETRIES:
                print(f"TPEX 第 {attempt} 次失敗（{e}），{wait}s 後重試…")
                time.sleep(wait)
            else:
                print(f"TPEX 抓取失敗，已重試 {TPEX_RETRIES} 次：{e}")

    return prices, date_str


# ────────────────────────────────────────────────────
#  更新各 JSON
# ────────────────────────────────────────────────────

def update_performance(prices: dict[str, float], date_str: str) -> bool:
    if not PERF_JSON.exists():
        print("performance.json 不存在，略過。")
        return False
    with open(PERF_JSON, encoding="utf-8") as f:
        pd = json.load(f)

    active = [p for p in pd.get("positions", []) if not p.get("confirmed", False)]
    if not active:
        print("performance：無持倉中部位，略過。")
        return False

    if "price_history" not in pd:
        pd["price_history"] = {}

    updated = False
    for pos in active:
        sid  = pos["stock_id"]
        name = pos.get("name", sid)
        if sid in prices:
            pd["price_history"].setdefault(sid, {})[date_str] = prices[sid]
            print(f"  perf ✅ {sid} {name}：{prices[sid]}")
            updated = True
        else:
            print(f"  perf ❌ {sid} {name}：找不到報價")

    if updated:
        pd["last_updated"] = date_str
        with open(PERF_JSON, "w", encoding="utf-8") as f:
            json.dump(pd, f, ensure_ascii=False, indent=2)
    return updated


def update_results_close(json_path: Path, label: str, prices: dict[str, float]) -> bool:
    """更新任意含 results[].{stock_id, close} 結構的 JSON。"""
    if not json_path.exists():
        print(f"{label}：檔案不存在，略過。")
        return False
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    results = data.get("results", [])
    if not results:
        print(f"{label}：results 為空，略過。")
        return False

    updated = False
    for item in results:
        sid = item.get("stock_id", "")
        if sid in prices:
            old = item.get("close")
            item["close"] = prices[sid]
            if old != prices[sid]:
                print(f"  {label} ✅ {sid} {item.get('name', '')}：{old} → {prices[sid]}")
                updated = True
        else:
            print(f"  {label} ❌ {sid} {item.get('name', '')}：找不到報價")

    if updated:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    return updated


# ────────────────────────────────────────────────────

def main():
    print("=== 批次更新收盤價 ===")
    prices, date_str = fetch_all_prices()

    if not prices or not date_str:
        print("無法取得市場報價，中止。")
        return

    print(f"\n使用日期 key：{date_str}\n")

    any_updated = False
    any_updated |= update_performance(prices, date_str)
    any_updated |= update_results_close(CHIPS_JSON,     "chips",     prices)
    any_updated |= update_results_close(RIGHT_TOP_JSON, "right_top", prices)

    if any_updated:
        print(f"\n✅ 全部更新完成（{date_str}）")
    else:
        print("\n無任何變動。")


if __name__ == "__main__":
    main()
