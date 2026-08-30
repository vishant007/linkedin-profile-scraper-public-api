"""Fetch raw Voyager JSON for a profile, and optionally save it as a fixture.

    uv run python -m scripts.probe https://www.linkedin.com/in/thevishantshah/
    uv run python -m scripts.probe <url> --save

Fixtures make the Phase 3 resolver testable with no network and no credentials.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.config import get_settings
from app.credentials import resolve
from app.errors import ApiError
from app.voyager.client import VoyagerClient
from app.voyager.endpoints import fetch_full_profile, public_identifier_from_url

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def _assert_no_secrets(blob: str) -> None:
    """A fixture is committed to a public repo. Never let a session into one."""
    settings = get_settings()
    for name, value in (
        ("LINKEDIN_LI_AT", settings.linkedin_li_at),
        ("LINKEDIN_JSESSIONID", settings.linkedin_jsessionid),
    ):
        if value and value.strip('"') and value.strip('"') in blob:
            raise SystemExit(f"REFUSING TO SAVE: {name} appears in the payload.")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2

    url = argv[0]
    save = "--save" in argv[1:]

    public_id = public_identifier_from_url(url)
    client = VoyagerClient(resolve())

    try:
        payload = fetch_full_profile(client, public_id)
    except ApiError as exc:
        print(f"[{exc.code.value}] {exc.message}", file=sys.stderr)
        return 1

    included = payload.get("included", [])
    types: dict[str, int] = {}
    for obj in included:
        key = str(obj.get("$type", "?")).split(".")[-1]
        types[key] = types.get(key, 0) + 1

    blob = json.dumps(payload, indent=2, ensure_ascii=False)
    print(f"identifier   : {public_id}")
    print(f"bytes        : {len(blob):,}")
    print(f"included[]   : {len(included)} objects")
    print("types        :")
    for key, count in sorted(types.items(), key=lambda kv: -kv[1]):
        print(f"               {count:>3}  {key}")

    if save:
        _assert_no_secrets(blob)
        FIXTURES.mkdir(parents=True, exist_ok=True)
        target = FIXTURES / f"{public_id}.json"
        target.write_text(blob, encoding="utf-8")
        print(f"\nsaved        : {target.relative_to(Path.cwd())}")
    else:
        print("\n(pass --save to write a fixture for the Phase 3 resolver tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
