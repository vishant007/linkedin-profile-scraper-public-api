"""Phase 3 — the resolver, tested offline against a real captured payload.

No network, no credentials. This is the point of capturing a fixture.
"""

import json
from pathlib import Path

import pytest

from app.schemas import DEFAULT_SECTIONS, Section, WarningCode
from app.voyager.resolver import normalize

FIXTURE = Path(__file__).parent / "fixtures" / "thevishantshah.json"


@pytest.fixture(scope="module")
def payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def result(payload):
    return normalize(payload, "thevishantshah", DEFAULT_SECTIONS)


# -- scalars ------------------------------------------------------------- #

def test_identity_fields(result):
    profile, _ = result
    assert profile.public_identifier == "thevishantshah"
    assert profile.first_name and profile.last_name
    assert profile.headline


def test_about_is_the_summary_field(result):
    profile, _ = result
    assert profile.about and len(profile.about) > 100


def test_location_resolved_through_geo_pointer(result):
    profile, _ = result
    assert profile.location is not None
    assert profile.location.full


def test_profile_picture_url_is_built_from_vector_image(result):
    profile, _ = result
    assert profile.profile_picture is not None
    assert profile.profile_picture.original.startswith("https://")
    assert len(profile.profile_picture.sizes) >= 1


# -- the graph walk ------------------------------------------------------- #

def test_experience_flattens_position_groups(result):
    profile, _ = result
    assert len(profile.experience) >= 4
    first = profile.experience[0]
    assert first.title and first.company
    assert first.dates and first.dates.start


def test_education_resolves_school_pointer(result):
    profile, _ = result
    assert len(profile.education) == 1
    assert profile.education[0].school


def test_skills_and_certifications_counts_match_the_capture(result):
    profile, _ = result
    assert len(profile.skills) == 20
    assert len(profile.certifications) == 10
    assert all(isinstance(s, str) and s for s in profile.skills)
    assert profile.certifications[0].name


def test_partial_dates_render_without_a_fake_day(result):
    profile, _ = result
    starts = [e.dates.start for e in profile.experience if e.dates and e.dates.start]
    assert starts
    assert all(len(s) in (4, 7, 10) for s in starts)


# -- honesty about missing data ------------------------------------------- #

def test_empty_section_becomes_a_warning_not_a_failure(result):
    """This profile lists no languages. That is a warning, not an error."""
    profile, warnings = result
    assert profile.languages == []
    assert any(
        w.section == "languages" and w.code == WarningCode.SECTION_UNAVAILABLE
        for w in warnings
    )


def test_sections_filter_controls_the_response(payload):
    profile, _ = normalize(payload, "thevishantshah", [Section.SKILLS])
    assert profile.skills
    assert profile.experience == []
    assert profile.education == []


# -- resilience ----------------------------------------------------------- #

def test_broken_pointer_warns_and_still_returns_a_profile(payload):
    """A dangling URN must degrade one section, never fail the request."""
    broken = json.loads(json.dumps(payload))
    prof = next(o for o in broken["included"] if o["$type"].endswith(".Profile"))
    prof["*profileSkills"] = "urn:li:fsd_profileSkill:(DOES_NOT_EXIST,0)"

    profile, warnings = normalize(broken, "thevishantshah", DEFAULT_SECTIONS)

    assert profile.first_name          # the rest of the profile survived
    assert profile.skills == []
    assert any(w.code == WarningCode.UNRESOLVED_REFERENCE for w in warnings)


def test_empty_payload_does_not_raise(payload):
    profile, warnings = normalize({"included": []}, "someone", DEFAULT_SECTIONS)
    assert profile.public_identifier == "someone"
    assert warnings


def test_resolver_is_pure_no_http_client_imported():
    import app.voyager.resolver as r

    source = Path(r.__file__).read_text(encoding="utf-8")
    for banned in ("curl_cffi", "requests", "httpx", "VoyagerClient"):
        assert banned not in source, f"{banned} must not appear in the resolver"
