import re
import uuid

import jwt
import pytest
from conftest import GRADER, FakeJwks, token
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    app = create_app()
    app.state.jwks = FakeJwks()
    return TestClient(app)


def me(client, auth: str | None):
    return client.get("/api/me", headers={"Authorization": auth} if auth else {})


def test_grader_gets_in(client):
    """TC-007: a professor/TA token with the grader permission is accepted."""
    r = me(client, f"Bearer {token()}")
    assert r.status_code == 200
    assert r.json() == {"sub": GRADER}


@pytest.mark.parametrize("auth", [
    None,
    "Basic dXNlcjpwYXNz",
    "Bearer not-a-jwt",
    f"Bearer {token(exp=1)}",
    f"Bearer {token(key=rsa.generate_private_key(public_exponent=65537, key_size=2048))}",
    f"Bearer {token(aud='https://another-api')}",
    f"Bearer {token(iss='https://evil.example/')}",
], ids=["missing", "not-bearer", "garbage", "expired", "bad-signature", "wrong-audience", "wrong-issuer"])
def test_invalid_or_expired_tokens_must_sign_in_again(client, auth):
    """TC-007: invalid and expired tokens get a sign-in prompt."""
    r = me(client, auth)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_REQUIRED"


def test_student_without_the_grader_permission_is_refused(client):
    """TC-007: a signed-in student (no Grader role) has no access."""
    r = me(client, f"Bearer {token(sub='auth0|student', permissions=())}")
    assert r.status_code == 403
    assert r.json()["error"] == r.json()["error"] | {
        "code": "NO_GRADER_ACCESS", "message": "Your account does not have grader access."}


def test_auth0_outage_is_retryable(client, monkeypatch):
    def down(token):
        raise jwt.PyJWKClientConnectionError("unreachable")

    monkeypatch.setattr(client.app.state.jwks, "get_signing_key_from_jwt", down)
    r = me(client, f"Bearer {token()}")
    assert r.status_code == 503
    assert r.json()["error"]["retryable"] is True


def test_every_api_route_needs_a_grader(client):
    paths = {p: ops for p, ops in client.app.openapi()["paths"].items() if p.startswith("/api")}
    assert len(paths) > 5
    for template, ops in paths.items():
        path = re.sub(r"\{\w+\}", str(uuid.uuid4()), template)
        for method in ops:
            assert client.request(method, path).status_code == 401, (method, template)
