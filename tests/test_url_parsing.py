"""M2.3 — every URL form a caller might realistically paste."""

import pytest

from app.errors import InvalidProfileUrl
from app.voyager.endpoints import public_identifier_from_url as parse


@pytest.mark.parametrize(
    "value",
    [
        "https://www.linkedin.com/in/thevishantshah/",
        "https://www.linkedin.com/in/thevishantshah",
        "http://www.linkedin.com/in/thevishantshah/",
        "https://linkedin.com/in/thevishantshah/",
        "www.linkedin.com/in/thevishantshah",
        "linkedin.com/in/thevishantshah",
        "https://in.linkedin.com/in/thevishantshah",
        "https://www.linkedin.com/in/thevishantshah/?originalSubdomain=in",
        "https://www.linkedin.com/in/thevishantshah/details/experience/",
        "  https://www.linkedin.com/in/thevishantshah/  ",
        "thevishantshah",
    ],
)
def test_accepts_every_common_form(value):
    assert parse(value) == "thevishantshah"


def test_percent_encoding_is_decoded():
    assert parse("https://www.linkedin.com/in/jos%C3%A9-garcia") == "josé-garcia"


def test_hyphenated_id_suffix_preserved():
    url = "https://www.linkedin.com/in/prathamesh-patil-794441385/"
    assert parse(url) == "prathamesh-patil-794441385"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "https://example.com/in/someone",
        "https://linkedin.com.evil.example/in/someone",
        "https://www.linkedin.com/company/tross",
        "https://www.linkedin.com/feed/",
        "https://www.linkedin.com/in/",
    ],
)
def test_rejects_anything_that_is_not_a_profile(value):
    with pytest.raises(InvalidProfileUrl):
        parse(value)
