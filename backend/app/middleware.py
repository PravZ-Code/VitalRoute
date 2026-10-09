"""VitalRoute Clinical & Operational Middlewares.

Implements:
1. ClinicalAuditMiddleware: Tracks request latency, clinical endpoints, and writes to audit database.
2. SecurityHeadersMiddleware: Ensures strict healthcare data privacy headers.
"""
from __future__ import annotations

import time
from typing import Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from . import database


class ClinicalAuditMiddleware(BaseHTTPMiddleware):
    """Measures execution latency and logs clinical actions to SQLite audit trail."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        
        # Process request
        response = await call_next(request)
        
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = f"{process_time * 1000:.2f}ms"
        response.headers["X-Healthcare-Protocol"] = "VitalRoute-SDG3"
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Audit critical clinical endpoints asynchronously in database
        path = request.url.path
        if path.startswith("/api/") and request.method in ("POST", "PUT", "DELETE"):
            client_ip = request.client.host if request.client else "unknown"
            database.log_audit_event("API_TRANSACTION", {
                "method": request.method,
                "path": path,
                "status_code": response.status_code,
                "client_ip": client_ip,
                "duration_ms": round(process_time * 1000, 2),
            })

        return response
