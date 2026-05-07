"""StockAI — Stock API Endpoints (FastAPI)"""
from fastapi import APIRouter, Query, HTTPException
from typing import Optional

from backend.app.services import mock_data_provider as mdp

router = APIRouter(prefix="/api", tags=["stocks"])


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "version": "1.7.0",
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "mode": "cloud-mock",
    }


@router.get("/status")
async def get_status():
    """System status."""
    return {
        "success": True,
        "data": mdp.get_system_status(),
    }


@router.get("/stock/{symbol}")
async def get_stock(symbol: str):
    """Get stock details."""
    try:
        data = mdp.get_stock_info(symbol)
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Stock {symbol} not found")


@router.get("/stock/{symbol}/history")
async def get_stock_history(
    symbol: str,
    days: int = Query(90, description="Number of days of history"),
):
    """Get stock price history."""
    try:
        data = mdp.get_stock_history(symbol, days)
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/stock/{symbol}/bb")
async def get_bollinger_bands(
    symbol: str,
    days: int = Query(90, description="Number of days"),
):
    """Get Bollinger Bands for a stock."""
    try:
        data = mdp.get_bollinger_bands(symbol, days)
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/predict/{symbol}")
async def get_prediction(symbol: str):
    """Get AI prediction for a stock."""
    try:
        data = mdp.get_prediction(symbol)
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/hot-stocks")
async def get_hot_stocks(limit: int = Query(10, description="Number of hot stocks")):
    """Get trending/hot stocks."""
    try:
        data = mdp.get_hot_stocks(limit)
        return {"success": True, "data": data, "total": len(data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search")
async def search_stock(q: str = Query("", description="Search query")):
    """Search stocks by symbol or name."""
    if not q:
        return {"success": True, "data": [], "total": 0}
    try:
        data = mdp.search_stocks(q)
        return {"success": True, "data": data, "total": len(data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/realtime/{symbol}")
async def get_realtime(symbol: str):
    """Get real-time stock data."""
    try:
        data = mdp.get_realtime(symbol)
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/stocks")
async def get_stock_list(market: str = Query("hk", description="Market: hk or us")):
    """Get list of all available stocks."""
    if market.lower() == "us":
        stocks = [mdp.get_stock_info(sym) for sym in sorted(mdp.US_STOCKS.keys())]
    else:
        stocks = mdp.get_hk_stock_list()

    return {"success": True, "data": stocks, "total": len(stocks)}
