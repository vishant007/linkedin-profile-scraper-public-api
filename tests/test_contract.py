"""Phase 1 conformance: the wire shape must match the frozen contract exactly."""

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings

PATH = "/api/integrations/linkedin/fetch-profile"
BODY = {
    "input": {"profileUrl": "https://www.linkedin.com/in/thevishantshah/"},
    "auth_id": "b3f1c2e4-8a90-4d21-9f77-2ce1d0a4b512",
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_KEYS", "test-key")
    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def test_missing_key_returns_error_envelope(client):
    r = client.post(PATH, json=BODY)
    assert r.status_code == 401
    err = r.json()["error"]
    assert err["code"] == "INVALID_API_KEY"
    assert err["retryable"] is False
    assert err["requestId"].startswith("req_")


def test_wrong_key_rejected(client):
    r = client.post(PATH, json=BODY, headers={"X-API-Key": "nope"})
    assert r.status_code == 401


def test_success_shape_matches_contract(client):
    r = client.post(PATH, json=BODY, headers={"X-API-Key": "test-key"})
    assert r.status_code == 200
    body = r.json()

    # Named domain key, no generic envelope -- this is the Tross convention.
    assert set(body) == {"profile", "warnings", "fetchedAt"}
    assert "data" not in body
    assert body["profile"]["publicIdentifier"]
    assert isinstance(body["warnings"], list)


def test_get_alias_works(client):
    r = client.get(
        PATH,
        params={"profileUrl": "https://www.linkedin.com/in/x/", "auth_id": "a"},
        headers={"X-API-Key": "test-key"},
    )
    assert r.status_code == 200


def test_malformed_body_uses_the_same_envelope(client):
    r = client.post(PATH, json={"input": {}}, headers={"X-API-Key": "test-key"})
    assert r.status_code == 422
    assert set(r.json()["error"]) == {"code", "message", "retryable", "requestId"}


def test_no_version_segment_in_any_route():
    """Goedecke rule 4 — and no Tross path carries a version segment either."""
    from app.main import app

    paths = list(app.openapi()["paths"])
    assert paths, "expected at least one documented path"
    assert not any("/v1" in p for p in paths), paths


def test_path_grammar_matches_tross():
    from app.main import app

    assert "/api/integrations/linkedin/fetch-profile" in app.openapi()["paths"]
