import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.core.errors import AppError
from app.core.logging import JsonFormatter
from app.main import create_app


@pytest.fixture
def client():
    app = create_app()

    @app.get("/test/app-error")
    async def app_error():
        raise AppError("BEDROCK_INVALID_OUTPUT", "The grading model returned an invalid result.", 502)

    @app.get("/test/crash")
    async def crash():
        raise RuntimeError("secret student text must not leak")

    @app.get("/test/needs-int")
    async def needs_int(n: int):
        return {"n": n}

    return TestClient(app, raise_server_exceptions=False)


def test_healthz_returns_ok_with_correlation_id(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert len(r.headers["X-Correlation-ID"]) == 32


def test_valid_incoming_correlation_id_is_kept(client):
    r = client.get("/healthz", headers={"X-Correlation-ID": "abc12345-trace"})
    assert r.headers["X-Correlation-ID"] == "abc12345-trace"


def test_malformed_correlation_id_is_replaced(client):
    r = client.get("/healthz", headers={"X-Correlation-ID": "<script>"})
    assert r.headers["X-Correlation-ID"] != "<script>"


def test_app_error_uses_envelope(client):
    r = client.get("/test/app-error")
    assert r.status_code == 502
    err = r.json()["error"]
    assert err["code"] == "BEDROCK_INVALID_OUTPUT"
    assert err["retryable"] is False
    assert err["correlation_id"] == r.headers["X-Correlation-ID"]


def test_unknown_route_uses_envelope(client):
    r = client.get("/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "HTTP_404"


def test_validation_error_names_fields_not_values(client):
    r = client.get("/test/needs-int", params={"n": "not-a-number"})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert "not-a-number" not in err["message"]


def test_unhandled_error_is_generic_and_correlated(client):
    r = client.get("/test/crash", headers={"X-Correlation-ID": "crash-trace-1", "Origin": "http://localhost:5173"})
    assert r.status_code == 500
    err = r.json()["error"]
    assert err["code"] == "INTERNAL_ERROR"
    assert "secret" not in r.text
    assert err["correlation_id"] == r.headers["X-Correlation-ID"] == "crash-trace-1"
    assert r.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"


def test_log_formatter_drops_unsafe_extra_fields():
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "graded", None, None)
    record.path = "/healthz"
    record.submission_text = "student answer"
    entry = json.loads(JsonFormatter().format(record))
    assert entry["path"] == "/healthz"
    assert "submission_text" not in entry
    assert "student answer" not in json.dumps(entry)
