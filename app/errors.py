"""The error envelope.

Tross documents no error format, so this one is ours. A stable machine-readable
`code`, a human `message`, an explicit `retryable` flag that pairs with the
rate-limit headers, and a `requestId` for support.
"""

from enum import StrEnum


class ErrorCode(StrEnum):
    INVALID_API_KEY = "INVALID_API_KEY"
    INVALID_PROFILE_URL = "INVALID_PROFILE_URL"
    PROFILE_NOT_FOUND = "PROFILE_NOT_FOUND"
    LINKEDIN_SESSION_EXPIRED = "LINKEDIN_SESSION_EXPIRED"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ApiError(Exception):
    """Base for everything that should reach the client as the error envelope."""

    status: int = 500
    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    retryable: bool = False

    def __init__(self, message: str, *, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.retry_after = retry_after


class InvalidApiKey(ApiError):
    status = 401
    code = ErrorCode.INVALID_API_KEY
    retryable = False


class InvalidProfileUrl(ApiError):
    status = 400
    code = ErrorCode.INVALID_PROFILE_URL
    retryable = False


class ProfileNotFound(ApiError):
    status = 404
    code = ErrorCode.PROFILE_NOT_FOUND
    retryable = False


class LinkedInSessionExpired(ApiError):
    """The backend session died. Retrying will not fix it — a human must re-mint."""

    status = 502
    code = ErrorCode.LINKEDIN_SESSION_EXPIRED
    retryable = False


class UpstreamUnavailable(ApiError):
    status = 502
    code = ErrorCode.UPSTREAM_UNAVAILABLE
    retryable = True


class RateLimited(ApiError):
    status = 429
    code = ErrorCode.RATE_LIMITED
    retryable = True
