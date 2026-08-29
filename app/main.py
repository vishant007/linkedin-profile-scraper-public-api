"""Application entrypoint.

Every failure leaves through one door, so the error envelope is identical
whatever went wrong.
"""

import logging
import uuid

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
        code="INVALID_REQUEST",
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


@app.get("/health", tags=["ops"], summary="Liveness and backend session state")
async def health() -> dict:
    # Phase 5 (M5.3) replaces sessionValid with a real upstream probe.
    return {"status": "ok", "sessionValid": None}


app.include_router(router)
