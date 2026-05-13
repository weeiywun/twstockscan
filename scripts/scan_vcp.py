#!/usr/bin/env python3
"""
VCP（Volatility Contraction Pattern）選股掃描器

掃描符合 Mark Minervini《超級績效》書中 VCP 型態的台股：
1. Stage 2 上升趨勢（收盤 > MA100，且 MA100 向上）
2. 近 16 週內出現 2~4 段波動收縮（每段回調幅度嚴格遞減）
3. 每段收縮期間成交量遞減
4. 最後樞紐區間緊縮（潛在突破點）
5. 交叉比對大戶持股（big1000.csv / big400.csv）
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

from finmind_client import get_stock_price_from_cache, load_price_cache

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
OUTPUT_PATH = os.path.join(DATA_DIR, "vcp.json")
STOCK_LIST_PATH = os.path.join(DATA_DIR, "stock_list_cache.json")
CSV_1000 = os.path.join(DATA_DIR, "big1000.csv")
CSV_400  = os.path.join(DATA_DIR, "big400.csv")

TW_TZ = timezone(timedelta(hours=8))
TODAY = datetime.now(TW_TZ).strftime("%Y-%m-%d")

LOOKBACK_DAYS = 210
BASE_WEEKS = 16        # 掃描最近 N 週作為底部基礎（快取約 27 週，保留彈性）
SWING_WINDOW = 1       # 週 K 擺動高低點識別 window（左右各 N 週）
MIN_CONTRACTIONS = 2
MAX_CONTRACTIONS = 4
MIN_FIRST_DEPTH = 6.0  # 第一段收縮最小回調幅度（%）
MAX_LAST_DEPTH = 20.0  # 最後一段收縮最大回調幅度（%）；超過代表整理不夠緊
PIVOT_NEAR_PCT  = 0.05  # 收盤距樞紐高點 5% 以內視為「靠近樞紐」
PIVOT_MAX_ABOVE = 0.15  # 收盤超過樞紐 15% 以上視為「已走完波段」，排除
PIVOT_L_MIN_IDX = BASE_WEEKS - 5  # 最後一段 L 必須在底部窗口的末 5 週內
MA_PERIOD = 100        # 趨勢均線週期（快取僅 ~136 日，改用 MA100 取代 MA150）
MIN_BARS = 105         # 最少需要 105 根日線（確保 MA100 有效）


def now_tw() -> str:
    return datetime.now(TW_TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def _require_fresh_cache(price_cache: pd.DataFrame) -> None:
    latest = price_cache["date"].max().strftime("%Y-%m-%d")
    if latest != TODAY:
        print(f"price_cache.parquet 最新資料為 {latest}，不是 {TODAY}；停止掃描，避免舊資料產生訊號")
        sys.exit(1)


def _to_weekly(df: pd.DataFrame) -> pd.DataFrame:
    df = df.set_index("date").sort_index()
    weekly = df.resample("W-FRI").agg(
        open=("open", "first"),
        max=("max", "max"),
        min=("min", "min"),
        close=("close", "last"),
        volume_lots=("volume_lots", "sum"),
    ).dropna(subset=["close"])
    return weekly.reset_index()


def _find_swing_points(prices: list[float], window: int = 2) -> list[tuple[int, float, str]]:
    """
    找出交替的擺動高低點（週 K 適用）。
    每個點需比左右各 window 根 K 棒都高（低）才算擺動點。
    回傳 [(index, price, 'H'|'L'), ...] 已強制交替。
    """
    n = len(prices)
    raw: list[tuple[int, float, str]] = []

    for i in range(window, n - window):
        is_h = all(prices[i] >= prices[i - j] for j in range(1, window + 1)) and \
               all(prices[i] >= prices[i + j] for j in range(1, window + 1))
        if is_h:
            raw.append((i, prices[i], "H"))
            continue
        is_l = all(prices[i] <= prices[i - j] for j in range(1, window + 1)) and \
               all(prices[i] <= prices[i + j] for j in range(1, window + 1))
        if is_l:
            raw.append((i, prices[i], "L"))

    if not raw:
        return []

    # 強制交替：相同類型相鄰時，保留更極值的那個
    alt = [raw[0]]
    for cur in raw[1:]:
        prev = alt[-1]
        if cur[2] == prev[2]:
            if (cur[2] == "H" and cur[1] > prev[1]) or (cur[2] == "L" and cur[1] < prev[1]):
                alt[-1] = cur
        else:
            alt.append(cur)

    return alt


def check_vcp(daily: pd.DataFrame) -> dict | None:
    """
    檢查單支股票是否符合 VCP 型態。
    回傳訊號 dict 或 None。
    """
    if daily is None or len(daily) < MIN_BARS:
        return None

    df = daily.sort_values("date").reset_index(drop=True).copy()
    df["ma"] = df["close"].rolling(MA_PERIOD).mean()

    latest = df.iloc[-1]
    if pd.isna(latest["ma"]):
        return None

    close_now = float(latest["close"])
    ma_now = float(latest["ma"])

    # ── 1. Stage 2 趨勢過濾 ──────────────────────────────────────────
    if close_now <= ma_now:
        return None

    # MA 在過去 20 個交易日需持續上升
    if len(df) >= 20 and not pd.isna(df.iloc[-20]["ma"]):
        if ma_now <= float(df.iloc[-20]["ma"]):
            return None

    # ── 2. 轉週線，取最近 BASE_WEEKS 週 ─────────────────────────────
    weekly = _to_weekly(df)
    min_weeks = BASE_WEEKS + SWING_WINDOW * 2 + 1
    if len(weekly) < min_weeks:
        return None

    base_wk = weekly.tail(BASE_WEEKS).reset_index(drop=True)
    closes  = base_wk["close"].tolist()
    volumes = base_wk["volume_lots"].tolist()

    # ── 3. 找擺動高低點 ──────────────────────────────────────────────
    swings = _find_swing_points(closes, window=SWING_WINDOW)
    if len(swings) < 3:  # 至少需要 H-L-H 或 L-H-L 才能萃取收縮
        return None

    # ── 4. 萃取 H→L 收縮段（保留 l_idx 供時效性過濾使用）─────────────
    contractions = []
    for i in range(len(swings) - 1):
        if swings[i][2] == "H" and swings[i + 1][2] == "L":
            h_idx, h_price = swings[i][0], swings[i][1]
            l_idx, l_price = swings[i + 1][0], swings[i + 1][1]
            depth = (h_price - l_price) / h_price * 100
            seg_vols = volumes[h_idx : l_idx + 1]
            avg_vol  = sum(seg_vols) / len(seg_vols) if seg_vols else 0
            contractions.append({
                "depth":   round(depth, 1),
                "avg_vol": avg_vol,
                "h_price": round(h_price, 2),
                "l_price": round(l_price, 2),
                "l_idx":   l_idx,   # 最後低點在底部窗口的位置
            })

    if len(contractions) < MIN_CONTRACTIONS:
        return None

    # 取最後 MAX_CONTRACTIONS 段作為完整的 VCP 底部
    contractions = contractions[-MAX_CONTRACTIONS:]

    # ── 時效性過濾：最後一段 L 必須在末 5 週內 ───────────────────────
    # 確保 VCP 仍在進行中，而非已走完波段的歷史形態
    if contractions[-1]["l_idx"] < PIVOT_L_MIN_IDX:
        return None

    depths = [c["depth"] for c in contractions]
    vols   = [c["avg_vol"] for c in contractions]

    # ── 5. 深度嚴格遞減驗證 ──────────────────────────────────────────
    if not all(depths[i] > depths[i + 1] for i in range(len(depths) - 1)):
        return None
    if depths[0] < MIN_FIRST_DEPTH:
        return None
    if depths[-1] > MAX_LAST_DEPTH:
        return None

    # ── 6. 量能嚴格遞減驗證 ──────────────────────────────────────────
    if not all(vols[i] >= vols[i + 1] for i in range(len(vols) - 1)):
        return None

    vol_contraction_ratio = round(vols[-1] / vols[0], 2) if vols[0] > 0 else None

    # ── 7. 樞紐高點與緊縮度 ──────────────────────────────────────────
    pivot_high = contractions[-1]["h_price"]  # 最後一段收縮的起點高位 = 潛在突破點
    pivot_range_pct = depths[-1]              # 最後一段收縮深度，反映樞紐緊縮程度
    pivot_dist_pct  = (close_now - pivot_high) / pivot_high * 100

    # 排除已大幅突破樞紐的歷史形態（收盤超過樞紐 15% 以上）
    if pivot_dist_pct > PIVOT_MAX_ABOVE * 100:
        return None

    is_near_pivot = pivot_dist_pct >= -(PIVOT_NEAR_PCT * 100)

    # ── 8. 品質分數（純技術面，whale 加成由呼叫端疊加）──────────────
    score = 40  # 基礎分
    score += min((len(contractions) - MIN_CONTRACTIONS) * 10, 20)

    if vol_contraction_ratio is not None:
        if vol_contraction_ratio < 0.50:
            score += 15
        elif vol_contraction_ratio < 0.70:
            score += 8

    depth_ratio = depths[-1] / depths[0] if depths[0] > 0 else 1
    if depth_ratio < 0.35:
        score += 10
    elif depth_ratio < 0.50:
        score += 5

    if pivot_range_pct < 6:       # 最後一段深度 <6%：極緊縮
        score += 10
    elif pivot_range_pct < 10:    # <10%：緊縮良好
        score += 5

    if is_near_pivot:
        score += 5

    # ── 9. 訊號標籤（技術面；whale 標籤由呼叫端疊加）───────────────
    tags = ["VCP", f"{len(contractions)}段收縮"]
    if vol_contraction_ratio is not None and vol_contraction_ratio < 0.60:
        tags.append("量縮到位")
    if pivot_range_pct < 10:   # 最後一段深度 <10% 視為樞紐緊縮
        tags.append("樞紐緊縮")
    if is_near_pivot:
        tags.append("靠近樞紐")

    return {
        "close":                 round(close_now, 2),
        "ma100":                 round(ma_now, 2),
        "bias_ma100":            round((close_now - ma_now) / ma_now * 100, 1),
        "contractions":          len(contractions),
        "contraction_depths":    depths,
        "vol_contraction_ratio": vol_contraction_ratio,
        "pivot_high":            pivot_high,
        "pivot_range_pct":       pivot_range_pct,
        "is_near_pivot":         is_near_pivot,
        "tags":                  tags,
        "quality_score":         score,  # 最終分由 main() 疊加 whale 後覆蓋
    }


def _parse_whale_csv(path: str) -> tuple[dict[str, dict[str, float]], list[str]]:
    if not os.path.exists(path):
        return {}, []
    stocks: dict[str, dict[str, float]] = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        date_cols = sorted([h for h in headers if re.fullmatch(r"\d{8}", h)])
        first_header = headers[0] if headers else ""
        for row in reader:
            raw = (row.get("股票") or row.get(first_header, "") or "").strip()
            parts = raw.split(None, 1)
            if len(parts) < 1 or not re.fullmatch(r"\d{4}", parts[0]):
                continue
            pct_map: dict[str, float] = {}
            for date_col in date_cols:
                try:
                    pct_map[date_col] = float((row.get(date_col) or "").strip())
                except ValueError:
                    pass
            stocks[parts[0]] = pct_map
    return stocks, date_cols


def _last_values(pct_map: dict[str, float], date_cols: list[str], n: int = 4) -> list[float]:
    valid = [c for c in date_cols if c in pct_map]
    return [pct_map[c] for c in valid[-n:]]


def _is_strictly_up(values: list[float]) -> bool:
    return len(values) >= 4 and all(values[i] > values[i - 1] for i in range(1, len(values)))


def load_whale_map() -> dict[str, dict]:
    stocks_1000, dates_1000 = _parse_whale_csv(CSV_1000)
    stocks_400,  dates_400  = _parse_whale_csv(CSV_400)
    whale_map: dict[str, dict] = {}
    for sid in set(stocks_1000) | set(stocks_400):
        v1000 = _last_values(stocks_1000.get(sid, {}), dates_1000)
        v400  = _last_values(stocks_400.get(sid, {}),  dates_400)
        whale_map[sid] = {
            "whale_3w_up":     _is_strictly_up(v1000),
            "whale_400_3w_up": _is_strictly_up(v400),
            "big_pct_1000":    round(v1000[-1], 2) if v1000 else None,
            "big_pct_400":     round(v400[-1],  2) if v400  else None,
            "big_1000_chg_3w": round(v1000[-1] - v1000[0], 2) if len(v1000) >= 4 else None,
            "big_400_chg_3w":  round(v400[-1]  - v400[0],  2) if len(v400)  >= 4 else None,
        }
    return whale_map


def _industry_list(value: str) -> list[str]:
    return [p.strip() for p in (value or "").split(" / ") if p.strip()]


def build_industry_stats(results: list[dict]) -> list[dict]:
    industry_map: dict[str, dict] = {}
    for row in results:
        for ind in _industry_list(row.get("industry", "")) or ["其他"]:
            if ind not in industry_map:
                industry_map[ind] = {"industry": ind, "count": 0, "stocks": []}
            industry_map[ind]["count"] += 1
            industry_map[ind]["stocks"].append({"stock_id": row["stock_id"], "name": row["name"]})
    return sorted(industry_map.values(), key=lambda x: x["count"], reverse=True)


def _write_output(results: list[dict], industry_stats: list[dict]) -> None:
    output = {
        "strategy_id":   "vcp",
        "updated":       now_tw(),
        "results":       results,
        "industry_stats": industry_stats,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"已寫入 {OUTPUT_PATH}，共 {len(results)} 檔")


def main() -> None:
    print("=== VCP 型態掃描器（Volatility Contraction Pattern）===")
    allow_stale = "--allow-stale" in sys.argv

    if not os.path.exists(STOCK_LIST_PATH):
        print("stock_list_cache.json 不存在，請先執行 update_price_cache.py")
        _write_output([], [])
        return

    with open(STOCK_LIST_PATH, encoding="utf-8") as f:
        raw_stocks = json.load(f)

    seen: dict[str, dict] = {}
    for s in raw_stocks:
        if s["stock_id"] not in seen:
            seen[s["stock_id"]] = s
    stocks = list(seen.values())
    print(f"股票清單：{len(stocks)} 檔")

    price_cache = load_price_cache()
    if price_cache is None or price_cache.empty:
        print("price_cache.parquet 不存在，請先執行 update_price_cache.py")
        _write_output([], [])
        return

    if allow_stale:
        signal_date = price_cache["date"].max().strftime("%Y-%m-%d")
        print(f"--allow-stale：使用快取最新交易日 {signal_date}")
    else:
        _require_fresh_cache(price_cache)
        signal_date = TODAY

    print(f"價格快取：{len(price_cache):,} 筆，{price_cache['stock_id'].nunique()} 檔")

    whale_map = load_whale_map()
    if whale_map:
        print(f"大戶資料：{len(whale_map)} 檔")
    else:
        print("大戶資料：big1000.csv / big400.csv 不存在，略過籌碼整合")

    start_date = (datetime.now(TW_TZ) - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    results: list[dict] = []
    skipped = 0

    for i, stock in enumerate(stocks, 1):
        sid = stock["stock_id"]
        daily = get_stock_price_from_cache(price_cache, sid, start_date)
        signal = check_vcp(daily)

        if signal:
            whale = whale_map.get(sid, {})

            # ── 疊加大戶加成分數 ──────────────────────────────────────
            score = signal["quality_score"]
            if whale.get("whale_3w_up"):
                score += 12
            if whale.get("whale_400_3w_up"):
                score += 6
            score = min(score, 100)

            # ── 疊加大戶標籤 ──────────────────────────────────────────
            tags = list(signal["tags"])
            if whale.get("whale_3w_up"):
                tags.append("千張大戶連增")
            if whale.get("whale_400_3w_up"):
                tags.append("400張同步")

            results.append({
                "stock_id":  sid,
                "name":      stock["name"],
                "industry":  stock.get("industry", ""),
                "market":    stock.get("market", ""),
                **signal,
                **whale,
                "tags":          tags,
                "quality_score": score,
                "signal_date":   signal_date,
            })
            depth_str = "→".join(str(d) for d in signal["contraction_depths"])
            whale_flag = " 🐋千張" if whale.get("whale_3w_up") else ""
            print(f"  {sid} {stock['name']}  {signal['contractions']}段 {depth_str}%  分={score}{whale_flag}")
        else:
            skipped += 1

        if i % 200 == 0:
            print(f"掃描進度：{i}/{len(stocks)}，命中 {len(results)}，跳過 {skipped}")

    results.sort(key=lambda r: r.get("quality_score", 0), reverse=True)
    industry_stats = build_industry_stats(results)

    print(f"完成：VCP 命中 {len(results)} 檔")
    _write_output(results, industry_stats)


if __name__ == "__main__":
    main()
