"""Security controls, audited against Postman's API security guidance.

Each test names the practice it enforces so a regression is traceable to the
control it breaks, not just to a failing assertion.
"""

import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.cache import reset_cache
from app.config import get_settings

PATH = "/api/integrations/linkedin/fetch-profile"
GOOD_AUTH = "b3f1c2e4-8a90-4d21-9f77-2ce1d0a4b512"


def _body(auth_id=GOOD_AUTH):
    return {
        "input": {"profileUrl": "https://www.linkedin.com/in/thevishantshah/"},
        "auth_id": auth_id,
    }


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_KEYS", "alice-key,bob-key")
    monkeypatch.setenv("AUTH_ID", GOOD_AUTH)
    monkeypatch.setenv("LINKEDIN_LI_AT", "test-li-at")
    monkeypatch.setenv("LINKEDIN_JSESSIONID", '"ajax:0000000000"')
    get_settings.cache_clear()
    reset_cache()

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


# -- #3 authorization: BOLA ----------------------------------------------- #

def test_unknown_auth_id_is_forbidden(client):
    """Authentication proves who is calling; it must not imply the handle is theirs."""
    r = client.post(PATH, json=_body("not-my-handle"), headers={"X-API-Key": "alice-key"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN_AUTH_ID"


def test_forbidden_response_does_not_reveal_whether_the_handle_exists(client):
    """Same error either way, so responses cannot be used to enumerate handles."""
    unknown = client.post(PATH, json=_body("does-not-exist"), headers={"X-API-Key": "alice-key"})
    malformed = client.post(PATH, json=_body("00000000-0000-0000-0000-000000000000"),
                            headers={"X-API-Key": "alice-key"})
    assert unknown.json()["error"]["message"] == malformed.json()["error"]["message"]


def test_a_valid_key_with_its_own_handle_succeeds(client):
    r = client.post(PATH, json=_body(), headers={"X-API-Key": "bob-key"})
    assert r.status_code == 200


# -- #8 logging ------------------------------------------------------------ #

def test_failed_authentication_is_logged(client, caplog):
    """Credential stuffing is only visible in the pattern of rejections."""
    with caplog.at_level(logging.WARNING, logger="app.security"):
        client.post(PATH, json=_body(), headers={"X-API-Key": "wrong"})
    assert any("auth failed" in r.message for r in caplog.records)


def test_missing_key_is_logged(client, caplog):
    with caplog.at_level(logging.WARNING, logger="app.security"):
        client.post(PATH, json=_body())
    assert any("no X-API-Key header" in r.message for r in caplog.records)


def test_logs_never_contain_the_presented_secret(client, caplog):
    """Log the fingerprint, never the key."""
    with caplog.at_level(logging.DEBUG):
        client.post(PATH, json=_body(), headers={"X-API-Key": "super-secret-key"})
    assert not any("super-secret-key" in r.getMessage() for r in caplog.records)


def test_rejected_auth_id_is_logged(client, caplog):
    with caplog.at_level(logging.WARNING, logger="app.credentials"):
        client.post(PATH, json=_body("nope"), headers={"X-API-Key": "alice-key"})
    assert any("auth_id rejected" in r.message for r in caplog.records)


# -- #1 transport ---------------------------------------------------------- #

def test_hsts_and_nosniff_headers_are_set(client):
    r = client.get("/health")
    assert r.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
    assert r.headers["X-Content-Type-Options"] == "nosniff"


def test_security_headers_are_present_even_on_errors(client):
    r = client.post(PATH, json=_body(), headers={"X-API-Key": "wrong"})
    assert r.status_code == 401
    assert "Strict-Transport-Security" in r.headers
