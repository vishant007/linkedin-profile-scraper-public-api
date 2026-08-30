"""Rest.li graph resolver — the heart of this project.

Voyager does not return a document. It returns a flat bag of typed objects in
`included[]` that reference one another by URN, mirroring LinkedIn's internal
storage rather than anything a caller wants. A key beginning `*` holds an
address, not a value: a person's jobs are not inside the person.

This module rebuilds the graph into one nested profile. It is a pure function
over a payload -- no network, no credentials -- which is why it can be developed
and tested entirely against a captured fixture.

Design rule throughout: a reference we cannot follow degrades to a warning and a
missing section. It never raises. LinkedIn shows different amounts of a profile
depending on who is looking, so partial data is a normal condition, and the
brief itself says "when available".
"""

from __future__ import annotations

from typing import Any, Iterable

from app.schemas import (
    Certification,
    DateRange,
    Education,
    Experience,
    Language,
    Location,
    Profile,
    ProfilePicture,
    ProfileWarning,
    Section,
    WarningCode,
)

# Profile pointer -> the section it feeds.
SECTION_POINTERS: dict[Section, str] = {
    Section.EXPERIENCE: "*profilePositionGroups",
    Section.EDUCATION: "*profileEducations",
    Section.SKILLS: "*profileSkills",
    Section.CERTIFICATIONS: "*profileCertifications",
    Section.LANGUAGES: "*profileLanguages",
}


def _short_type(obj: dict[str, Any]) -> str:
    return str(obj.get("$type", "")).split(".")[-1]


def _fmt_date(node: dict[str, Any] | None) -> str | None:
    """LinkedIn dates are partial by nature -- year only, or year and month."""
    if not isinstance(node, dict):
        return None
    year, month, day = node.get("year"), node.get("month"), node.get("day")
    if not year:
        return None
    if month and day:
        return f"{year:04d}-{month:02d}-{day:02d}"
    if month:
        return f"{year:04d}-{month:02d}"
    return f"{year:04d}"


def _date_range(node: dict[str, Any] | None) -> DateRange | None:
    if not isinstance(node, dict):
        return None
    start, end = _fmt_date(node.get("start")), _fmt_date(node.get("end"))
    if start is None and end is None:
        return None
    return DateRange(start=start, end=end)


def _largest_image(reference: Any) -> tuple[str | None, list[str]]:
    """Pull a usable URL out of LinkedIn's vectorImage structure."""
    if not isinstance(reference, dict):
        return None, []
    vector = reference.get("vectorImage") or reference
    root = vector.get("rootUrl")
    artifacts = vector.get("artifacts") or []
    if not root or not isinstance(artifacts, list):
        return None, []

    urls: list[str] = []
    for art in artifacts:
        segment = art.get("fileIdentifyingUrlPathSegment") if isinstance(art, dict) else None
        if segment:
            urls.append(f"{root}{segment}")
    return (urls[-1] if urls else None), urls


