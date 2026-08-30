"""M5.1 — the profile cache.

Its real job is protecting a single upstream session from repeated identical
requests, so the tests are mostly about *not* calling LinkedIn.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.cache import ProfileCache, reset_cache
from app.config import get_settings
from app.schemas import Profile, Section

PATH = "/api/integrations/linkedin/fetch-profile"
BODY = {
    "input": {"profileUrl": "https://www.linkedin.com/in/thevishantshah/"},
    "auth_id": "b3f1c2e4-8a90-4d21-9f77-2ce1d0a4b512",
}


# -- unit ----------------------------------------------------------------- #

def test_key_is_case_insensitive_and_section_order_independent():
    c = ProfileCache(60)
    a = c.key("x", "TheVishantShah", [Section.SKILLS, Section.EXPERIENCE])
    b = c.key("x", "thevishantshah", [Section.EXPERIENCE, Section.SKILLS])
    assert a == b


def test_key_separates_auth_ids():
    """Guards a real data-leak class if this ever becomes multi-tenant."""
    c = ProfileCache(60)
    assert c.key("alice", "p", [Section.SKILLS]) != c.key("bob", "p", [Section.SKILLS])


def test_entries_expire():
    c = ProfileCache(ttl_seconds=0)
    k = c.key("x", "p", [Section.SKILLS])
    c.put(k, Profile(public_identifier="p"), [], datetime.now(timezone.utc))
    assert c.get(k) is None


def test_eviction_is_bounded():
    c = ProfileCache(60, max_entries=3)
    for i in range(10):
        c.put(c.key("x", f"p{i}", []), Profile(public_identifier=f"p{i}"), [], datetime.now(timezone.utc))
    assert len(c) == 3


# -- through the API ------------------------------------------------------ #

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_KEYS", "test-key")
    monkeypatch.setenv("LINKEDIN_LI_AT", "test-li-at")
    monkeypatch.setenv("LINKEDIN_JSESSIONID", '"ajax:0000000000"')
    monkeypatch.setenv("CACHE_TTL_SECONDS", "600")
    monkeypatch.setenv("AUTH_ID", "b3f1c2e4-8a90-4d21-9f77-2ce1d0a4b512")
    get_settings.cache_clear()
    reset_cache()

    payload = json.loads(
        (Path(__file__).parent / "fixtures" / "thevishantshah.json").read_text()
    )
    calls: list[str] = []

    import app.routes as routes

    def counted(_client, public_id):
        calls.append(public_id)
        return payload

    monkeypatch.setattr(routes, "fetch_full_profile", counted)

    from app.main import app

    with TestClient(app) as c:
        c.upstream_calls = calls
        yield c

    get_settings.cache_clear()
    reset_cache()


def test_repeat_requests_hit_the_cache_not_linkedin(client):
    """The point of the whole module: ten clicks, one upstream call."""
    for _ in range(10):
        r = client.post(PATH, json=BODY, headers={"X-API-Key": "test-key"})
        assert r.status_code == 200
    assert len(client.upstream_calls) == 1


def test_cache_header_reports_hit_and_miss(client):
    first = client.post(PATH, json=BODY, headers={"X-API-Key": "test-key"})
    second = client.post(PATH, json=BODY, headers={"X-API-Key": "test-key"})
    assert first.headers["X-Cache"] == "MISS"
    assert second.headers["X-Cache"] == "HIT"


def test_cached_response_keeps_the_original_fetched_at(client):
    """A cached body must not claim to be fresher than it is."""
    first = client.post(PATH, json=BODY, headers={"X-API-Key": "test-key"}).json()
    second = client.post(PATH, json=BODY, headers={"X-API-Key": "test-key"}).json()
    assert first["fetchedAt"] == second["fetchedAt"]


def test_different_sections_are_cached_separately(client):
    body_a = {**BODY, "input": {**BODY["input"], "sections": ["skills"]}}
    body_b = {**BODY, "input": {**BODY["input"], "sections": ["education"]}}
    client.post(PATH, json=body_a, headers={"X-API-Key": "test-key"})
    client.post(PATH, json=body_b, headers={"X-API-Key": "test-key"})
    assert len(client.upstream_calls) == 2


def test_cached_body_is_identical_to_the_live_one(client):
    a = client.post(PATH, json=BODY, headers={"X-API-Key": "test-key"}).json()
    b = client.post(PATH, json=BODY, headers={"X-API-Key": "test-key"}).json()
    assert a == b
