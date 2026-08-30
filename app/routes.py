"""fetch-profile handler.

Path grammar, method and envelope all mirror Tross:
``POST /api/integrations/{vendor}/{verb-noun}``, no version segment.
A GET alias is offered because it is what people reach for first.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request

from app.credentials import resolve as resolve_session
from app.schemas import (
    DEFAULT_SECTIONS,
    FetchProfileInput,
    FetchProfileRequest,
    FetchProfileResponse,
    Section,
)
from app.security import require_api_key
from app.voyager.client import VoyagerClient
from app.voyager.endpoints import fetch_full_profile, public_identifier_from_url
from app.voyager.resolver import normalize

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integrations/linkedin", tags=["linkedin"])


def _fetch(payload: FetchProfileRequest, request_id: str) -> FetchProfileResponse:
    """Credential vault -> Voyager client -> graph resolver.

    Each step is one box on the flow diagram, in order.
    """
    public_id = public_identifier_from_url(payload.input.profile_url)

    session = resolve_session(payload.auth_id)
    client = VoyagerClient(session)

    log.info(
        "fetch-profile id=%s sections=%s request_id=%s",
        public_id,
        ",".join(s.value for s in payload.input.sections),
        request_id,
    )

    raw = fetch_full_profile(client, public_id)
    profile, warnings = normalize(raw, public_id, payload.input.sections)

    return FetchProfileResponse(
        profile=profile,
        warnings=warnings,
        fetched_at=datetime.now(timezone.utc),
    )


@router.post(
    "/fetch-profile",
    response_model=FetchProfileResponse,
    response_model_exclude_none=True,
    summary="Fetch a LinkedIn profile as structured JSON",
    description=(
        "Returns name, headline, location, about, experience, education, skills, "
        "certifications, languages and profile images when available. Sections that "
        "the backend session cannot see are reported in `warnings` rather than "
        "failing the request."
    ),
)
async def fetch_profile(
    payload: FetchProfileRequest,
    request: Request,
    _key: str = Depends(require_api_key),
) -> FetchProfileResponse:
    return _fetch(payload, getattr(request.state, "request_id", "req_unknown"))


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
    request: Request,
    profile_url: str = Query(alias="profileUrl"),
    auth_id: str = Query(alias="auth_id"),
    sections: list[Section] | None = Query(default=None),
    _key: str = Depends(require_api_key),
) -> FetchProfileResponse:
    payload = FetchProfileRequest(
        input=FetchProfileInput(
            profile_url=profile_url,
            sections=sections or list(DEFAULT_SECTIONS),
        ),
        auth_id=auth_id,
    )
    return _fetch(payload, getattr(request.state, "request_id", "req_unknown"))
