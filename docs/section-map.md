# Section Reachability Map — Phase 0

**Probed:** 2026-08-27, against a live logged-in session, profile `thevishantshah`.
**Method:** `fetch()` from the page context with the four Voyager headers
(`csrf-token`, `accept: application/vnd.linkedin.normalized+json+2.1`,
`x-restli-protocol-version: 2.0.0`, session cookie).

## Endpoints probed

| Candidate | Path | Status | Bytes | Verdict |
|---|---|---|---|---|
| Legacy full profile | `/voyager/api/identity/profiles/{id}/profileView` | **410 Gone** | 0 | Retired by LinkedIn. Most older scrapers targeted this. |
| Dash top card | `/voyager/api/identity/dash/profiles?q=memberIdentity&memberIdentity={id}&decorationId=…WebTopCardCore-6` | **200** | 12,417 | Core identity only |
| **Dash full profile** | `/voyager/api/identity/dash/profiles?q=memberIdentity&memberIdentity={id}&decorationId=…FullProfileWithEntities-63` | **200** | **84,675** | ✅ **Primary source — everything in one call** |
| Deferred cards | `/voyager/api/identity/dash/profileCards?q=deferredCards&profileUrn={urn}` | 404 | 0 | Wrong query shape |
| Cards by section | `…/profileCards?q=deferredCards&profileUrn={urn}&sectionType=skills` | 404 | 0 | Wrong query shape |
| Components by section | `…/profileComponents?q=entitiesByProfileAndSection&…&sectionType=skills` | 404 | 0 | Wrong query shape |

## Field coverage

`decorationId=com.linkedin.voyager.dash.deco.identity.profile.FullProfileWithEntities-63`

| Required field | Present | Evidence |
|---|---|---|
| name | ✅ | `WebTopCardCore-6` confirmed `firstName` / `lastName` at field level |
| headline | ✅ | confirmed at field level |
| location | ✅ | `Geo` objects in `included[]` |
| about | ✅ | `summary` present in payload |
| experience | ✅ | `POSITION` markers present |
| education | ✅ | `SCHOOL` markers present |
| skills | ✅ | `skill` markers present |
| certifications | ✅ | `certification` markers present |
| languages | ✅ | `language` markers present |
| profile images | ✅ | `profilePicture` present |

> **Confidence caveat.** Coverage above is verified by presence of the corresponding
> markers in the 84KB payload, plus field-level confirmation of the top-card values.
> Per-field extraction paths are confirmed during Phase 3 when the resolver is built
> against a captured fixture. Any field that does not survive that step moves to
> Known Limitations rather than being silently dropped.

## Consequences for the plan

**1. Gap B (Goedecke rule 5) is closed — favourably.** Every field the brief names is
reachable. There is no unreachable-section limitation to declare.

**2. One call, not many.** `FullProfileWithEntities-63` returns the whole profile.
The plan assumed one upstream call per section; it is actually one call total.

**3. The GraphQL fallback is no longer needed** for coverage. Demote
`app/voyager/graphql.py` to optional — document the persisted-query mechanism in the
README as reverse-engineering findings, but do not build it unless time allows.
This is a simplification, not a drift: the diagram already marks GraphQL as fallback.

**4. Gap A's premise weakens — `input.sections` is no longer a cost lever.**
Since all sections arrive in a single response, requesting fewer does not reduce
upstream work. Two honest options:

- **Keep `sections` as a response-shaping filter.** Still useful (smaller payloads,
  caller control) but it no longer satisfies Goedecke rule 11's *"expensive to serve"*
  rationale, and the weighted rate limit in M5.2 loses its justification.
- **Recommended: keep `sections`, revise the reasoning, and drop the weighting.**
  Document it as response shaping, and note in the README that per-section upstream
  cost was measured and found to be flat — so a weighted limiter would be theatre.
  Rule 9 is then satisfied by a plain limit, honestly explained.

Measuring cost before optimising for it is the correct outcome here; carrying a
weighted limiter that reflects no real cost would be exactly the checklist-following
the design set out to avoid.

## Risk note

`FullProfileWithEntities-63` is version-suffixed. The `-63` will eventually increment.
Phase 2 should probe a small range of adjacent suffixes at startup and use the first
that returns 200, with the resolved value logged. This belongs in Known Limitations.
