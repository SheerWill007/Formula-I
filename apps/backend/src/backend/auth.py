"""
    Clerk Session Token Verification

Verifies RS256 signatures against Clerk's published JWKS. Product APIs
(agent, sessions, telemetry, predictions) use ``require_api_auth`` so a
valid bearer token is required and absent/invalid tokens get a consistent
JSON 401. CORS preflight (OPTIONS) is always permitted.
"""

from __future__ import annotations
from functools import lru_cache
import jwt
from flask import g, jsonify, request
from backend.config import settings


class ClerkAuthError(Exception):
    """It is raised when a bearer token is absent"""


@lru_cache(maxsize=1)
def _jwks_client() -> jwt.PyJWKClient:
    """Build one JWKS client per process; PyJWT caches the keys internally"""
    if not settings.clerk_issuer:
        raise ClerkAuthError("Clerk issuer is not configured")
    url = f"{settings.clerk_issuer.rstrip('/')}/.well-known/jwks.json"
    return jwt.PyJWKClient(url, cache_keys=True)


def verify_session_token(token: str) -> str:
    """Return the clerk_user_id ('sub') for a valid session token."""
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
    except jwt.PyJWKClientError as exc:
        raise ClerkAuthError(f"cannot resolve signing key: {exc}") from exc
    try:
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=settings.clerk_issuer.rstrip("/"),
            options={"verify_aud": False},
        )
    except jwt.InvalidTokenError as exc:
        raise ClerkAuthError(f"invalid token: {exc}") from exc
    sub = payload.get("sub")
    if not sub:
        raise ClerkAuthError("token has no 'sub' claim")
    return str(sub)


def require_api_auth() -> tuple[dict, int] | None:
    """Blueprint ``before_request`` guard for Clerk-protected product APIs.

    - OPTIONS (CORS preflight) never carries credentials, so it passes.
    - A missing/malformed Authorization header returns a JSON 401.
    - An invalid token returns a JSON 401 with the verification reason.
    - On success stores ``clerk_user_id`` on ``flask.g`` and returns None.
    """
    if request.method == "OPTIONS":
        return None
    if getattr(g, "clerk_user_id", None):
        return None  # already verified by the app-wide hook
    header =request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return jsonify({"error": "Missing bearer token"}), 401
    try:
        g.clerk_user_id = verify_session_token(header.removeprefix("Bearer "))
    except ClerkAuthError as exc:
        return jsonify({"error": f"Invalid token: {exc}"}), 401
    return None
