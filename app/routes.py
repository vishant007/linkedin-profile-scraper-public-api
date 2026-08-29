"""fetch-profile handler.

Path grammar, method and envelope all mirror Tross:
``POST /api/integrations/{vendor}/{verb-noun}``, no version segment.
A GET alias is offered because it is what people reach for first.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from app.schemas import (
    DEFAULT_SECTIONS,
    FetchProfileInput,
    FetchProfileRequest,
    FetchProfileResponse,
    Profile,
    Section,
)
from app.security import require_api_key

router = APIRouter(prefix="/api/integrations/linkedin", tags=["linkedin"])


async def _fetch(payload: FetchProfileRequest) -> FetchProfileResponse:
    # Phase 1 stub. Phase 2-4 replace this with credentials -> client -> resolver.
    return FetchProfileResponse(
        profile=Profile(
            public_identifier="stub",
            first_name="Stub",
            last_name="Response",
            headline="Phase 1 scaffold - not yet wired to LinkedIn",
        ),
        warnings=[],
        fetched_at=datetime.now(timezone.utc),
    )


@router.post(
    "/fetch-profile",
    response_model=FetchProfileResponse,
    response_model_exclude_none=True,
    summary="Fetch a LinkedIn profile as structured JSON",
)
async def fetch_profile(
    payload: FetchProfileRequest,
    _key: str = Depends(require_api_key),
) -> FetchProfileResponse:
    return await _fetch(payload)


@router.get(
    "/fetch-profile",
    response_model=FetchProfileResponse,
    response_model_exclude_none=True,
    summary="Convenience GET alias",
    description=(
        "POST is the primary method: it matches Tross's convention and keeps "
        "profile URLs out of access logs, browser history and Referer headers. "
        "This alias exists because GET is what callers reach for first."
    ),
)
async def fetch_profile_get(
    profile_url: str = Query(alias="profileUrl"),
    auth_id: str = Query(alias="auth_id"),
    sections: list[Section] | None = Query(default=None),
    _key: str = Depends(require_api_key),
) -> FetchProfileResponse:
    return await _fetch(
        FetchProfileRequest(
            input=FetchProfileInput(
                profile_url=profile_url,
                sections=sections or list(DEFAULT_SECTIONS),
            ),
            auth_id=auth_id,
        )
    )
