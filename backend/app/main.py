import logging
import re
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import correlation_id, setup_logging

log = logging.getLogger("app.request")
_VALID_CID = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(title="Canvas Autograder API")
    register_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-ID"],
    )

    @app.middleware("http")
    async def correlation_and_timing(request: Request, call_next):
        incoming = request.headers.get("X-Correlation-ID", "")
        cid = incoming if _VALID_CID.match(incoming) else uuid.uuid4().hex
        request.state.correlation_id = cid
        token = correlation_id.set(cid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = cid
            log.info("request", extra={
                "method": request.method, "path": request.url.path, "status": response.status_code,
                "latency_ms": round((time.perf_counter() - start) * 1000),
            })
            return response
        finally:
            correlation_id.reset(token)

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    return app


app = create_app()
