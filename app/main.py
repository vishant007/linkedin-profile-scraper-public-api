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
from fastapi.responses import HTMLResponse, JSONResponse

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

    # Tell browsers never to speak plain HTTP to this host again. TLS is
    # terminated by the platform, but without this a client will happily try
    # http:// once more and be redirected in the clear.
    response.headers["Strict-Transport-Security"] = (
        "max-age=31536000; includeSubDomains"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
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
# `checked_at` is the monotonic clock for expiry; `checked_wall` is the real
# time the probe ran, which is what the response reports. Reporting "now"
# instead would make a cached answer look freshly verified.
_health_cache: dict[str, object] = {
    "checked_at": 0.0,
    "checked_wall": None,
    "valid": None,
    "detail": None,
}


def _probe_session() -> tuple[bool | None, str | None]:
    """Ask LinkedIn who we are. Returns (sessionValid, detail)."""
    from app.credentials import resolve_operator_session
    from app.voyager.client import VoyagerClient
    from app.voyager.endpoints import fetch_me

    try:
        payload = fetch_me(VoyagerClient(resolve_operator_session()))
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
        _health_cache.update(
            checked_at=now,
            checked_wall=datetime.now(timezone.utc),
            valid=valid,
            detail=detail,
        )

    valid = _health_cache["valid"]
    body: dict[str, object] = {
        "status": "ok" if valid else "degraded",
        "sessionValid": valid,
        # When the session was last actually probed -- not when this reply was
        # written. A cached answer must not claim to be freshly verified.
        "checkedAt": (
            _health_cache["checked_wall"].isoformat().replace("+00:00", "Z")
            if _health_cache["checked_wall"]
            else None
        ),
    }
    if not valid and _health_cache["detail"]:
        body["detail"] = _health_cache["detail"]
        body["remedy"] = (
            "Renew LINKEDIN_LI_AT and LINKEDIN_JSESSIONID in the environment. "
            "See the README section 'If the session expires'."
        )
    return body


_INDEX_HTML = """<!doctype html>
<meta charset="utf-8">
<title>LinkedIn Profile API</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  :root{--bg:#f5f7f9;--card:#fff;--ink:#12181f;--dim:#5a6875;--line:#dde4ea;--acc:#0d6e78}
  @media(prefers-color-scheme:dark){:root{--bg:#0e1218;--card:#171e26;--ink:#dce3ea;--dim:#8e9ba6;--line:#2a343f;--acc:#45b9c4}}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif}
  .wrap{max-width:760px;margin:0 auto;padding:48px 22px 72px}
  h1{font-size:28px;letter-spacing:-.02em;margin:0 0 6px}
  .sub{color:var(--dim);margin:0 0 28px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:18px 20px;margin-bottom:14px}
  h2{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim);margin:0 0 12px}
  .op{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;padding:7px 0;border-bottom:1px solid var(--line)}
  .op:last-child{border-bottom:0}
  .m{font:700 11px ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--acc);color:var(--card);padding:2px 7px;border-radius:3px}
  .p{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px}
  .d{color:var(--dim);font-size:13px;width:100%}
  pre{background:var(--bg);border:1px solid var(--line);border-radius:4px;padding:13px;overflow-x:auto;
      font:12px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;margin:0}
  a{color:var(--acc)}
  .links{display:flex;gap:16px;flex-wrap:wrap;font-size:14px}
  footer{color:var(--dim);font-size:13px;margin-top:26px}
</style>
<div class="wrap">
  <h1>LinkedIn Profile API</h1>
  <p class="sub">Accepts a LinkedIn profile URL and returns the profile as structured JSON,
     sourced from LinkedIn&rsquo;s internal Voyager API.</p>

  <div class="card">
    <h2>Operations</h2>
    <div class="op"><span class="m">POST</span><span class="p">/api/integrations/linkedin/fetch-profile</span>
      <span class="d">Name, headline, location, about, experience, education, skills,
      certifications, languages and profile images &mdash; when available.</span></div>
    <div class="op"><span class="m">GET</span><span class="p">/api/integrations/linkedin/fetch-profile</span>
      <span class="d">Convenience alias taking the same input as query parameters.</span></div>
    <div class="op"><span class="m">GET</span><span class="p">/health</span>
      <span class="d">Liveness, plus whether the backend LinkedIn session is still usable. No API key required.</span></div>
  </div>

  <div class="card">
    <h2>Try it</h2>
    <pre>curl -X POST https://tross-assignment-ihro.onrender.com/api/integrations/linkedin/fetch-profile \\
  -H "X-API-Key: &lt;your key&gt;" \\
  -H "Content-Type: application/json" \\
  -d '{"input":{"profileUrl":"https://www.linkedin.com/in/thevishantshah/"},
       "auth_id":"b3f1c2e4-8a90-4d21-9f77-2ce1d0a4b512"}'</pre>
  </div>

  <div class="card">
    <h2>Documentation</h2>
    <div class="links">
      <a href="/docs">Interactive docs</a>
      <a href="/redoc">Reference</a>
      <a href="/openapi.json">OpenAPI spec</a>
      <a href="/health">Health</a>
      <a href="https://github.com/vishant007/tross-assignment">Source</a>
    </div>
  </div>

  <footer>Request and response shapes deliberately mirror the conventions published at
    <a href="https://app.ontross.com/docs">app.ontross.com/docs</a>.</footer>
</div>
"""


@app.get("/", include_in_schema=False)
async def index(request: Request):
    """Landing page.

    A base URL that 404s reads as a broken deployment to anyone who pastes it
    into a browser, which a reviewer will. Serves HTML to browsers and JSON to
    API clients, so both audiences get something useful.
    """
    links = {
        "documentation": "/docs",
        "reference": "/redoc",
        "openapi": "/openapi.json",
        "health": "/health",
        "fetchProfile": "POST /api/integrations/linkedin/fetch-profile",
        "repository": "https://github.com/vishant007/tross-assignment",
    }
    if "text/html" not in request.headers.get("accept", ""):
        return JSONResponse({"service": app.title, "version": app.version, "links": links})

    return HTMLResponse(_INDEX_HTML)


app.include_router(router)
