"""CSRF protection middleware for Sentinel web UI (TD-013).

Uses HMAC-signed tokens tied to a per-process secret. Tokens are
set as cookies and must be echoed back in POST form data or headers.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from collections.abc import MutableMapping
from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

_CSRF_COOKIE = "sentinel_csrf"
_CSRF_FIELD = "csrf_token"
_CSRF_HEADER = "x-csrf-token"
# Methods that mutate state and require CSRF validation
_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _sign_token(secret: str, raw: str) -> str:
    """Create an HMAC signature for a token."""
    return hmac.new(
        secret.encode(), raw.encode(), hashlib.sha256
    ).hexdigest()


def _make_token(secret: str) -> str:
    """Generate a new CSRF token (random value + signature)."""
    raw = secrets.token_hex(16)
    sig = _sign_token(secret, raw)
    return f"{raw}.{sig}"


def _verify_token(secret: str, token: str) -> bool:
    """Verify a CSRF token's signature."""
    if not token or "." not in token:
        return False
    raw, sig = token.rsplit(".", 1)
    expected = _sign_token(secret, raw)
    return hmac.compare_digest(sig, expected)


class CSRFMiddleware:
    """ASGI middleware that enforces CSRF tokens on state-mutating requests.

    - Sets a signed CSRF cookie on every response if not already present.
    - Validates that POST/PUT/PATCH/DELETE requests include the cookie
      token in either form data (csrf_token field) or X-CSRF-Token header.
    - HTMX requests include the token via header (configured in base template).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._secret = secrets.token_hex(32)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive, send)
        method = request.method
        cookie_token = request.cookies.get(_CSRF_COOKIE, "")

        if method in _UNSAFE_METHODS:
            # Validate: cookie must exist and be validly signed
            if not _verify_token(self._secret, cookie_token):
                response = Response("CSRF validation failed", status_code=403)
                await response(scope, receive, send)
                return

            # Get submitted token from header first (htmx), then form data
            submitted = request.headers.get(_CSRF_HEADER, "")
            if not submitted:
                content_type = request.headers.get("content-type", "")
                if "application/x-www-form-urlencoded" in content_type:
                    body = await request.body()
                    from urllib.parse import parse_qs
                    form_data = parse_qs(body.decode("utf-8", errors="replace"))
                    submitted_list = form_data.get(_CSRF_FIELD, [])
                    submitted = submitted_list[0] if submitted_list else ""

                    # Rebuild receive so downstream can read the body again
                    async def new_receive() -> dict[str, Any]:
                        return {"type": "http.request", "body": body, "more_body": False}
                    receive = new_receive

            if not submitted or not hmac.compare_digest(submitted, cookie_token):
                response = Response("CSRF token mismatch", status_code=403)
                await response(scope, receive, send)
                return

            await self.app(scope, receive, send)
        else:
            # Safe methods — ensure cookie exists, inject token into state
            need_cookie = not cookie_token or not _verify_token(self._secret, cookie_token)
            if need_cookie:
                cookie_token = _make_token(self._secret)

            # Store token in scope state so templates can access via request
            scope.setdefault("state", {})
            scope["state"]["csrf_token"] = cookie_token

            if need_cookie:
                original_send = send

                async def send_with_cookie(message: MutableMapping[str, Any]) -> None:
                    if message["type"] == "http.response.start":
                        headers = list(message.get("headers", []))
                        cookie_val = (
                            f"{_CSRF_COOKIE}={cookie_token}; Path=/; SameSite=Strict"
                        )
                        headers.append((b"set-cookie", cookie_val.encode()))
                        message = {**message, "headers": headers}
                    await original_send(message)

                await self.app(scope, receive, send_with_cookie)
            else:
                # Cookie already valid — just make sure state has it
                await self.app(scope, receive, send)
