import asyncio
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager

import jwt
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import canvas, grading
from app.core.auth import User, current_user
from app.core.config import get_settings
from app.core.errors import error_response, register_error_handlers
from app.core.logging import correlation_id, setup_logging
from app.integrations.bedrock import bedrock_grader
from app.integrations.fakes import FakeCanvas, FakeGrader
from app.services.retention import sweep_forever
from app.services.runner import Runner

log = logging.getLogger("app.request")
_VALID_CID = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = create_async_engine(settings.database_url)
        app.state.sessions = async_sessionmaker(engine, expire_on_commit=False)
        app.state.canvas = FakeCanvas()  # shortcut: fake Canvas only, swap in the live client once it exists
        grader = bedrock_grader(settings) if settings.ai_mode == "bedrock" else FakeGrader()
        app.state.runner = Runner(app.state.sessions, app.state.canvas, grader, settings.grade_concurrency)
        await app.state.runner.resume()
        sweeper = asyncio.create_task(sweep_forever(app.state.sessions))
        yield
        sweeper.cancel()
        app.state.runner.stop()
        await engine.dispose()

    app = FastAPI(title="Canvas Autograder API", lifespan=lifespan)
    app.state.jwks = jwt.PyJWKClient(f"https://{settings.auth0_domain}/.well-known/jwks.json")
    register_error_handlers(app)
    app.include_router(canvas.router, dependencies=[Depends(current_user)])
    app.include_router(grading.router, dependencies=[Depends(current_user)])

    @app.middleware("http")
    async def correlation_and_timing(request: Request, call_next):
        incoming = request.headers.get("X-Correlation-ID", "")
        cid = incoming if _VALID_CID.match(incoming) else uuid.uuid4().hex
        request.state.correlation_id = cid
        token = correlation_id.set(cid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            log.error("unhandled error", exc_info=exc, extra={"safe_error_code": "INTERNAL_ERROR"})
            response = error_response(request, 500, "INTERNAL_ERROR", "Something went wrong. Nothing was published.")
        response.headers["X-Correlation-ID"] = cid
        log.info("request", extra={
            "method": request.method, "path": request.url.path, "status": response.status_code,
            "latency_ms": round((time.perf_counter() - start) * 1000),
        })
        correlation_id.reset(token)
        return response

    # Added last so it is outermost and 500 responses get CORS headers too.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-ID"],
    )

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    @app.get("/api/me")
    async def me(user: User):
        return {"sub": user}

    return app


app = create_app()
