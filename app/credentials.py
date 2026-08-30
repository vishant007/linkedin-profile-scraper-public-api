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

import hashlib
import logging
from dataclasses import dataclass

from app.config import get_settings

log = logging.getLogger(__name__)


def _fingerprint(value: str) -> str:
    """Identify a secret in logs without recording it."""
    return hashlib.sha256(value.encode()).hexdigest()[:12] if value else "<empty>"
from app.errors import ForbiddenAuthId, LinkedInSessionExpired


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


@dataclass(frozen=True)
class Binding:
    """One handle, the keys entitled to use it, and the session behind it."""

    auth_id: str
    owner_keys: frozenset[str]
    session: LinkedInSession


def _bindings() -> dict[str, Binding]:
    """Build the handle registry from configuration.

    Single-tenant: one handle, owned by every configured API key, because all
    keys belong to the same operator. The registry is a mapping rather than a
    single value so the ownership check below is a real code path and not a
    comment -- adding a second binding is the whole of multi-tenancy here.
    """
    settings = get_settings()
    session = LinkedInSession(
        li_at=settings.linkedin_li_at.strip(),
        jsessionid=settings.linkedin_jsessionid.strip(),
    )
    return {
        settings.auth_id: Binding(
            auth_id=settings.auth_id,
            owner_keys=settings.accepted_api_keys,
            session=session,
        )
    }


def resolve_operator_session() -> LinkedInSession:
    """The session the service itself holds, with no ownership check.

    For internal use only -- the health probe asking "is my own credential
    still good?". There is no caller here, so there is no ownership to verify;
    demanding one would mean inventing a fake key to satisfy it.
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


def resolve(auth_id: str, api_key: str) -> LinkedInSession:
    """Resolve an opaque handle to a session, checking the caller owns it.

    Without this check the API has a Broken Object Level Authorization flaw:
    authentication proves *who is calling*, but nothing would prove the handle
    they passed is theirs to use. Single tenancy makes the check vacuous today,
    which is exactly why it is worth writing down rather than assuming.
    """
    settings = get_settings()

    if not settings.linkedin_li_at or not settings.linkedin_jsessionid:
        raise LinkedInSessionExpired(
            "No LinkedIn session is configured. Set LINKEDIN_LI_AT and "
            "LINKEDIN_JSESSIONID in the environment."
        )

    binding = _bindings().get(auth_id)

    # One error for "no such handle" and "not yours", so the response cannot be
    # used to enumerate which handles exist.
    if binding is None or api_key not in binding.owner_keys:
        log.warning(
            "auth_id rejected: handle=%s key=%s",
            _fingerprint(auth_id),
            _fingerprint(api_key),
        )
        raise ForbiddenAuthId(
            "The supplied auth_id is not available to this API key."
        )

    return binding.session
