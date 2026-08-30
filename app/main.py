"""Application entrypoint.

Every failure leaves through one door, so the error envelope is identical
whatever went wrong.
"""

import logging
import time
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.errors import ApiError, ErrorCode
from app.routes import router
from app.schemas import ErrorBody, ErrorResponse

log = logging.getLogger("linkedin-profile-api")

app = FastAPI(
    title="LinkedIn Profile API",
    version="0.1.0",
    description=(
        "Accepts a LinkedIn profile URL and returns the profile as structured JSON, "
        "sourced from LinkedIn's internal Voyager API.\n\n"
        "Request and response shapes deliberately mirror the conventions published "
        "at https://app.ontross.com/docs"
    ),
)


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    request.state.request_id = f"req_{uuid.uuid4().hex[:20]}"
    response = await call_next(request)
    response.headers["X-Request-Id"] = request.state.request_id
    return response


def _envelope(
    request: Request, *, code: str, message: str, retryable: bool, status: int,
    retry_after: int | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "req_unknown")
    body = ErrorResponse(
        error=ErrorBody(
            code=code, message=message, retryable=retryable, request_id=request_id
        )
    )
    headers = {"Retry-After": str(retry_after)} if retry_after else None
    return JSONResponse(
        status_code=status,
        content=body.model_dump(by_alias=True, mode="json"),
        headers=headers,
    )


@app.exception_handler(ApiError)
async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
    return _envelope(
        request,
        code=exc.code.value,
        message=exc.message,
        retryable=exc.retryable,
        status=exc.status,
        retry_after=exc.retry_after,
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    first = exc.errors()[0] if exc.errors() else {}
    where = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
    detail = first.get("msg", "Request body did not match the expected shape.")
    return _envelope(
        request,
        code=ErrorCode.INVALID_REQUEST.value,
        message=f"{where}: {detail}" if where else detail,
        retryable=False,
        status=422,
    )


@app.exception_handler(Exception)
async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "req_unknown")
    log.exception("unhandled error request_id=%s", request_id)
    return _envelope(
        request,
        code=ErrorCode.INTERNAL_ERROR.value,
        message="An unexpected error occurred. Quote the requestId when reporting it.",
        retryable=True,
        status=500,
    )


# The session probe is cached so that repeated health checks -- uptime monitors,
# keep-warm pings, a reviewer clicking refresh -- cannot themselves become the
# traffic that gets the backend session flagged.
_HEALTH_TTL_SECONDS = 60
_health_cache: dict[str, object] = {"checked_at": 0.0, "valid": None, "detail": None}


def _probe_session() -> tuple[bool | None, str | None]:
    """Ask LinkedIn who we are. Returns (sessionValid, detail)."""
    from app.credentials import resolve as resolve_session
    from app.voyager.client import VoyagerClient
    from app.voyager.endpoints import fetch_me

    try:
        payload = fetch_me(VoyagerClient(resolve_session("health")))
    except ApiError as exc:
        return False, exc.message
    except Exception:  # never let a health check raise
        log.exception("health probe failed unexpectedly")
        return None, "The session could not be checked."

    if not payload.get("included") and not payload.get("data"):
        return False, "LinkedIn returned an empty identity response."
    return True, None


@app.get("/health", tags=["ops"], summary="Liveness and backend session state")
async def health() -> dict:
    """Liveness, plus whether the backend LinkedIn session is still usable.

    Always returns 200 -- the service is up either way. ``sessionValid: false``
    means the credential needs renewing, which is an operator task rather than a
    caller error, and saying so plainly beats letting the next profile request
    fail with an error the caller cannot act on.
    """
    now = time.monotonic()
    if now - float(_health_cache["checked_at"]) > _HEALTH_TTL_SECONDS:
        # Belt and braces: _probe_session guards itself, but /health is what
        # uptime monitors and keep-warm pings call. It must never return 5xx,
        # or a transient upstream blip looks like the service being down.
        try:
            valid, detail = _probe_session()
        except Exception:
            log.exception("health probe raised")
            valid, detail = None, "The session could not be checked."
        _health_cache.update(checked_at=now, valid=valid, detail=detail)

    valid = _health_cache["valid"]
    body: dict[str, object] = {
        "status": "ok" if valid else "degraded",
        "sessionValid": valid,
        "checkedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if not valid and _health_cache["detail"]:
        body["detail"] = _health_cache["detail"]
        body["remedy"] = (
            "Renew LINKEDIN_LI_AT and LINKEDIN_JSESSIONID in the environment. "
            "See the README section 'If the session expires'."
        )
    return body


app.include_router(router)
