"""Session minting — dev-time only. The application never imports this.

There is no headless browser in this project, so minting a session is a manual
step you do once. This script tells you how, then verifies what you pasted.

    uv run python -m scripts.mint_session
"""

from __future__ import annotations

from app.credentials import resolve
from app.errors import ApiError
from app.voyager.client import VoyagerClient
from app.voyager.endpoints import fetch_top_card

INSTRUCTIONS = """
How to mint a session
---------------------
1. Sign in to LinkedIn in Chrome.
2. DevTools -> Application -> Cookies -> https://www.linkedin.com
3. Copy two values into your .env:

     li_at       ->  LINKEDIN_LI_AT
     JSESSIONID  ->  LINKEDIN_JSESSIONID     (looks like "ajax:1234567890123456789")

li_at is HttpOnly, which is why it cannot be read by script and must be copied
by hand. Treat it like a password: it grants full account access. Revoke it any
time with LinkedIn -> Settings -> Sign out of all sessions.
"""


def main() -> int:
    print(INSTRUCTIONS)
    try:
        session = resolve()
    except ApiError as exc:
        print(f"NOT CONFIGURED: {exc.message}")
        return 1

    print(f"csrf-token derived : {session.csrf_token[:12]}...")
    print("verifying against LinkedIn ...")

    try:
        payload = fetch_top_card(VoyagerClient(session), "thevishantshah")
    except ApiError as exc:
        print(f"FAILED [{exc.code.value}]: {exc.message}")
        return 1

    print(f"OK - session is live ({len(payload.get('included', []))} objects returned)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
