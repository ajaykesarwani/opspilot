import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from opspilot_common.correlation import (
    CORRELATION_ID_HEADER,
    resolve_correlation_id,
    set_correlation_id,
)

logger = logging.getLogger("opspilot_api.access")


def install_correlation_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def correlation_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        correlation_id = resolve_correlation_id(request.headers.get(CORRELATION_ID_HEADER))
        set_correlation_id(correlation_id)
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[CORRELATION_ID_HEADER] = correlation_id
            return response
        finally:
            logger.info(
                "request_completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
