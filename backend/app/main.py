"""StockAI — FastAPI Application Entry Point

Production deployment runs on Railway with mock data providers
for cloud compatibility. Live data sources can be added via
the service layer.

Usage:
    uvicorn backend.app.main:app --host 0.0.0.0 --port 8080 --reload
"""
import json
import os
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.stock import router as stock_router

# ── App Initialization ──
app = FastAPI(
    title="StockAI - Intelligent Stock Analysis System",
    description="Stock analysis, prediction, and monitoring system",
    version="1.7.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Include Routers ──
app.include_router(stock_router)


# ════════════════════════════════════════════════════════════
# Static Files (Frontend)
# ════════════════════════════════════════════════════════════

FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"

# Mount static directories
app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")
app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")


# ════════════════════════════════════════════════════════════
# Root & Static Routes
# ════════════════════════════════════════════════════════════

@app.get("/", tags=["general"])
async def root():
    """Serve the main frontend page."""
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
    return {
        "service": "StockAI",
        "version": "1.7.0",
        "status": "running",
        "docs": "/docs",
        "endpoints": {
            "health": "/api/health",
            "status": "/api/status",
            "stocks": "/api/stocks",
            "stock_detail": "/api/stock/{symbol}",
            "stock_history": "/api/stock/{symbol}/history",
            "bollinger_bands": "/api/stock/{symbol}/bb",
            "prediction": "/api/predict/{symbol}",
            "hot_stocks": "/api/hot-stocks",
            "search": "/api/search?q={query}",
            "realtime": "/api/realtime/{symbol}",
        },
    }


@app.get("/watchlist.json", tags=["general"])
async def get_watchlist():
    """Serve watchlist.json from the project root."""
    watchlist_path = Path(__file__).parent.parent.parent / "watchlist.json"
    if watchlist_path.exists():
        data = json.loads(watchlist_path.read_text())
        return JSONResponse(content=data)
    return JSONResponse(
        content={
            "watchlist": ["0700.HK", "9988.HK", "0005.HK", "1810.HK", "2318.HK"],
            "last_updated": datetime.now().isoformat(),
        }
    )


# ════════════════════════════════════════════════════════════
# Error Handlers
# ════════════════════════════════════════════════════════════

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(
        status_code=404,
        content={"success": False, "error": "Endpoint not found", "path": str(request.url)},
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Internal server error"},
    )
