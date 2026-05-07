"""StockAI — Mock Data Provider for Cloud Deployment

Provides realistic mock stock data when live market data sources
(yfinance, etc.) are unavailable in the cloud environment.
"""
import random
import math
from datetime import datetime, timedelta
from typing import Optional

# ── Session-Level Price Cache ──
# Caches generated stock info per ticker within the same session.
# First call generates & caches; subsequent calls return cached value.
# New page refresh (new server request) triggers regeneration.
_stock_info_cache: dict[str, dict] = {}

# ── Stock Universe ──
HONG_KONG_STOCKS = {
    "0700.HK": {"name": "Tencent Holdings", "sector": "Technology"},
    "9988.HK": {"name": "Alibaba Group", "sector": "E-Commerce"},
    "0005.HK": {"name": "HSBC Holdings", "sector": "Banking"},
    "0999.HK": {"name": "Hua Hong Semiconductor", "sector": "Technology"},
    "1810.HK": {"name": "Xiaomi Corp", "sector": "Technology"},
    "9989.HK": {"name": "Dongfeng Motor", "sector": "Automotive"},
    "2318.HK": {"name": "Ping An Insurance", "sector": "Insurance"},
    "939.HK": {"name": "CCB", "sector": "Banking"},
    "1299.HK": {"name": "AIA Group", "sector": "Insurance"},
    "0001.HK": {"name": "CK Hutchison", "sector": "Conglomerate"},
    "0002.HK": {"name": "CLP Holdings", "sector": "Utilities"},
    "0003.HK": {"name": "HK & China Gas", "sector": "Utilities"},
    "0016.HK": {"name": "SHK Properties", "sector": "Property"},
    "0017.HK": {"name": "New World Dev", "sector": "Property"},
    "0019.HK": {"name": "Swire Pacific", "sector": "Conglomerate"},
    "0027.HK": {"name": "Galaxy Entertainment", "sector": "Gaming"},
    "0388.HK": {"name": "HKEX", "sector": "Finance"},
    "0883.HK": {"name": "CNOOC", "sector": "Energy"},
    "0900.HK": {"name": "Aeon Stores", "sector": "Retail"},
    "0941.HK": {"name": "China Mobile", "sector": "Telecom"},
    "0968.HK": {"name": "Xinyi Glass", "sector": "Manufacturing"},
    "0981.HK": {"name": "SMIC", "sector": "Semiconductor"},
    "1024.HK": {"name": "Kuaishou Tech", "sector": "Technology"},
    "1211.HK": {"name": "BYD Co.", "sector": "Automotive"},
    "1398.HK": {"name": "ICBC", "sector": "Banking"},
    "1928.HK": {"name": "Sands China", "sector": "Gaming"},
    "2382.HK": {"name": "Sunny Optical", "sector": "Technology"},
    "2800.HK": {"name": "Tracker Fund", "sector": "ETF"},
    "2823.HK": {"name": "A50 ETF", "sector": "ETF"},
    "3690.HK": {"name": "Meituan", "sector": "E-Commerce"},
    "3988.HK": {"name": "Bank of China", "sector": "Banking"},
    "6189.HK": {"name": "Nongfu Spring", "sector": "Beverage"},
    "6862.HK": {"name": "Haidi Lao", "sector": "Restaurant"},
    "6888.HK": {"name": "Alibaba Health", "sector": "Healthcare"},
    "9618.HK": {"name": "JD.com", "sector": "E-Commerce"},
    "9626.HK": {"name": "Bilibili", "sector": "Technology"},
    "9888.HK": {"name": "Baido", "sector": "Technology"},
    "9923.HK": {"name": "YES Securit", "sector": "Finance"},
    "9961.HK": {"name": "Trip.com", "sector": "Travel"},
}

US_STOCKS = {
    "AAPL": {"name": "Apple Inc.", "sector": "Technology"},
    "GOOGL": {"name": "Alphabet Inc.", "sector": "Technology"},
    "MSFT": {"name": "Microsoft Corp", "sector": "Technology"},
    "AMZN": {"name": "Amazon.com", "sector": "E-Commerce"},
    "META": {"name": "Meta Platforms", "sector": "Technology"},
    "TSLA": {"name": "Tesla Inc.", "sector": "Automotive"},
    "NVDA": {"name": "NVIDIA Corp", "sector": "Semiconductor"},
    "JPM": {"name": "JPMorgan Chase", "sector": "Banking"},
    "V": {"name": "Visa Inc.", "sector": "Finance"},
    "JNJ": {"name": "Johnson & Johnson", "sector": "Healthcare"},
}

