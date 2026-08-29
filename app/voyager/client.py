"""HTTP client for LinkedIn's internal Voyager API.

No browser. Voyager returns JSON, so there is nothing to render; the only thing
a headless browser would contribute is request realism, and `curl_cffi` supplies
that far more cheaply by replaying Chrome's actual TLS/JA3 and HTTP/2 handshake.

Detection begins at the TLS handshake, before a single header is parsed -- which
is why setting a browser User-Agent on a default HTTP client is not enough.
"""

from __future__ import annotations

import logging
from typing import Any

from curl_cffi import requests as curl_requests

from app.credentials import LinkedInSession
from app.errors import (
    LinkedInSessionExpired,
    ProfileNotFound,
    UpstreamUnavailable,
)

log = logging.getLogger(__name__)

BASE_URL = "https://www.linkedin.com"
IMPERSONATE = "chrome"
TIMEOUT_SECONDS = 20

# The four headers that make a Voyager call work. Each buys exactly one thing;
# see docs/approach.html for the observed failure mode when any is removed.
BASE_HEADERS = {
    "accept": "application/vnd.linkedin.normalized+json+2.1",
    "x-restli-protocol-version": "2.0.0",
    "accept-language": "en-US,en;q=0.9",
    "x-li-lang": "en_US",
}


class VoyagerClient:
    def __init__(self, session: LinkedInSession) -> None:
        self._session = session

    def _headers(self) -> dict[str, str]:
        return {
            **BASE_HEADERS,
            "csrf-token": self._session.csrf_token,
            "cookie": self._session.cookie_header,
        }

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET a Voyager path and return parsed JSON, or raise an ApiError."""
        url = f"{BASE_URL}{path}"
        try:
            response = curl_requests.get(
                url,
                params=params,
                headers=self._headers(),
                impersonate=IMPERSONATE,
                timeout=TIMEOUT_SECONDS,
                allow_redirects=False,  # a redirect IS the signal, not a detour
            )
        except Exception as exc:  # network-level failure
            log.warning("voyager transport error path=%s err=%s", path, type(exc).__name__)
            raise UpstreamUnavailable(
                "Could not reach LinkedIn. This is usually transient."
            ) from exc

        return self._interpret(response, path)

    @staticmethod
    def _interpret(response, path: str) -> dict[str, Any]:
        status = response.status_code

        # A redirect to the login page means the backing session is dead.
        if status in (301, 302, 303, 307, 308):
            location = response.headers.get("location", "")
            if "login" in location or "authwall" in location or "checkpoint" in location:
                raise LinkedInSessionExpired(
                    "The backend LinkedIn session is no longer valid and must be renewed."
                )
            raise UpstreamUnavailable(f"Unexpected redirect from LinkedIn to {location!r}.")

        if status in (401, 403):
            raise LinkedInSessionExpired(
                "LinkedIn rejected the backend session (missing or stale credentials)."
            )
        if status == 404:
            raise ProfileNotFound("LinkedIn has no profile at that identifier.")
        if status == 429:
            raise UpstreamUnavailable(
                "LinkedIn is rate limiting the backend session. Try again shortly."
            )
        if status >= 500:
            raise UpstreamUnavailable(f"LinkedIn returned {status}.")
        if status != 200:
            raise UpstreamUnavailable(f"Unexpected status {status} from LinkedIn.")

        try:
            return response.json()
        except Exception as exc:
            log.warning("voyager non-json response path=%s", path)
            raise UpstreamUnavailable(
                "LinkedIn returned a response that was not JSON."
            ) from exc
