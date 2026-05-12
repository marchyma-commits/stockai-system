"""StockAI v2 — Application Entry Point

FastAPI application with modular architecture.
Designed for Railway deployment with mock data providers.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from api.v1 import health, stock
from core.audit import audit_logger

# ── App Initialization ──
app = FastAPI(
    title="StockAI v2",
    description="Intelligent Stock Analysis System",
    version="2.0.0",
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
app.include_router(health.router)
app.include_router(stock.router)


# ── Static Files (Frontend) ──
FRONTEND_OUT = Path(__file__).parent.parent / "frontend" / "out"

if FRONTEND_OUT.exists():
    # Mount built frontend assets (Next.js static export)
    next_static = FRONTEND_OUT / "_next" / "static"
    if next_static.exists():
        app.mount("/_next/static", StaticFiles(directory=str(next_static)), name="next_static")
    # Serve all static assets from out directory
    app.mount("/static", StaticFiles(directory=str(FRONTEND_OUT)), name="frontend_static")


# ════════════════════════════════════════════════════════════
# Root & Error Handlers
# ════════════════════════════════════════════════════════════


@app.get("/", tags=["general"])
async def root():
    """Root endpoint — serves frontend or redirects to dashboard."""
    # Try direct index.html
    index_path = FRONTEND_OUT / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
    # Try dashboard page (Next.js static export)
    dashboard_path = FRONTEND_OUT / "dashboard" / "index.html"
    if dashboard_path.exists():
        return HTMLResponse(content=dashboard_path.read_text(encoding="utf-8"))
    dashboard_direct = FRONTEND_OUT / "dashboard.html"
    if dashboard_direct.exists():
        return HTMLResponse(content=dashboard_direct.read_text(encoding="utf-8"))
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/dashboard")


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(
        status_code=404,
        content={
            "success": False,
            "error": "endpoint_not_found",
            "path": str(request.url),
        },
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    await audit_logger.log(
        action="internal_error",
        details={"path": str(request.url), "error": str(exc)},
        status="error",
    )
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": "Internal server error"},
    )
