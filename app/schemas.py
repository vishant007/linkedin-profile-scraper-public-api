"""The public contract.

Shape is deliberately Tross's: an ``{input, auth_id}`` request envelope, and a
response keyed by one domain noun (``profile``) with no generic ``data`` wrapper.
Response fields are camelCase, matching every operation in their public docs.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Snake_case in Python, camelCase on the wire."""

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="ignore"
    )


# --------------------------------------------------------------------------- #
# request
# --------------------------------------------------------------------------- #

class Section(StrEnum):
    """Optional sections. Core identity fields are always returned."""

    EXPERIENCE = "experience"
    EDUCATION = "education"
    SKILLS = "skills"
    CERTIFICATIONS = "certifications"
    LANGUAGES = "languages"


DEFAULT_SECTIONS: list[Section] = list(Section)


class FetchProfileInput(CamelModel):
    profile_url: str = Field(
        description="Any LinkedIn profile URL, e.g. https://www.linkedin.com/in/someone/",
        examples=["https://www.linkedin.com/in/thevishantshah/"],
    )
    sections: list[Section] = Field(
        default_factory=lambda: list(DEFAULT_SECTIONS),
        description=(
            "Which optional sections to include. Response shaping only — upstream "
            "cost is flat, since LinkedIn returns the whole profile in one call."
        ),
    )


class FetchProfileRequest(BaseModel):
    """Tross's envelope. Note ``auth_id`` keeps its snake_case name, as theirs does."""

    model_config = ConfigDict(extra="ignore")

    input: FetchProfileInput
    auth_id: str = Field(
        description="Opaque handle to a stored LinkedIn session. Never a credential.",
        examples=["b3f1c2e4-8a90-4d21-9f77-2ce1d0a4b512"],
    )


# --------------------------------------------------------------------------- #
# response
# --------------------------------------------------------------------------- #

class WarningCode(StrEnum):
    SECTION_UNAVAILABLE = "SECTION_UNAVAILABLE"
    SECTION_PARTIAL = "SECTION_PARTIAL"
    UNRESOLVED_REFERENCE = "UNRESOLVED_REFERENCE"


class ProfileWarning(CamelModel):
    """Partial success. A section we could not see is a warning, never a failure."""

    code: WarningCode
    section: str | None = None
    message: str


class Location(CamelModel):
    country: str | None = None
    city: str | None = None
    full: str | None = None


class ProfilePicture(CamelModel):
    original: str | None = None
    sizes: list[str] = Field(default_factory=list)


class DateRange(CamelModel):
    start: str | None = None
    end: str | None = None


class Experience(CamelModel):
    title: str | None = None
    company: str | None = None
    company_urn: str | None = None
    location: str | None = None
    description: str | None = None
    dates: DateRange | None = None


class Education(CamelModel):
    school: str | None = None
    degree: str | None = None
    field_of_study: str | None = None
    dates: DateRange | None = None


class Certification(CamelModel):
    name: str | None = None
    authority: str | None = None
    url: str | None = None
    dates: DateRange | None = None


class Language(CamelModel):
    name: str | None = None
    proficiency: str | None = None


class Profile(CamelModel):
    public_identifier: str
    first_name: str | None = None
    last_name: str | None = None
    headline: str | None = None
    location: Location | None = None
    about: str | None = None
    profile_picture: ProfilePicture | None = None
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    languages: list[Language] = Field(default_factory=list)


class FetchProfileResponse(CamelModel):
    profile: Profile
    warnings: list[ProfileWarning] = Field(default_factory=list)
    fetched_at: datetime


class ErrorBody(CamelModel):
    code: str
    message: str
    retryable: bool
    request_id: str


class ErrorResponse(CamelModel):
    error: ErrorBody
