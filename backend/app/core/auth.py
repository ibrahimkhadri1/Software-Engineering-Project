from typing import Annotated

import jwt
from fastapi import Depends, Request

from app.core.config import get_settings
from app.core.errors import AppError

PERMISSION = "use:autograder"


def current_user(request: Request) -> str:
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AppError("AUTH_REQUIRED", "Sign in to continue.", 401)
    settings = get_settings()
    try:
        key = request.app.state.jwks.get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"], audience=settings.auth0_audience,
                            issuer=f"https://{settings.auth0_domain}/", options={"require": ["exp", "sub"]})
    except jwt.PyJWKClientConnectionError as e:
        raise AppError("AUTH_UNAVAILABLE", "Sign-in cannot be checked right now. Try again shortly.", 503,
                       retryable=True) from e
    except jwt.PyJWTError as e:
        raise AppError("AUTH_REQUIRED", "Your session is invalid or has expired. Sign in again.", 401) from e
    if PERMISSION not in claims.get("permissions", []):
        raise AppError("NO_GRADER_ACCESS", "Your account does not have grader access.", 403)
    return claims["sub"]


User = Annotated[str, Depends(current_user)]