ALL_STOCKS = {**HONG_KONG_STOCKS, **US_STOCKS}


def _seeded_random(symbol: str, field: str = "price") -> float:
    """Deterministic pseudo-random based on symbol for consistent mock values."""
    seed = abs(hash(f"{symbol}_{field}")) % 10000
    return seed / 10000.0


def _base_price(symbol: str) -> float:
    """Generate a realistic base price for each stock."""
    prices = {
        # HK Stocks
        "0700.HK": 520.0, "9988.HK": 85.0, "0005.HK": 72.0,
        "0999.HK": 18.0, "1810.HK": 30.0, "9989.HK": 3.5,
        "2318.HK": 55.0, "0939.HK": 6.5, "1299.HK": 75.0,
        "0001.HK": 52.0, "0002.HK": 65.0, "0003.HK": 12.0,
        "0016.HK": 82.0, "0017.HK": 18.0, "0019.HK": 45.0,
        "0027.HK": 38.0, "0388.HK": 310.0, "0883.HK": 18.0,
        "0900.HK": 2.0, "0941.HK": 72.0, "0968.HK": 14.0,
        "0981.HK": 28.0, "1024.HK": 52.0, "1211.HK": 280.0,
        "1398.HK": 5.0, "1928.HK": 28.0, "2382.HK": 42.0,
        "2800.HK": 22.0, "2823.HK": 13.0, "3690.HK": 160.0,
        "3988.HK": 4.0, "6189.HK": 42.0, "6862.HK": 18.0,
        "6888.HK": 5.0, "9618.HK": 135.0, "9626.HK": 100.0,
        "9888.HK": 85.0, "9923.HK": 10.0, "9961.HK": 450.0,
        # US Stocks
        "AAPL": 230.0, "GOOGL": 175.0, "MSFT": 425.0,
        "AMZN": 200.0, "META": 550.0, "TSLA": 350.0,
        "NVDA": 125.0, "JPM": 210.0, "V": 280.0,
        "JNJ": 160.0,
    }
    return prices.get(symbol, 50.0)


def get_stock_info(symbol: str) -> dict:
    """Get basic stock info with session-level caching.
    
    First call generates the price deterministically and caches it.
    Subsequent calls within the same session return the cached value,
    ensuring consistent prices across all pages (watchlist, detail, etc.).
    """
    # Return cached result if available (session-level consistency)
    if symbol in _stock_info_cache:
        cached = dict(_stock_info_cache[symbol])
        cached["timestamp"] = datetime.now().isoformat()
        return cached

    info = ALL_STOCKS.get(symbol, {"name": symbol, "sector": "Unknown"})
    base = _base_price(symbol)
    seed_variation = _seeded_random(symbol, "variation") * 0.2 - 0.1
    price = round(base * (1 + seed_variation), 2)
    change_pct = round((_seeded_random(symbol, "change") * 0.06) - 0.03, 2)
    change = round(price * change_pct, 2)

    result = {
        "symbol": symbol,
        "name": info["name"],
        "sector": info["sector"],
        "price": price,
        "change": change,
        "change_percent": change_pct * 100,
        "volume": int(_seeded_random(symbol, "volume") * 50_000_000),
        "market_cap": round(price * _seeded_random(symbol, "mc") * 1_000_000_000, 2),
        "high_52w": round(base * 1.3, 2),
        "low_52w": round(base * 0.7, 2),
        "pe_ratio": round(8 + _seeded_random(symbol, "pe") * 30, 2),
        "dividend_yield": round(_seeded_random(symbol, "div") * 8, 2),
        "timestamp": datetime.now().isoformat(),
    }

    # Cache the result for session-level consistency
    _stock_info_cache[symbol] = result
    return result


