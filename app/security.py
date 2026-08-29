"""API Gateway — caller authentication.

Plain long-lived API keys, matching Tross's ``X-API-Key`` and Goedecke's
recommendation that an API stay reachable by people who are not full-time
engineers.
"""

from fastapi import Header

from app.config import get_settings
from app.errors import InvalidApiKey


async def require_api_key(x_api_key: str | None = Header(default=None)) -> str:
    accepted = get_settings().accepted_api_keys

    if not accepted:
        # No keys configured: refuse rather than silently running open.
        raise InvalidApiKey(
            "This deployment has no API keys configured. Set API_KEYS in the environment."
        )
    if not x_api_key:
        raise InvalidApiKey("Missing X-API-Key header.")
    if x_api_key not in accepted:
        raise InvalidApiKey("The supplied X-API-Key is not recognised.")
    return x_api_key
