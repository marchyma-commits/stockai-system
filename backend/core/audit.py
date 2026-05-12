"""StockAI v2 — Audit Log Middleware

Append-only audit logging for SFC compliance.
All actions are logged with timestamp, user, IP, and action details.
Retention: ≥ 2 years (HK PDPO compliance).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Request

logger = logging.getLogger("stockai.audit")


class AuditLogger:
    """Append-only audit logger.

    Writes JSONL format to both file and database.
    For Phase 1: file-based. Phase 3+: DB-backed.
    """

    def __init__(self, log_dir: Path | None = None):
        from core.config import get_settings

        settings = get_settings()
        self.log_dir = log_dir or settings.audit_log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _get_log_file(self) -> Path:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self.log_dir / f"audit-{today}.jsonl"

    def log(
        self,
        action: str,
        user_id: str | None = None,
        ip_address: str | None = None,
        details: dict[str, Any] | None = None,
        status: str = "success",
    ) -> None:
        """Write an audit log entry (append-only)."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "user_id": user_id,
            "ip_address": ip_address,
            "details": details or {},
            "status": status,
        }
        log_file = self._get_log_file()
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        logger.info(f"AUDIT: {action} | user={user_id} | status={status}")

    async def log_request(self, request: Request, action: str, **kwargs) -> None:
        """Convenience: log from a FastAPI request object."""
        self.log(
            action=action,
            user_id=kwargs.get("user_id"),
            ip_address=request.client.host if request.client else None,
            details=kwargs.get("details"),
            status=kwargs.get("status", "success"),
        )


# Singleton
audit_logger = AuditLogger()


async def audit_middleware(request: Request, call_next):
    """FastAPI middleware for automatic request audit logging."""
    response = await call_next(request)
    # Log non-GET requests for audit trail
    if request.method != "GET":
        await audit_logger.log_request(
            request,
            action=f"{request.method} {request.url.path}",
            status="success" if response.status_code < 400 else "error",
            details={"status_code": response.status_code},
        )
    return response
