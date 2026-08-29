"""Voyager REST endpoints, and turning a LinkedIn URL into an identifier.

Phase 0 established that one decoration returns the whole profile, so there is
no per-section fan-out: `FullProfileWithEntities` carries name, headline,
location, about, experience, education, skills, certifications, languages and
profile images in a single ~85 kB response. See docs/section-map.md.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import unquote, urlparse

from app.errors import ApiError, InvalidProfileUrl, ProfileNotFound
from app.voyager.client import VoyagerClient

log = logging.getLogger(__name__)

PROFILES_PATH = "/voyager/api/identity/dash/profiles"

_DECO = "com.linkedin.voyager.dash.deco.identity.profile"
FULL_PROFILE_DECORATION = f"{_DECO}.FullProfileWithEntities"
TOP_CARD_DECORATION = f"{_DECO}.WebTopCardCore-6"

# The version suffix increments over time. -63 was verified working on
# 2026-08-27; neighbours are probed so a bump does not take the service down.
DECORATION_VERSIONS: tuple[int, ...] = (63, 64, 65, 62, 66, 61, 67, 60)

_ALLOWED_HOSTS = {"linkedin.com", "www.linkedin.com"}
# Deliberately permissive: LinkedIn slugs are ASCII in practice, but wrongly
# rejecting a valid profile is worse than passing junk through to a 404.
_SLUG_RE = re.compile(r"^[\w\-.%]{2,120}$", re.UNICODE)

# Remembered once resolved, so we probe at most once per process.
_resolved_version: int | None = None


def public_identifier_from_url(value: str) -> str:
    """Extract the public identifier from any LinkedIn profile URL form.

    Accepts a bare slug too, since that is what people paste half the time.
    """
    raw = (value or "").strip()
    if not raw:
        raise InvalidProfileUrl("profileUrl is required.")

    # A bare slug, no scheme and no slashes.
    if "/" not in raw and "." not in raw:
        slug = raw
    else:
        candidate = raw if "//" in raw else f"https://{raw}"
        parsed = urlparse(candidate)
        host = (parsed.netloc or "").split("@")[-1].split(":")[0].lower()

        # Regional subdomains are legitimate: in.linkedin.com, uk.linkedin.com...
        if host not in _ALLOWED_HOSTS and not host.endswith(".linkedin.com"):
            raise InvalidProfileUrl(
                f"Not a LinkedIn URL: {raw!r}. Expected a linkedin.com/in/... address."
            )

        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) < 2 or parts[0] != "in":
            raise InvalidProfileUrl(
                f"Not a LinkedIn profile URL: {raw!r}. Expected /in/<identifier>."
            )
        slug = parts[1]

    slug = unquote(slug).strip()
    if not _SLUG_RE.match(slug):
        raise InvalidProfileUrl(f"Could not read a profile identifier from {raw!r}.")
    return slug


def _params(public_id: str, decoration: str) -> dict[str, str]:
    return {
        "q": "memberIdentity",
        "memberIdentity": public_id,
        "decorationId": decoration,
    }


def fetch_full_profile(client: VoyagerClient, public_id: str) -> dict[str, Any]:
    """Fetch the entire profile in one call, probing decoration versions."""
    global _resolved_version

    versions = (
        (_resolved_version,) + tuple(v for v in DECORATION_VERSIONS if v != _resolved_version)
        if _resolved_version is not None
        else DECORATION_VERSIONS
    )

    last: ApiError | None = None
    for version in versions:
        decoration = f"{FULL_PROFILE_DECORATION}-{version}"
        try:
            payload = client.get(PROFILES_PATH, _params(public_id, decoration))
        except ProfileNotFound:
            # Unambiguous: the member does not exist. Do not keep probing.
            raise
        except ApiError as exc:
            last = exc
            log.info("decoration %s rejected (%s), trying next", version, exc.code.value)
            continue

        if _resolved_version != version:
            log.info("resolved FullProfileWithEntities version to -%s", version)
            _resolved_version = version
        return payload

    raise last if last else ProfileNotFound("Profile could not be retrieved.")


def fetch_top_card(client: VoyagerClient, public_id: str) -> dict[str, Any]:
    """A small, cheap call. Used by /health to check the session is still alive."""
    return client.get(PROFILES_PATH, _params(public_id, TOP_CARD_DECORATION))
