#!/usr/bin/env python3
"""
從集保中心 OpenAPI 抓取股權分散表，自動更新 big1000.csv / big400.csv。

big1000：持股分級 15（1,000,000 股以上 = 1000張+）
big400 ：持股分級 12~15（400,000 股以上 = 400張+）
"""

import csv
import os
import re
import sys
import time

import requests

TDCC_URL   = "https://openapi.tdcc.com.tw/v1/opendata/1-5"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(SCRIPT_DIR, "..", "data")
CSV_1000   = os.path.join(DATA_DIR, "big1000.csv")
CSV_400    = os.path.join(DATA_DIR, "big400.csv")

LEVELS_1000 = {15}
LEVELS_400  = {12, 13, 14, 15}


# ── 工具函式 ──────────────────────────────────────────────────────

def roc_to_yyyymmdd(roc: str) -> str:
    """民國年 '114/04/18' 或 '1140418' → '20250418'"""
    roc = roc.strip()
    if "/" in roc or "-" in roc:
        parts = re.split(r"[/\-]", roc)
        y, m, d = int(parts[0]) + 1911, int(parts[1]), int(parts[2])
    else:
        y = int(roc[:3]) + 1911
        m, d = int(roc[3:5]), int(roc[5:7])
    return f"{y}{m:02d}{d:02d}"


# ── TDCC 資料抓取 ─────────────────────────────────────────────────

def fetch_tdcc() -> tuple[list[dict], str]:
    print(f"  GET {TDCC_URL}")
    for attempt in range(3):
        try:
            resp = requests.get(
                TDCC_URL,
                headers={"accept": "application/json"},
                timeout=90,
            )
            resp.raise_for_status()
            data = resp.json()
            break
        except Exception as e:
            if attempt == 2:
                raise
            print(f"  第 {attempt+1} 次失敗 ({e})，3 秒後重試...")
            time.sleep(3)

    if not data:
        raise ValueError("TDCC API 回傳空資料")

    date_raw = data[0].get("資料日期", "")
    date_str = roc_to_yyyymmdd(date_raw)
    print(f"  資料日期：{date_raw} → {date_str}，共 {len(data):,} 筆")
    return data, date_str


def compute_holdings(data: list[dict], levels: set[int]) -> dict[str, float]:
    """計算各股在指定持股分級的合計持股比例"""
    holdings: dict[str, float] = {}
    for row in data:
        code = str(row.get("證券代號", "")).strip()
        if not code:
            continue
        try:
            level = int(row.get("持股分級", 0))
            pct   = float(str(row.get("占集保庫存數比例%", "0")).replace("%", "").strip())
        except (ValueError, TypeError):
            continue
        if level not in levels:
            continue
        holdings[code] = round(holdings.get(code, 0.0) + pct, 4)
    return holdings


# ── CSV 更新 ──────────────────────────────────────────────────────

def update_csv(
    csv_path: str,
    holdings: dict[str, float],
    new_date: str,
    encoding: str,
) -> None:
    with open(csv_path, encoding=encoding, newline="") as f:
        reader     = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows       = list(reader)

    date_cols = sorted(
        [c for c in fieldnames if re.fullmatch(r"\d{8}", c)],
        reverse=True,
    )

    if new_date in date_cols:
        print(f"  {os.path.basename(csv_path)}：{new_date} 已存在，略過")
        return

    prev_date = date_cols[0] if date_cols else None

    # 在 (%)差異 後插入新日期欄
    diff_idx      = fieldnames.index("(%)差異")
    new_fieldnames = fieldnames[:diff_idx+1] + [new_date] + fieldnames[diff_idx+1:]

    hit = 0
    for row in rows:
        code_raw = str(row.get("股票") or "").strip()
        m = re.match(r"^(\d{4})", code_raw)
        if not m:
            row[new_date] = ""
            continue
        code = m.group(1)
        pct  = holdings.get(code)
        row[new_date] = f"{pct:.2f}" if pct is not None else ""
        if pct is not None:
            hit += 1

        # 更新 (%)差異
        if prev_date and row.get(prev_date):
            try:
                row["(%)差異"] = f"{float(row[new_date]) - float(row[prev_date]):.2f}"
            except (ValueError, TypeError):
                row["(%)差異"] = ""

    with open(csv_path, "w", encoding=encoding, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=new_fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"  ✅ {os.path.basename(csv_path)}：新增 {new_date}，命中 {hit}/{len(rows)} 支")


# ── 主程式 ────────────────────────────────────────────────────────

def main() -> None:
    print("=== 集保中心股權分散表更新 ===")

    print("\nStep 1：抓取 TDCC API 資料...")
    data, date_str = fetch_tdcc()

    print("\nStep 2：計算各股持股比例...")
    h1000 = compute_holdings(data, LEVELS_1000)
    h400  = compute_holdings(data, LEVELS_400)
    print(f"  big1000 命中 {len(h1000)} 支，big400 命中 {len(h400)} 支")

    print("\nStep 3：更新 CSV...")
    update_csv(CSV_1000, h1000, date_str, "utf-8-sig")
    update_csv(CSV_400,  h400,  date_str, "utf-8")

    print("\n=== 完成 ===")


if __name__ == "__main__":
    main()
