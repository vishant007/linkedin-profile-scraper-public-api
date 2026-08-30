"""Credential Vault.

The LinkedIn session lives here and nowhere else. No route accepts a credential
over the wire, so the credential-theft attack surface is absent from the API
rather than defended against.

Authorization is by API key alone. There is no per-caller resource to
authorize, because every caller shares one operator-held session -- which is
exactly what the brief specifies: "You may use your own LinkedIn credentials in
the backend."
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.config import get_settings
from app.errors import LinkedInSessionExpired

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class LinkedInSession:
    """One upstream session. Never logged, never serialised."""

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


def resolve() -> LinkedInSession:
    """The session this deployment holds.

    Supporting several sessions later means giving this function a caller
    identity and looking it up -- and adding that identity to the cache key,
    since LinkedIn discloses different amounts of a profile depending on the
    viewing account. Both are changes to this module and to app/cache.py; the
    request shape would also have to grow a field to carry the identity.
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


# The health probe asks whether this deployment's own credential still works.
resolve_operator_session = resolve
