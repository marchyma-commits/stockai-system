"""StockAI v2 — Health Check Endpoint"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health_check():
    """Health check endpoint for Railway deployment monitoring."""
    return {
        "status": "ok",
        "service": "StockAI v2",
        "version": "2.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/api/status")
async def status():
    """Detailed system status."""
    return {
        "status": "running",
        "service": "StockAI v2",
        "version": "2.0.0",
        "uptime": "development_mode",
        "database": "mock",
        "cache": "mock",
    }
