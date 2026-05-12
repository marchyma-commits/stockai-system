"""StockAI v2 — Mock Data Provider

Provides realistic mock stock data for development and demo.
Covers HK (35), US (10), and A-shares (5) = 50 stocks.
"""

from __future__ import annotations

import random
import math
from datetime import datetime, timedelta, timezone
from typing import Any

# ── Stock Universe ──

STOCK_UNIVERSE: list[dict[str, Any]] = [
    # ── Hong Kong (35) ──
    {"symbol": "0700.HK", "name": "騰訊控股", "exchange": "HKEX", "currency": "HKD", "base_price": 380.0},
    {"symbol": "9988.HK", "name": "阿里巴巴", "exchange": "HKEX", "currency": "HKD", "base_price": 118.0},
    {"symbol": "0005.HK", "name": "滙豐控股", "exchange": "HKEX", "currency": "HKD", "base_price": 72.0},
    {"symbol": "1810.HK", "name": "小米集團", "exchange": "HKEX", "currency": "HKD", "base_price": 28.0},
    {"symbol": "2318.HK", "name": "中國平安", "exchange": "HKEX", "currency": "HKD", "base_price": 62.0},
    {"symbol": "0941.HK", "name": "中國移動", "exchange": "HKEX", "currency": "HKD", "base_price": 72.0},
    {"symbol": "1211.HK", "name": "比亞迪股份", "exchange": "HKEX", "currency": "HKD", "base_price": 286.0},
    {"symbol": "3690.HK", "name": "美團", "exchange": "HKEX", "currency": "HKD", "base_price": 152.0},
    {"symbol": "1299.HK", "name": "友邦保險", "exchange": "HKEX", "currency": "HKD", "base_price": 68.0},
    {"symbol": "0388.HK", "name": "香港交易所", "exchange": "HKEX", "currency": "HKD", "base_price": 320.0},
    {"symbol": "0011.HK", "name": "恒生銀行", "exchange": "HKEX", "currency": "HKD", "base_price": 108.0},
    {"symbol": "0016.HK", "name": "新鴻基地產", "exchange": "HKEX", "currency": "HKD", "base_price": 88.0},
    {"symbol": "0017.HK", "name": "新世界發展", "exchange": "HKEX", "currency": "HKD", "base_price": 12.0},
    {"symbol": "0027.HK", "name": "銀河娛樂", "exchange": "HKEX", "currency": "HKD", "base_price": 42.0},
    {"symbol": "0066.HK", "name": "港鐵公司", "exchange": "HKEX", "currency": "HKD", "base_price": 32.0},
    {"symbol": "0083.HK", "name": "信和置業", "exchange": "HKEX", "currency": "HKD", "base_price": 10.0},
    # ── US (10) ──
    {"symbol": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ", "currency": "USD", "base_price": 198.0},
    {"symbol": "MSFT", "name": "Microsoft Corp", "exchange": "NASDAQ", "currency": "USD", "base_price": 425.0},
    {"symbol": "GOOGL", "name": "Alphabet Inc.", "exchange": "NASDAQ", "currency": "USD", "base_price": 175.0},
    {"symbol": "AMZN", "name": "Amazon.com Inc.", "exchange": "NASDAQ", "currency": "USD", "base_price": 195.0},
    {"symbol": "NVDA", "name": "NVIDIA Corp", "exchange": "NASDAQ", "currency": "USD", "base_price": 880.0},
    {"symbol": "META", "name": "Meta Platforms", "exchange": "NASDAQ", "currency": "USD", "base_price": 510.0},
    {"symbol": "TSLA", "name": "Tesla Inc.", "exchange": "NASDAQ", "currency": "USD", "base_price": 248.0},
    {"symbol": "JPM", "name": "JPMorgan Chase", "exchange": "NYSE", "currency": "USD", "base_price": 198.0},
    {"symbol": "V", "name": "Visa Inc.", "exchange": "NYSE", "currency": "USD", "base_price": 285.0},
    {"symbol": "TSM", "name": "TSMC ADR", "exchange": "NYSE", "currency": "USD", "base_price": 165.0},
    # ── A-Shares (5) ──
    {"symbol": "600519.SH", "name": "貴州茅臺", "exchange": "SSE", "currency": "CNY", "base_price": 1680.0},
    {"symbol": "000858.SZ", "name": "五糧液", "exchange": "SZSE", "currency": "CNY", "base_price": 145.0},
    {"symbol": "601318.SH", "name": "中國平安A", "exchange": "SSE", "currency": "CNY", "base_price": 42.0},
    {"symbol": "000333.SZ", "name": "美的集團", "exchange": "SZSE", "currency": "CNY", "base_price": 65.0},
    {"symbol": "600036.SH", "name": "招商銀行", "exchange": "SSE", "currency": "CNY", "base_price": 36.0},
]

# ── Price Cache ──
_price_cache: dict[str, dict[str, Any]] = {}


def _generate_price(base_price: float, volatility: float = 0.02) -> dict[str, float]:
    """Generate a realistic price with open/high/low/close."""
    change_pct = random.uniform(-volatility, volatility)
    last_close = base_price * (1 + random.uniform(-0.01, 0.01))
    open_price = last_close * (1 + random.uniform(-0.005, 0.005))
    close_price = open_price * (1 + change_pct)
    high_price = max(open_price, close_price) * (1 + random.uniform(0, 0.01))
    low_price = min(open_price, close_price) * (1 - random.uniform(0, 0.01))
    change = close_price - last_close
    change_percent = (change / last_close) * 100

    return {
        "price": round(close_price, 2),
        "open": round(open_price, 2),
        "high": round(high_price, 2),
        "low": round(low_price, 2),
        "prev_close": round(last_close, 2),
        "change": round(change, 2),
        "change_percent": round(change_percent, 2),
    }


def get_stock_info(symbol: str) -> dict[str, Any] | None:
    """Get stock info with generated price (cached per session)."""
    stock = next((s for s in STOCK_UNIVERSE if s["symbol"] == symbol), None)
    if not stock:
        return None

    if symbol not in _price_cache:
        price_data = _generate_price(stock["base_price"])
        _price_cache[symbol] = {
            **stock,
            **price_data,
            "volume": f"{random.randint(5, 100)}M",
            "week_high": round(stock["base_price"] * 1.15, 2),
            "week_low": round(stock["base_price"] * 0.85, 2),
            "market_cap": round(stock["base_price"] * random.uniform(1e8, 1e10), 0),
            "pe": round(random.uniform(8, 35), 1),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    return _price_cache[symbol]


def get_stock_list() -> list[dict[str, Any]]:
    """Return all stocks with current prices."""
    return [get_stock_info(s["symbol"]) for s in STOCK_UNIVERSE]


def generate_kline_data(symbol: str, periods: int = 90) -> list[dict[str, Any]]:
    """Generate mock K-line (candlestick) data."""
    stock = get_stock_info(symbol)
    if not stock:
        return []

    base = stock["price"]
    data = []
    now = datetime.now(timezone.utc)

    for i in range(periods):
        date = now - timedelta(days=periods - i)
        volatility = base * 0.02
        open_price = base + random.uniform(-volatility, volatility)
        close_price = open_price + random.uniform(-volatility, volatility)
        high_price = max(open_price, close_price) * (1 + random.uniform(0, 0.005))
        low_price = min(open_price, close_price) * (1 - random.uniform(0, 0.005))

        data.append({
            "x": date.strftime("%Y-%m-%d"),
            "y": [
                round(open_price, 2),
                round(high_price, 2),
                round(low_price, 2),
                round(close_price, 2),
            ],
        })
        base = close_price

    return data


def search_stocks(query: str) -> list[dict[str, Any]]:
    """Search stocks by symbol or name."""
    q = query.lower()
    results = []
    for stock in STOCK_UNIVERSE:
        if q in stock["symbol"].lower() or q in stock["name"].lower():
            info = get_stock_info(stock["symbol"])
            if info:
                results.append(info)
    return results[:10]


def get_hot_stocks(limit: int = 10) -> list[dict[str, Any]]:
    """Return randomly selected hot stocks."""
    selected = random.sample(STOCK_UNIVERSE, min(limit, len(STOCK_UNIVERSE)))
    return [get_stock_info(s["symbol"]) for s in selected]
