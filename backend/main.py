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
FRONTEND_DIR = Path(__file__).parent.parent / "frontend" / "src"

if FRONTEND_DIR.exists():
    # Mount built frontend assets
    static_dir = FRONTEND_DIR.parent / "out"
    if static_dir.exists():
        app.mount("/_next", StaticFiles(directory=str(static_dir / "_next")), name="next")
        app.mount("/js", StaticFiles(directory=str(static_dir / "js")), name="js")
        app.mount("/css", StaticFiles(directory=str(static_dir / "css")), name="css")


# ════════════════════════════════════════════════════════════
# Root & Error Handlers
# ════════════════════════════════════════════════════════════


@app.get("/", tags=["general"])
async def root():
    """Root endpoint — serves frontend or API info."""
    index_path = FRONTEND_DIR.parent / "out" / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
    return {
        "service": "StockAI v2",
        "version": "2.0.0",
        "status": "running",
        "docs": "/docs",
        "frontend": "pending (Phase 2)",
    }


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
