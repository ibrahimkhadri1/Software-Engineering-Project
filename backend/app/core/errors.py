import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.core.logging import correlation_id

log = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.retryable = retryable


def error_response(request: Request, status: int, code: str, message: str,
                   retryable: bool = False) -> JSONResponse:
    cid = getattr(request.state, "correlation_id", None) or correlation_id.get()
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "retryable": retryable, "correlation_id": cid}},
        headers={"X-Correlation-ID": cid},
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    log.warning("request failed", extra={"safe_error_code": exc.code})
    return error_response(request, exc.status, exc.code, exc.message, exc.retryable)


async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return error_response(request, exc.status_code, f"HTTP_{exc.status_code}", str(exc.detail))


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Field names only: the values may be student content.
    fields = ", ".join(".".join(str(p) for p in e["loc"]) for e in exc.errors())
    return error_response(request, 422, "VALIDATION_ERROR", f"Invalid request: {fields}")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(HTTPException, http_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
