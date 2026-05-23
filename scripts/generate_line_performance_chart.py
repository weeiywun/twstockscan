#!/usr/bin/env python3
"""
Generate the latest performance chart image for LINE Flex messages.

The script intentionally uses only Python's standard library so the workflow
does not need a heavy charting dependency. It overwrites one PNG:
assets/line/performance-latest.png
"""

from __future__ import annotations

import json
import math
import os
import struct
import zlib
from datetime import datetime, timedelta, timezone


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
DATA_DIR = os.path.join(ROOT_DIR, "data")
OUT_DIR = os.path.join(ROOT_DIR, "assets", "line")
OUT_PATH = os.path.join(OUT_DIR, "performance-latest.png")
PERF_PATH = os.path.join(DATA_DIR, "performance.json")
MARKET_PATH = os.path.join(DATA_DIR, "market_index.json")

WIDTH = 1000
HEIGHT = 520
PLOT_LEFT = 78
PLOT_TOP = 74
PLOT_RIGHT = WIDTH - 44
PLOT_BOTTOM = HEIGHT - 76

COLORS = {
    "bg": (255, 255, 255),
    "panel": (247, 248, 250),
    "grid": (224, 230, 238),
    "axis": (148, 163, 184),
    "text": (30, 41, 59),
    "muted": (100, 116, 139),
    "total": (29, 78, 216),
    "realized": (12, 107, 62),
    "market": (240, 136, 62),
    "zero": (71, 85, 105),
}


