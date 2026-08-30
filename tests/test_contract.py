"""Phase 1 conformance: the wire shape must match the frozen contract exactly."""

import json
from pathlib import Path

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
    """Hermetic: the upstream call is stubbed with the captured fixture.

    These tests assert the wire contract, so they must never touch LinkedIn --
    otherwise the suite is slow, flaky, and quietly burns the backend session.
    The real resolver still runs, so the response shape is genuine.
    """
    monkeypatch.setenv("API_KEYS", "test-key")
    monkeypatch.setenv("LINKEDIN_LI_AT", "test-li-at")
    monkeypatch.setenv("LINKEDIN_JSESSIONID", '"ajax:0000000000"')
    get_settings.cache_clear()

    payload = json.loads(
        (Path(__file__).parent / "fixtures" / "thevishantshah.json").read_text()
    )

    import app.routes as routes

    monkeypatch.setattr(routes, "fetch_full_profile", lambda _client, _id: payload)

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
    assert body["profile"]["publicIdentifier"] == "thevishantshah"
    assert body["profile"]["firstName"]
    assert body["profile"]["experience"]
    assert isinstance(body["warnings"], list)


def test_get_alias_works(client):
    r = client.get(
        PATH,
        params={
            "profileUrl": "https://www.linkedin.com/in/thevishantshah/",
            "auth_id": "b3f1c2e4-8a90-4d21-9f77-2ce1d0a4b512",
        },
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


# --------------------------------------------------------------------------- #
# /health — M5.3
# --------------------------------------------------------------------------- #

def _reset_health_cache():
    import app.main as m

    m._health_cache.update(checked_at=0.0, valid=None, detail=None)


def test_health_reports_a_live_session(client, monkeypatch):
    import app.main as m

    _reset_health_cache()
    monkeypatch.setattr(m, "_probe_session", lambda: (True, None))

    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["sessionValid"] is True
    assert body["checkedAt"].endswith("Z")
    assert "remedy" not in body


def test_health_reports_a_dead_session_with_a_remedy(client, monkeypatch):
    """A reviewer meeting a dead session should be told what is wrong, not left guessing."""
    import app.main as m

    _reset_health_cache()
    monkeypatch.setattr(
        m, "_probe_session", lambda: (False, "The backend LinkedIn session is no longer valid.")
    )

    r = client.get("/health")
    assert r.status_code == 200          # the service is up; the credential is not
    body = r.json()
    assert body["status"] == "degraded"
    assert body["sessionValid"] is False
    assert "no longer valid" in body["detail"]
    assert "LINKEDIN_LI_AT" in body["remedy"]


def test_health_probe_is_cached(client, monkeypatch):
    """Repeated pings must not become the traffic that gets the session flagged."""
    import app.main as m

    _reset_health_cache()
    calls = []
    monkeypatch.setattr(m, "_probe_session", lambda: (calls.append(1), (True, None))[1])

    for _ in range(5):
        client.get("/health")
    assert len(calls) == 1


def test_health_never_raises_even_if_the_probe_explodes(client, monkeypatch):
    import app.main as m

    _reset_health_cache()

    def boom():
        raise RuntimeError("upstream on fire")

    monkeypatch.setattr(m, "_probe_session", boom)
    # _probe_session is replaced wholesale, so the guard under test is the route's.
    try:
        r = client.get("/health")
    except RuntimeError:
        raise AssertionError("/health must never propagate an exception")
    assert r.status_code in (200, 500)
