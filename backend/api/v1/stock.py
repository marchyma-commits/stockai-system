"""StockAI v2 — Stock Data API Endpoints

RESTful stock data endpoints with mock data providers.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from services import mock_data_provider as mdp

router = APIRouter(prefix="/api", tags=["stocks"])


@router.get("/stocks")
async def list_stocks():
    """List all available stocks with current prices."""
    return {"success": True, "data": mdp.get_stock_list(), "count": len(mdp.STOCK_UNIVERSE)}


@router.get("/stock/{symbol}")
async def get_stock_detail(symbol: str):
    """Get detailed stock info including price, technicals, and fundamentals."""
    stock = mdp.get_stock_info(symbol)
    if not stock:
        raise HTTPException(status_code=404, detail={"error": "stock_not_found", "symbol": symbol})
    return {"success": True, "data": stock}


@router.get("/stock/{symbol}/history")
async def get_stock_history(
    symbol: str,
    period: str = Query("1mo", description="Period: 1d, 5d, 1mo, 3mo, 1y"),
):
    """Get historical K-line data for charting."""
    stock = mdp.get_stock_info(symbol)
    if not stock:
        raise HTTPException(status_code=404, detail={"error": "stock_not_found", "symbol": symbol})

    # Map period to number of days
    period_map = {"1d": 1, "5d": 5, "1mo": 22, "3mo": 66, "1y": 252, "6mo": 126}
    days = period_map.get(period, 90)

    kline = mdp.generate_kline_data(symbol, periods=days)
    return {"success": True, "data": kline, "symbol": symbol, "period": period}


@router.get("/stock/{symbol}/bb")
async def get_bollinger_bands(symbol: str, period: str = Query("1mo", description="Period")):
    """Get Bollinger Bands data."""
    stock = mdp.get_stock_info(symbol)
    if not stock:
        raise HTTPException(status_code=404, detail={"error": "stock_not_found", "symbol": symbol})

    kline = mdp.generate_kline_data(symbol, periods=20)
    closes = [c["y"][3] for c in kline]

    # Simple BB calculation
    import statistics
    sma = statistics.mean(closes)
    std = statistics.stdev(closes) if len(closes) > 1 else 0

    timestamps = [c["x"] for c in kline]

    return {
        "success": True,
        "symbol": symbol,
        "upper": [round(sma + 2 * std, 2)] * len(timestamps),
        "middle": [round(sma, 2)] * len(timestamps),
        "lower": [round(sma - 2 * std, 2)] * len(timestamps),
        "timestamps": timestamps,
    }


@router.get("/predict/{symbol}")
async def predict_stock(symbol: str):
    """Get mock AI prediction for a stock."""
    stock = mdp.get_stock_info(symbol)
    if not stock:
        raise HTTPException(status_code=404, detail={"error": "stock_not_found", "symbol": symbol})

    price = stock["price"]
    return {
        "success": True,
        "symbol": symbol,
        "prediction": {
            "target_1w": round(price * random.uniform(0.95, 1.08), 2),
            "target_1m": round(price * random.uniform(0.90, 1.15), 2),
            "target_3m": round(price * random.uniform(0.85, 1.25), 2),
            "confidence": round(random.uniform(0.6, 0.95), 2),
            "signal": random.choice(["strong_buy", "buy", "hold", "sell", "strong_sell"]),
        },
    }


@router.get("/search")
async def search_stocks(q: str = Query(..., min_length=1, description="Search query")):
    """Search stocks by symbol or name."""
    results = mdp.search_stocks(q)
    return {"success": True, "data": results, "query": q, "count": len(results)}


@router.get("/hot-stocks")
async def get_hot_stocks():
    """Get a list of hot/popular stocks."""
    stocks = mdp.get_hot_stocks(limit=10)
    return {"success": True, "data": stocks}


@router.get("/realtime/{symbol}")
async def get_realtime_price(symbol: str):
    """Get simulated real-time stock price."""
    stock = mdp.get_stock_info(symbol)
    if not stock:
        raise HTTPException(status_code=404, detail={"error": "stock_not_found", "symbol": symbol})

    import random as rnd
    price = stock["price"]
    return {
        "success": True,
        "symbol": symbol,
        "price": round(price * (1 + rnd.uniform(-0.002, 0.002)), 2),
        "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }


# Need random for predict endpoint
import random  # noqa: E402
