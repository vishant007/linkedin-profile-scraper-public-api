"""API Gateway — caller authentication.

Plain long-lived API keys, matching Tross's ``X-API-Key`` and Goedecke's
recommendation that an API stay reachable by people who are not full-time
engineers.
"""

import hashlib
import logging

from fastapi import Header

from app.config import get_settings
from app.errors import InvalidApiKey

log = logging.getLogger(__name__)


def _fingerprint(value: str | None) -> str:
    """Identify a key in logs without recording it.

    Failed attempts must be logged -- credential stuffing is only visible in the
    pattern of rejections -- but the presented secret itself must not be.
    """
    return hashlib.sha256(value.encode()).hexdigest()[:12] if value else "<absent>"


async def require_api_key(x_api_key: str | None = Header(default=None)) -> str:
    accepted = get_settings().accepted_api_keys

    if not accepted:
        # No keys configured: refuse rather than silently running open.
        log.error("auth refused: no API keys configured in this deployment")
        raise InvalidApiKey(
            "This deployment has no API keys configured. Set API_KEYS in the environment."
        )
    if not x_api_key:
        log.warning("auth failed: no X-API-Key header presented")
        raise InvalidApiKey("Missing X-API-Key header.")
    if x_api_key not in accepted:
        log.warning("auth failed: unrecognised key fp=%s", _fingerprint(x_api_key))
        raise InvalidApiKey("The supplied X-API-Key is not recognised.")

    log.info("auth ok: key fp=%s", _fingerprint(x_api_key))
    return x_api_key