def get_stock_history(symbol: str, days: int = 90) -> list[dict]:
    """Generate realistic OHLCV history, scaled to converge with the cached session price.

    After generating the raw OHLCV sequence, we calculate a scale_factor so that the
    last candle's close equals the cached price from get_stock_info(). This ensures
    the K-line chart's last close always matches the watchlist / stock-info price.
    """
    # Grab the cached session price first (triggers caching if not yet called)
    cached_info = get_stock_info(symbol)
    cached_price = cached_info["price"]

    base = _base_price(symbol)
    history = []
    today = datetime.now()

    price = base * 0.8
    for i in range(days, 0, -1):
        date = today - timedelta(days=i)
        if date.weekday() >= 5:  # Skip weekends
            continue

        drift = _seeded_random(f"{symbol}_drift_{i}", "drift") * 0.04 - 0.02
        volatility = _seeded_random(f"{symbol}_vol_{i}", "vol") * 0.03 + 0.005

        price = price * (1 + drift)
        high = price * (1 + volatility * 2)
        low = price * (1 - volatility * 1.5)
        volume = int(_seeded_random(f"{symbol}_vol_{i}", "vlm") * 30_000_000 + 5_000_000)

        history.append({
            "date": date.strftime("%Y-%m-%d"),
            "open": round(price * (1 - volatility * 0.5), 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(price, 2),
            "volume": volume,
        })

    # ── Scale entire history so last close matches the cached price ──
    if history:
        last_close = history[-1]["close"]
        if last_close > 0:
            scale_factor = cached_price / last_close
            for bar in history:
                bar["open"] = round(bar["open"] * scale_factor, 2)
                bar["high"] = round(bar["high"] * scale_factor, 2)
                bar["low"] = round(bar["low"] * scale_factor, 2)
                bar["close"] = round(bar["close"] * scale_factor, 2)

    return history


def get_bollinger_bands(symbol: str, days: int = 90) -> list[dict]:
    """Generate Bollinger Bands based on mock history."""
    history = get_stock_history(symbol, days)

    bands = []
    for i in range(len(history)):
        # Calculate SMA of last 20 periods
        window = history[max(0, i - 19):i + 1]
        closes = [p["close"] for p in window]
        sma = sum(closes) / len(closes)
        variance = sum((c - sma) ** 2 for c in closes) / len(closes)
        std_dev = math.sqrt(variance)

        bands.append({
            "date": history[i]["date"],
            "upper": round(sma + 2 * std_dev, 2),
            "middle": round(sma, 2),
            "lower": round(sma - 2 * std_dev, 2),
            "close": history[i]["close"],
        })

    return bands


def get_hot_stocks(limit: int = 10) -> list[dict]:
    """Get mock hot/trending stocks."""
    symbols = list(HONG_KONG_STOCKS.keys())
    random.seed(42)  # Fixed seed for consistent ordering
    random.shuffle(symbols)
    random.seed()  # Reset seed

    hot = []
    for sym in symbols[:limit]:
        info = get_stock_info(sym)
        info["heat_score"] = round(_seeded_random(sym, "heat") * 100, 1)
        hot.append(info)

    # Sort by heat score descending
    hot.sort(key=lambda x: x["heat_score"], reverse=True)
    return hot


def search_stocks(query: str) -> list[dict]:
    """Search stocks by symbol or name."""
    query = query.upper().strip()
    results = []

    for sym, info in ALL_STOCKS.items():
        if query in sym.upper() or query in info["name"].upper():
            results.append(get_stock_info(sym))

    return results[:20]


def get_prediction(symbol: str) -> dict:
    """Generate mock AI prediction."""
    info = get_stock_info(symbol)
    score = _seeded_random(symbol, "prediction")

    if score > 0.6:
        direction = "bullish"
        confidence = round(0.6 + score * 0.35, 2)
        target = round(info["price"] * (1.05 + score * 0.2), 2)
    elif score > 0.3:
        direction = "neutral"
        confidence = round(0.4 + score * 0.4, 2)
        target = round(info["price"] * (1 + score * 0.1), 2)
    else:
        direction = "bearish"
        confidence = round(0.5 + (1 - score) * 0.3, 2)
        target = round(info["price"] * (0.85 + score * 0.15), 2)

    return {
        "symbol": symbol,
        "prediction": direction,
        "confidence": confidence,
        "current_price": info["price"],
        "target_price": target,
        "signals": [
            {"indicator": "RSI", "value": round(30 + score * 40, 1), "signal": "neutral"},
            {"indicator": "MACD", "value": round(score * 2 - 1, 3), "signal": direction},
            {"indicator": "SMA_50_200", "value": round(score * 100, 1), "signal": "bullish" if score > 0.5 else "bearish"},
        ],
        "timestamp": datetime.now().isoformat(),
    }


def get_realtime(symbol: str) -> dict:
    """Generate mock real-time data.

    Uses the exact cached session price (no artificial micro-change) so that
    the realtime endpoint always matches the watchlist / stock-info price.
    """
    base_info = get_stock_info(symbol)

    return {
        "symbol": symbol,
        "price": base_info["price"],
        "change": base_info["change"],
        "change_percent": base_info["change_percent"],
        "volume": base_info["volume"] + int(_seeded_random(symbol, "rtv") * 100000),
        "bid": round(base_info["price"] * 0.999, 3),
        "ask": round(base_info["price"] * 1.001, 3),
        "timestamp": datetime.now().isoformat(),
    }


def get_system_status() -> dict:
    """Get mock system status."""
    return {
        "status": "running",
        "uptime": "0d 1h 23m",
        "version": "1.7.0",
        "mode": "cloud",
        "data_source": "mock",
        "api_requests_today": int(_seeded_random("requests", "today") * 10000),
        "stocks_monitored": len(HONG_KONG_STOCKS),
        "last_update": datetime.now().isoformat(),
        "memory_usage_mb": round(128 + _seeded_random("mem", "usage") * 64, 1),
    }


def get_hk_stock_list() -> list[dict]:
    """Get list of all Hong Kong stocks."""
    stocks = []
    for sym in sorted(HONG_KONG_STOCKS.keys()):
        stocks.append(get_stock_info(sym))
    return stocks


def get_market_overview() -> dict:
    """Get market index overview (HSI, TECH, A50, SHCOMP)."""
    seed = _seeded_random("market", "overview")
    return {
        "indices": [
            {"name": "HSI", "value": 22148.0, "change": round(seed * 150 - 30, 2), "change_pct": round(seed * 1.5 - 0.3, 2), "direction": "up" if seed > 0.4 else "down"},
            {"name": "TECH", "value": 5326.0, "change": round(seed * 80 - 20, 2), "change_pct": round(seed * 2.0 - 0.4, 2), "direction": "up" if seed > 0.35 else "down"},
            {"name": "A50", "value": 12886.0, "change": round(seed * 60 - 50, 2), "change_pct": round(seed * 1.2 - 0.5, 2), "direction": "down" if seed < 0.5 else "up"},
            {"name": "SHCOMP", "value": 3286.0, "change": round(seed * 40 - 10, 2), "change_pct": round(seed * 0.8 - 0.2, 2), "direction": "up" if seed > 0.45 else "down"},
        ],
        "timestamp": datetime.now().isoformat(),
    }


def get_watchlist_data() -> list[dict]:
    """Get watchlist with real-time prices."""
    watchlist_symbols = ["0700.HK", "9988.HK", "0941.HK", "1211.HK", "3690.HK"]
    results = []
    for sym in watchlist_symbols:
        info = get_stock_info(sym)
        results.append({
            "symbol": sym,
            "name": HONG_KONG_STOCKS.get(sym, {}).get("name", sym),
            "price": info["price"],
            "change": info["change"],
            "change_percent": info["change_percent"],
            "direction": "up" if info["change"] >= 0 else "down",
        })
    return results


def get_capital_flow_market() -> dict:
    """Get market-level capital flow data."""
    seed = _seeded_random("capital", "market")
    return {
        "total": {
            "main_force": round(seed * 200 + 28, 0),
            "retail": round((1 - seed) * 100 - 32, 0),
        },
        "sectors": [
            {"name": "科技", "flow": round(seed * 80 + 10, 0)},
            {"name": "金融", "flow": round(seed * 40 + 8, 0)},
            {"name": "醫藥", "flow": round(seed * 20 - 5, 0)},
            {"name": "消費", "flow": round(seed * 15 - 10, 0)},
            {"name": "能源", "flow": round(seed * 10 + 2, 0)},
        ],
        "timestamp": datetime.now().isoformat(),
    }


def get_stock_capital_flow(symbol: str = "0700.HK") -> dict:
    """Get capital flow details for a specific stock."""
    seed = _seeded_random(symbol, "cap_flow")
    return {
        "symbol": symbol,
        "name": HONG_KONG_STOCKS.get(symbol, {}).get("name", symbol),
        "details": {
            "超大單": round(seed * 5 + 2, 1),
            "大單": round(seed * 3 + 1, 1),
            "中單": round((1 - seed) * 2 - 1, 1),
            "小單": round((1 - seed) * 3 - 2, 1),
        },
        "timestamp": datetime.now().isoformat(),
    }


def get_capital_flow_history(days: int = 20) -> list[dict]:
    """Get historical capital flow data for trend chart."""
    history = []
    today = datetime.now()
    base = _seeded_random("cap_hist", "base") * 100
    for i in range(days, 0, -1):
        date = today - timedelta(days=i)
        if date.weekday() >= 5:
            continue
        drift = _seeded_random(f"cap_{i}", "drift") * 30 - 15
        history.append({
            "date": date.strftime("%Y-%m-%d"),
            "main_force": round(base + drift + _seeded_random(f"cap_{i}", "main") * 20, 0),
            "retail": round(-base * 0.3 + drift * 0.2 + _seeded_random(f"cap_{i}", "retail") * 10, 0),
        })
    return history


def get_capital_flow_top_stocks(limit: int = 5) -> list[dict]:
    """Get top stocks by capital flow."""
    symbols = list(HONG_KONG_STOCKS.keys())
    results = []
    for sym in symbols[:limit]:
        info = get_stock_info(sym)
        seed = _seeded_random(sym, "top_flow")
        results.append({
            "symbol": sym,
            "name": HONG_KONG_STOCKS.get(sym, {}).get("name", sym),
            "net_flow": round(seed * 10 - 2, 1),
            "price": info["price"],
            "change_pct": info["change_percent"],
        })
    return sorted(results, key=lambda x: x["net_flow"], reverse=True)


def get_south_north_flow() -> dict:
    """Get South-North bound capital flow data."""
    seed = _seeded_random("south_north", "flow")
    return {
        "滬股通": round(seed * 50 - 10, 1),
        "深股通": round(seed * 40 - 5, 1),
        "港股通(滬)": round(seed * 30 + 15, 1),
        "港股通(深)": round(seed * 25 + 10, 1),
        "timestamp": datetime.now().isoformat(),
    }


def get_ai_signals() -> list[dict]:
    """Get AI trading signals for watchlist stocks."""
    signals = [
        {"symbol": "0700.HK", "name": "騰訊", "signal": "買入", "confidence": 85, "reason": "AI利好", "direction": "up"},
        {"symbol": "0941.HK", "name": "中移動", "signal": "賣出", "confidence": 72, "reason": "資金流出", "direction": "down"},
        {"symbol": "9988.HK", "name": "阿里", "signal": "買入", "confidence": 78, "reason": "業績改善", "direction": "up"},
        {"symbol": "1211.HK", "name": "比亞迪", "signal": "持有", "confidence": 65, "reason": "觀望", "direction": "neutral"},
    ]
    return signals


def get_news_sentiment_summary() -> list[dict]:
    """Get news sentiment summary for display in bottom bar."""
    return [
        {"symbol": "0700.HK", "title": "騰訊AI業務利好", "sentiment": "positive", "summary": "AI業務增長強勁"},
        {"symbol": "3690.HK", "title": "美團外賣業務受壓", "sentiment": "negative", "summary": "競爭加劇利淡"},
        {"symbol": "9988.HK", "title": "阿里雲收入超預期", "sentiment": "positive", "summary": "雲業務復甦"},
    ]


def get_ai_strategy(symbol: str = "0700.HK") -> dict:
    """Get AI-generated trading strategy for a stock."""
    info = get_stock_info(symbol)
    seed = _seeded_random(symbol, "strategy")
    action = "buy" if seed > 0.6 else ("sell" if seed < 0.3 else "hold")
    score = round(50 + seed * 40, 0)
    return {
        "symbol": symbol,
        "action": action,
        "overall_score": score,
        "confidence": "高" if score > 75 else ("中" if score > 55 else "低"),
        "recommended_position": f"{round(seed * 30 + 5)}%" if action != "sell" else "0%",
        "risk_reward": round(1.5 + seed * 2, 1),
        "entry": {
            "buy_price": round(info["price"] * 0.98, 2),
            "stop_loss": round(info["price"] * 0.93, 2),
        },
        "exit": {
            "target_1": round(info["price"] * 1.05, 2),
            "target_2": round(info["price"] * 1.12, 2),
        },
        "signals": {
            "trend": "bullish" if action == "buy" else ("bearish" if action == "sell" else "neutral"),
            "rsi": 55 + round(seed * 20, 0),
            "macd": "golden_cross" if action == "buy" else ("death_cross" if action == "sell" else "neutral"),
            "kdj": 50 + round(seed * 20, 0),
            "bollinger": "middle",
        },
    }