class ProfileGraph:
    """An index over `included[]`, plus the pointer-following rules."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.warnings: list[ProfileWarning] = []
        included = payload.get("included") or []
        self._by_urn: dict[str, dict[str, Any]] = {
            obj["entityUrn"]: obj
            for obj in included
            if isinstance(obj, dict) and obj.get("entityUrn")
        }
        self._included = [o for o in included if isinstance(o, dict)]

    # -- lookup ---------------------------------------------------------- #

    def by_type(self, name: str) -> dict[str, Any] | None:
        return next((o for o in self._included if _short_type(o) == name), None)

    def get(self, urn: str | None, *, section: str | None = None) -> dict[str, Any] | None:
        if not urn:
            return None
        found = self._by_urn.get(urn)
        if found is None:
            self.warn(
                WarningCode.UNRESOLVED_REFERENCE,
                f"A referenced object was not present in the response ({urn[:60]}).",
                section=section,
            )
        return found

    def follow(self, obj: dict[str, Any] | None, key: str, *, section: str | None = None):
        """Follow a `*` pointer. Handles both a single URN and a list of them."""
        if not obj:
            return None
        value = obj.get(key)
        if isinstance(value, list):
            return [self.get(u, section=section) for u in value]
        return self.get(value, section=section)

    def collection(self, obj: dict[str, Any] | None, key: str, *, section: str) -> list[dict[str, Any]]:
        """Follow a pointer to a CollectionResponse and return its elements.

        Two hops, which is the shape that trips people up: the pointer names a
        collection, and the collection names the items.
        """
        target = self.follow(obj, key, section=section)
        if target is None:
            return []
        if isinstance(target, list):  # already a list of objects
            return [o for o in target if o]

        urns = target.get("*elements") or target.get("elements") or []
        if urns and isinstance(urns[0], dict):
            return urns  # inlined rather than referenced
        resolved = [self.get(u, section=section) for u in urns]
        return [o for o in resolved if o]

    def warn(self, code: WarningCode, message: str, *, section: str | None = None) -> None:
        self.warnings.append(ProfileWarning(code=code, section=section, message=message))


# --------------------------------------------------------------------------- #
# section mappers -- one small pure function each
# --------------------------------------------------------------------------- #

def map_location(graph: ProfileGraph, profile: dict[str, Any]) -> Location | None:
    geo = graph.follow(profile, "*geoLocation", section="location")
    if not isinstance(geo, dict):
        geo = graph.by_type("Geo")
    if not isinstance(geo, dict):
        return None
    country = graph.follow(geo, "*country", section="location")
    return Location(
        full=geo.get("defaultLocalizedName"),
        city=geo.get("defaultLocalizedNameWithoutCountryName"),
        country=(country or {}).get("defaultLocalizedName") if isinstance(country, dict) else None,
    )


def map_picture(profile: dict[str, Any]) -> ProfilePicture | None:
    pic = profile.get("profilePicture")
    if not isinstance(pic, dict):
        return None
    for key in ("displayImageReference", "originalImageReference"):
        original, sizes = _largest_image(pic.get(key))
        if original:
            return ProfilePicture(original=original, sizes=sizes)
    return None


def map_experience(graph: ProfileGraph, profile: dict[str, Any]) -> list[Experience]:
    """PositionGroup -> Position. Several roles at one company form a group."""
    out: list[Experience] = []
    groups = graph.collection(profile, "*profilePositionGroups", section="experience")

    for group in groups:
        company = graph.follow(group, "*company", section="experience")
        company_name = group.get("companyName") or (company or {}).get("name")
        positions = graph.collection(group, "*profilePositionInPositionGroup", section="experience")

        if not positions:  # a group with no inner roles still carries a company
            out.append(
                Experience(
                    company=company_name,
                    company_urn=group.get("companyUrn"),
                    dates=_date_range(group.get("dateRange")),
                )
            )
            continue

        for pos in positions:
            geo = graph.follow(pos, "*geo", section="experience")
            out.append(
                Experience(
                    title=pos.get("title"),
                    company=pos.get("companyName") or company_name,
                    company_urn=pos.get("companyUrn") or group.get("companyUrn"),
                    location=pos.get("locationName")
                    or pos.get("geoLocationName")
                    or (geo or {}).get("defaultLocalizedName"),
                    description=pos.get("description"),
                    dates=_date_range(pos.get("dateRange")),
                )
            )
    return out


def map_education(graph: ProfileGraph, profile: dict[str, Any]) -> list[Education]:
    out: list[Education] = []
    for edu in graph.collection(profile, "*profileEducations", section="education"):
        school = graph.follow(edu, "*school", section="education")
        out.append(
            Education(
                school=edu.get("schoolName") or (school or {}).get("name"),
                degree=edu.get("degreeName"),
                field_of_study=edu.get("fieldOfStudy"),
                dates=_date_range(edu.get("dateRange")),
            )
        )
    return out


def map_skills(graph: ProfileGraph, profile: dict[str, Any]) -> list[str]:
    return [
        s["name"]
        for s in graph.collection(profile, "*profileSkills", section="skills")
        if s.get("name")
    ]


def map_certifications(graph: ProfileGraph, profile: dict[str, Any]) -> list[Certification]:
    return [
        Certification(
            name=c.get("name"),
            authority=c.get("authority") or c.get("displaySource"),
            url=c.get("url"),
            dates=_date_range(c.get("dateRange")),
        )
        for c in graph.collection(profile, "*profileCertifications", section="certifications")
    ]


def map_languages(graph: ProfileGraph, profile: dict[str, Any]) -> list[Language]:
    return [
        Language(name=l.get("name"), proficiency=l.get("proficiency"))
        for l in graph.collection(profile, "*profileLanguages", section="languages")
    ]


# --------------------------------------------------------------------------- #
# assembly
# --------------------------------------------------------------------------- #

_MAPPERS = {
    Section.EXPERIENCE: ("experience", map_experience),
    Section.EDUCATION: ("education", map_education),
    Section.SKILLS: ("skills", map_skills),
    Section.CERTIFICATIONS: ("certifications", map_certifications),
    Section.LANGUAGES: ("languages", map_languages),
}


def normalize(
    payload: dict[str, Any],
    public_id: str,
    sections: Iterable[Section],
) -> tuple[Profile, list[ProfileWarning]]:
    """Turn one Voyager payload into one Profile, plus honest warnings."""
    graph = ProfileGraph(payload)
    raw = graph.by_type("Profile")

    if raw is None:
        graph.warn(
            WarningCode.SECTION_UNAVAILABLE,
            "LinkedIn returned no profile object for this identifier.",
        )
        return Profile(public_identifier=public_id), graph.warnings

    profile = Profile(
        public_identifier=raw.get("publicIdentifier") or public_id,
        first_name=raw.get("firstName"),
        last_name=raw.get("lastName"),
        headline=raw.get("headline"),
        about=raw.get("summary"),
        location=map_location(graph, raw),
        profile_picture=map_picture(raw),
    )

    wanted = set(sections)
    for section, (field, mapper) in _MAPPERS.items():
        if section not in wanted:
            continue
        values = mapper(graph, raw)
        setattr(profile, field, values)
        if not values:
            graph.warn(
                WarningCode.SECTION_UNAVAILABLE,
                f"No {field} were returned. The profile may not list any, "
                "or they may not be visible to the backend session.",
                section=field,
            )

    return profile, graph.warnings
