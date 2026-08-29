"""Credential Vault.

Tross documents `auth_id` only as "Auth id", and no route in their public API
accepts a credential — provisioning is out-of-band by design. We take the same
posture: `auth_id` is an opaque handle resolved server-side, and nothing in this
service accepts a LinkedIn credential over the wire.

Today every handle resolves to one operator-held session read from the
environment. That is exactly what the brief asks for ("You may use your own
LinkedIn credentials in the backend"). Supporting many sessions later is a
change to this module only -- the wire contract does not move.
"""

from dataclasses import dataclass

from app.config import get_settings
from app.errors import LinkedInSessionExpired


@dataclass(frozen=True)
class LinkedInSession:
    """One resolved upstream session. Never logged, never serialised."""

    li_at: str
    jsessionid: str

    @property
    def csrf_token(self) -> str:
        """LinkedIn wants the JSESSIONID value echoed back, minus its quotes."""
        return self.jsessionid.strip('"')

    @property
    def cookie_header(self) -> str:
        return f'li_at={self.li_at}; JSESSIONID="{self.csrf_token}"'

    def __repr__(self) -> str:  # pragma: no cover - defensive
        return "LinkedInSession(li_at=<redacted>, jsessionid=<redacted>)"


def resolve(auth_id: str) -> LinkedInSession:
    """Resolve an opaque handle to a session.

    Single-tenant: the handle is accepted and recorded, but every handle maps to
    the one configured session. Multi-tenant would look the handle up in a store
    here -- and would also need `auth_id` in the cache key, since LinkedIn
    discloses different amounts of a profile depending on the viewing account.
    """
    settings = get_settings()

    if not settings.linkedin_li_at or not settings.linkedin_jsessionid:
        raise LinkedInSessionExpired(
            "No LinkedIn session is configured. Set LINKEDIN_LI_AT and "
            "LINKEDIN_JSESSIONID in the environment."
        )

    return LinkedInSession(
        li_at=settings.linkedin_li_at.strip(),
        jsessionid=settings.linkedin_jsessionid.strip(),
    )
