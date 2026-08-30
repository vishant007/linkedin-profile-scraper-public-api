"""M5.2 - inbound rate limiting."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.cache import reset_cache
from app.config import get_settings
from app.errors import RateLimited
from app.ratelimit import RateLimiter, reset_limiter

PATH = "/api/integrations/linkedin/fetch-profile"
AUTH = "b3f1c2e4-8a90-4d21-9f77-2ce1d0a4b512"


def _body(url="https://www.linkedin.com/in/thevishantshah/"):
    return {"input": {"profileUrl": url}, "auth_id": AUTH}


# -- unit ------------------------------------------------------------------ #

def test_allows_up_to_the_limit_then_refuses():
    r = RateLimiter(per_minute=5)
    assert [r.check("k") for _ in range(5)] == [4, 3, 2, 1, 0]
    with pytest.raises(RateLimited) as exc:
        r.check("k")
    assert exc.value.retry_after >= 1
    assert exc.value.retryable is True


def test_buckets_are_per_key():
    r = RateLimiter(per_minute=1)
    r.check("alice")
    r.check("bob")  # bob is unaffected by alice
    with pytest.raises(RateLimited):
        r.check("alice")


def test_zero_disables_the_limiter():
    r = RateLimiter(per_minute=0)
    for _ in range(100):
        r.check("k")


def test_tracked_keys_are_bounded():
    """An attacker cycling keys must not grow the map without limit."""
    from app.ratelimit import MAX_TRACKED_KEYS

    r = RateLimiter(per_minute=60)
    for i in range(MAX_TRACKED_KEYS + 50):
        r.check(f"key-{i}")
    assert len(r._buckets) <= MAX_TRACKED_KEYS


# -- through the API -------------------------------------------------------- #

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_KEYS", "test-key")
    monkeypatch.setenv("AUTH_ID", AUTH)
    monkeypatch.setenv("LINKEDIN_LI_AT", "x")
    monkeypatch.setenv("LINKEDIN_JSESSIONID", '"ajax:1"')
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "3")
    monkeypatch.setenv("CACHE_TTL_SECONDS", "0")  # force every call through
    get_settings.cache_clear()
    reset_cache()
    reset_limiter()

    payload = json.loads(
        (Path(__file__).parent / "fixtures" / "thevishantshah.json").read_text()
    )
    import app.routes as routes

    monkeypatch.setattr(routes, "fetch_full_profile", lambda _c, _i: payload)

    from app.main import app

    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()
    reset_cache()
    reset_limiter()


def test_successful_responses_report_the_remaining_allowance(client):
    r = client.post(PATH, json=_body(), headers={"X-API-Key": "test-key"})
    assert r.status_code == 200
    assert r.headers["X-Limit-Remaining"] == "2"


def test_exceeding_the_limit_returns_429_with_both_headers(client):
    for _ in range(3):
        client.post(PATH, json=_body(), headers={"X-API-Key": "test-key"})

    r = client.post(PATH, json=_body(), headers={"X-API-Key": "test-key"})
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "RATE_LIMITED"
    assert r.json()["error"]["retryable"] is True
    assert int(r.headers["Retry-After"]) >= 1
    assert r.headers["X-Limit-Remaining"] == "0"


def test_rate_limited_response_uses_the_standard_error_envelope(client):
    for _ in range(4):
        r = client.post(PATH, json=_body(), headers={"X-API-Key": "test-key"})
    assert set(r.json()["error"]) == {"code", "message", "retryable", "requestId"}
