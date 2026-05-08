"""StockAI — Stock API Endpoints (FastAPI)"""
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import JSONResponse
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
        if not data:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": f"股票代碼 {symbol} 無效", "symbol": symbol}
            )
        return {"success": True, "data": data}
    except Exception as e:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": f"股票代碼 {symbol} 無效", "symbol": symbol}
        )


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
        return JSONResponse(
            status_code=200,  # Return 200 with error flag so frontend can handle gracefully
            content={"success": False, "error": "搜尋失敗，請重試", "data": [], "total": 0}
        )


@router.get("/realtime/{symbol}")
async def get_realtime(symbol: str):
    """Get real-time stock data."""
    try:
        data = mdp.get_realtime(symbol)
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/stocks")
async def get_stock_list(market: str = Query("hk", description="Market: hk, us, a, or all")):
    """Get list of all available stocks by market."""
    market = market.lower()
    if market == "us":
        stocks = [mdp.get_stock_info(sym) for sym in sorted(mdp.US_STOCKS.keys())]
    elif market == "a":
        stocks = mdp.get_a_stock_list()
    elif market == "all":
        stocks = [mdp.get_stock_info(sym) for sym in sorted(mdp.ALL_STOCKS.keys())]
    else:
        stocks = mdp.get_hk_stock_list()

    return {"success": True, "data": stocks, "total": len(stocks)}


# ════════════════════════════════════════════════════════════
# New UI Endpoints
# ════════════════════════════════════════════════════════════

@router.get("/market/overview")
async def get_market_overview():
    """Get market index overview."""
    data = mdp.get_market_overview()
    return {"success": True, "data": data}


@router.get("/watchlist")
async def get_watchlist_data():
    """Get watchlist with prices."""
    data = mdp.get_watchlist_data()
    return {"success": True, "data": data}


@router.get("/capital-flow/market")
async def get_capital_flow_market():
    """Get market-level capital flow."""
    data = mdp.get_capital_flow_market()
    return {"success": True, "data": data}


@router.get("/capital-flow/stock/{symbol}")
async def get_stock_capital_flow(symbol: str = "0700.HK"):
    """Get capital flow for a specific stock."""
    data = mdp.get_stock_capital_flow(symbol)
    return {"success": True, "data": data}


@router.get("/capital-flow/history")
async def get_capital_flow_history(days: int = Query(20, description="Days of history")):
    """Get historical capital flow for trend chart."""
    data = mdp.get_capital_flow_history(days)
    return {"success": True, "data": data}


@router.get("/capital-flow/top-stocks")
async def get_capital_flow_top_stocks(limit: int = Query(5, description="Number of top stocks")):
    """Get top stocks by capital flow."""
    data = mdp.get_capital_flow_top_stocks(limit)
    return {"success": True, "data": data}


@router.get("/capital-flow/south-north")
async def get_south_north_flow():
    """Get South-North bound capital flow."""
    data = mdp.get_south_north_flow()
    return {"success": True, "data": data}


@router.get("/ai/signals")
async def get_ai_signals():
    """Get AI trading signals."""
    data = mdp.get_ai_signals()
    return {"success": True, "data": data}


@router.get("/news/sentiment-summary")
async def get_news_sentiment_summary():
    """Get news sentiment summary."""
    data = mdp.get_news_sentiment_summary()
    return {"success": True, "data": data}


@router.get("/ai/strategy/{symbol}")
async def get_ai_strategy(symbol: str = "0700.HK"):
    """Get AI trading strategy for a stock."""
    data = mdp.get_ai_strategy(symbol)
    return {"success": True, "data": data}
