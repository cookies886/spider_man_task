"""Request ID middleware + logging context.

Injects an X-Request-ID header (uuid4 if client didn't supply one) on every
request and exposes the value via a contextvar so log formatters can pick it up.
"""
from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdLogFilter(logging.Filter):
    """Adds %(request_id)s to log records — wire into your formatter."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


async def request_id_middleware(request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex
    token = request_id_var.set(rid)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response
    finally:
        request_id_var.reset(token)