FONT = {
    " ": ["00000", "00000", "00000", "00000", "00000", "00000", "00000"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "10000", "11110", "00001", "00001", "11110"],
    "6": ["01110", "10000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00001", "01110"],
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01111", "10000", "10000", "10011", "10001", "10001", "01111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["01110", "00100", "00100", "00100", "00100", "00100", "01110"],
    "J": ["00111", "00010", "00010", "00010", "00010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "10101", "01010"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    ".": ["00000", "00000", "00000", "00000", "00000", "01100", "01100"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    "+": ["00000", "00100", "00100", "11111", "00100", "00100", "00000"],
    "%": ["11001", "11010", "00010", "00100", "01000", "01011", "10011"],
    "/": ["00001", "00010", "00010", "00100", "01000", "01000", "10000"],
    ":": ["00000", "01100", "01100", "00000", "01100", "01100", "00000"],
    "|": ["00100", "00100", "00100", "00100", "00100", "00100", "00100"],
    "(": ["00010", "00100", "01000", "01000", "01000", "00100", "00010"],
    ")": ["01000", "00100", "00010", "00010", "00010", "00100", "01000"],
}


def load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def to_number(value, default=0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def stock_cost(position: dict) -> float:
    shares = to_number(position.get("shares"))
    price = to_number(position.get("cost_price") or position.get("entry_price"))
    return shares * price


def build_perf_series(perf: dict, market: dict) -> dict:
    positions = perf.get("positions") or []
    price_history = perf.get("price_history") or {}
    start_cap = to_number(perf.get("starting_capital"), 450000.0)
    dates = set()

    for hist in price_history.values():
        dates.update(str(d) for d in hist.keys())
    for p in positions:
        for key in ("entry_date", "exit_date"):
            if p.get(key):
                dates.add(str(p[key])[:10])
        for ex in p.get("exits") or []:
            if ex.get("date"):
                dates.add(str(ex["date"])[:10])

    labels = sorted(d for d in dates if len(d) >= 10)
    if len(labels) < 2 or not positions:
        return {"labels": [], "total": [], "realized": [], "market": []}

    total_cost = sum(stock_cost(p) for p in positions)
    cash = start_cap - total_cost
    total_line = []
    realized_line = []

    for date in labels:
        market_value = 0.0
        realized_value = 0.0
        for p in positions:
            shares = to_number(p.get("shares"))
            cost = stock_cost(p)
            cost_price = cost / shares if shares else to_number(p.get("cost_price") or p.get("entry_price"))
            entry_date = str(p.get("entry_date") or date)[:10]
            if date < entry_date:
                market_value += cost
                realized_value += cost
                continue

            exits = p.get("exits") or []
            if exits:
                exited_shares = 0.0
                exited_net = 0.0
                for ex in exits:
                    if date >= str(ex.get("date") or "")[:10]:
                        exited_shares += to_number(ex.get("shares"))
                        exited_net += to_number(ex.get("exit_net"), to_number(ex.get("shares")) * to_number(ex.get("exit_price")))
                remaining = max(0.0, shares - exited_shares)
                market_value += exited_net
                realized_value += exited_net
                if remaining > 0:
                    price = latest_price(price_history.get(str(p.get("stock_id")), {}), date, cost_price)
                    market_value += remaining * price
                    realized_value += remaining * cost_price
            elif p.get("confirmed") and p.get("exit_date") and date >= str(p.get("exit_date"))[:10]:
                exit_value = to_number(p.get("exit_net"), shares * to_number(p.get("exit_price")))
                market_value += exit_value
                realized_value += exit_value
            else:
                price = latest_price(price_history.get(str(p.get("stock_id")), {}), date, cost_price)
                market_value += shares * price
                realized_value += cost

        total_line.append(round((cash + market_value) / start_cap * 100 - 100, 2))
        realized_line.append(round((cash + realized_value) / start_cap * 100 - 100, 2))

    return {
        "labels": labels,
        "total": total_line,
        "realized": realized_line,
        "market": build_market_series(labels, market),
    }


def latest_price(history: dict, date: str, fallback: float) -> float:
    keys = sorted(str(k) for k in history.keys() if str(k) <= date)
    if not keys:
        return fallback
    return to_number(history.get(keys[-1]), fallback)


def build_market_series(labels: list[str], market: dict, key: str = "TAIEX") -> list[float | None]:
    index_info = (market.get("indices") or {}).get(key) or {}
    history = dict(((market.get("history") or {}).get(key) or {}))
    if index_info.get("date") and index_info.get("close") is not None:
        history[str(index_info["date"])[:10]] = index_info["close"]
    dates = sorted(d for d, v in history.items() if math.isfinite(to_number(v, math.nan)))
    if len(dates) < 2:
        return []
    base_date = next((d for d in dates if d >= labels[0]), dates[0])
    base_close = to_number(history.get(base_date))
    if not base_close:
        return []
    result = []
    idx = 0
    last_close = None
    for label in labels:
        while idx < len(dates) and dates[idx] <= label:
            last_close = to_number(history.get(dates[idx]))
            idx += 1
        if label < base_date or last_close is None:
            result.append(None)
        else:
            result.append(round(last_close / base_close * 100 - 100, 2))
    return result if sum(v is not None for v in result) >= 2 else []


def new_canvas() -> list[list[tuple[int, int, int]]]:
    return [[COLORS["bg"] for _ in range(WIDTH)] for _ in range(HEIGHT)]


def set_px(img, x: int, y: int, color: tuple[int, int, int]):
    if 0 <= x < WIDTH and 0 <= y < HEIGHT:
        img[y][x] = color


def rect(img, x1: int, y1: int, x2: int, y2: int, color: tuple[int, int, int]):
    for y in range(max(0, y1), min(HEIGHT, y2 + 1)):
        row = img[y]
        for x in range(max(0, x1), min(WIDTH, x2 + 1)):
            row[x] = color


def line(img, x1: int, y1: int, x2: int, y2: int, color: tuple[int, int, int], width: int = 1):
    dx = abs(x2 - x1)
    dy = -abs(y2 - y1)
    sx = 1 if x1 < x2 else -1
    sy = 1 if y1 < y2 else -1
    err = dx + dy
    x, y = x1, y1
    half = max(0, width // 2)
    while True:
        for yy in range(y - half, y + half + 1):
            for xx in range(x - half, x + half + 1):
                set_px(img, xx, yy, color)
        if x == x2 and y == y2:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy


def circle(img, cx: int, cy: int, radius: int, color: tuple[int, int, int]):
    for y in range(cy - radius, cy + radius + 1):
        for x in range(cx - radius, cx + radius + 1):
            if (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2:
                set_px(img, x, y, color)


def text_width(text: str, scale: int = 2) -> int:
    return len(text) * 6 * scale


def draw_text(img, x: int, y: int, text: str, color: tuple[int, int, int], scale: int = 2):
    cursor = x
    for ch in text.upper():
        pattern = FONT.get(ch, FONT[" "])
        for row_i, row in enumerate(pattern):
            for col_i, bit in enumerate(row):
                if bit == "1":
                    rect(
                        img,
                        cursor + col_i * scale,
                        y + row_i * scale,
                        cursor + (col_i + 1) * scale - 1,
                        y + (row_i + 1) * scale - 1,
                        color,
                    )
        cursor += 6 * scale


def y_for(value: float, min_v: float, max_v: float) -> int:
    if max_v == min_v:
        return (PLOT_TOP + PLOT_BOTTOM) // 2
    return int(PLOT_BOTTOM - (value - min_v) / (max_v - min_v) * (PLOT_BOTTOM - PLOT_TOP))


def x_for(index: int, total: int) -> int:
    if total <= 1:
        return PLOT_LEFT
    return int(PLOT_LEFT + index / (total - 1) * (PLOT_RIGHT - PLOT_LEFT))


def nice_bounds(values: list[float]) -> tuple[float, float]:
    if not values:
        return -5.0, 5.0
    lo = min(values + [0.0])
    hi = max(values + [0.0])
    span = max(2.0, hi - lo)
    pad = span * 0.18
    lo -= pad
    hi += pad
    step = 5 if span > 20 else 2
    return math.floor(lo / step) * step, math.ceil(hi / step) * step


def draw_series(img, labels: list[str], values: list[float | None], color: tuple[int, int, int], min_v: float, max_v: float):
    prev = None
    for i, value in enumerate(values):
        if value is None:
            prev = None
            continue
        x = x_for(i, len(labels))
        y = y_for(float(value), min_v, max_v)
        if prev:
            line(img, prev[0], prev[1], x, y, color, 3)
        prev = (x, y)
    for i, value in enumerate(values):
        if value is None:
            continue
        x = x_for(i, len(labels))
        y = y_for(float(value), min_v, max_v)
        circle(img, x, y, 3, color)


def last_value(values: list[float | None]) -> float | None:
    for value in reversed(values):
        if value is not None:
            return float(value)
    return None


def write_png(path: str, img: list[list[tuple[int, int, int]]]):
    raw = bytearray()
    for row in img:
        raw.append(0)
        for r, g, b in row:
            raw.extend((r, g, b))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(png)


def draw_chart(series: dict):
    labels = series["labels"]
    total = series["total"]
    realized = series["realized"]
    market = series["market"]
    values = [v for v in total + realized + market if v is not None]
    min_v, max_v = nice_bounds(values)
    img = new_canvas()

    rect(img, 0, 0, WIDTH - 1, HEIGHT - 1, COLORS["bg"])
    rect(img, 24, 22, WIDTH - 24, HEIGHT - 28, COLORS["panel"])
    draw_text(img, 52, 36, "PERFORMANCE VS TAIEX", COLORS["text"], 3)
    generated = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    draw_text(img, WIDTH - 250, 42, f"UPDATED {generated}", COLORS["muted"], 2)

    for i in range(6):
        value = min_v + (max_v - min_v) * i / 5
        y = y_for(value, min_v, max_v)
        line(img, PLOT_LEFT, y, PLOT_RIGHT, y, COLORS["grid"], 1)
        label = f"{value:+.0f}%"
        draw_text(img, 22, y - 8, label, COLORS["muted"], 2)

    zero_y = y_for(0, min_v, max_v)
    line(img, PLOT_LEFT, zero_y, PLOT_RIGHT, zero_y, COLORS["zero"], 2)
    line(img, PLOT_LEFT, PLOT_TOP, PLOT_LEFT, PLOT_BOTTOM, COLORS["axis"], 2)
    line(img, PLOT_LEFT, PLOT_BOTTOM, PLOT_RIGHT, PLOT_BOTTOM, COLORS["axis"], 2)

    draw_series(img, labels, market, COLORS["market"], min_v, max_v)
    draw_series(img, labels, realized, COLORS["realized"], min_v, max_v)
    draw_series(img, labels, total, COLORS["total"], min_v, max_v)

    legend_y = HEIGHT - 48
    legend_x = 84
    for name, color in [
        ("TOTAL", COLORS["total"]),
        ("REALIZED", COLORS["realized"]),
        ("TAIEX", COLORS["market"]),
    ]:
        line(img, legend_x, legend_y + 8, legend_x + 34, legend_y + 8, color, 4)
        draw_text(img, legend_x + 44, legend_y, name, COLORS["text"], 2)
        legend_x += 190

    if labels:
        draw_text(img, PLOT_LEFT, PLOT_BOTTOM + 18, labels[0][5:].replace("-", "/"), COLORS["muted"], 2)
        end_label = labels[-1][5:].replace("-", "/")
        draw_text(img, PLOT_RIGHT - text_width(end_label, 2), PLOT_BOTTOM + 18, end_label, COLORS["muted"], 2)

    summary_x = WIDTH - 310
    summary_y = 94
    for i, (name, value, color) in enumerate(
        [
            ("TOTAL", last_value(total), COLORS["total"]),
            ("REALIZED", last_value(realized), COLORS["realized"]),
            ("TAIEX", last_value(market), COLORS["market"]),
        ]
    ):
        y = summary_y + i * 30
        draw_text(img, summary_x, y, f"{name} {value:+.1f}%" if value is not None else f"{name} --", color, 2)

    write_png(OUT_PATH, img)


def main() -> int:
    perf = load_json(PERF_PATH)
    market = load_json(MARKET_PATH)
    series = build_perf_series(perf, market)
    if not series["labels"]:
        print("[chart] no enough data to generate performance chart")
        return 0
    draw_chart(series)
    size_kb = os.path.getsize(OUT_PATH) / 1024
    print(f"[chart] wrote {OUT_PATH} ({size_kb:.1f} KB, {len(series['labels'])} points)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
