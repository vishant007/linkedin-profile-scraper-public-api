# LinkedIn Profile API

Accepts a LinkedIn profile URL and returns the profile as structured JSON, sourced from LinkedIn's **internal Voyager API** rather than by scraping the rendered page.

Request and response shapes deliberately mirror the conventions published at [app.ontross.com/docs](https://app.ontross.com/docs).

```bash
curl -X POST https://<host>/api/integrations/linkedin/fetch-profile \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input":{"profileUrl":"https://www.linkedin.com/in/thevishantshah/"},
       "auth_id":"b3f1c2e4-8a90-4d21-9f77-2ce1d0a4b512"}'
```

---

## Contents

- [Try it in Postman](#try-it-in-postman-fastest)
- [Quick start](#quick-start)
- [API reference](#api-reference)
- [Approach](#approach--how-the-api-was-reverse-engineered)
- [Design decisions](#design-decisions)
- [Known limitations](#known-limitations)
- [If the session expires](#if-the-session-expires)
- [Legal and ethical posture](#legal-and-ethical-posture)
- [Project layout](#project-layout)
- [Testing](#testing)
- [Deployment](#deployment)

---

## Try it in Postman (fastest)

A ready-made collection lives at [`postman/LinkedIn-Profile-API.postman_collection.json`](postman/LinkedIn-Profile-API.postman_collection.json).

1. **Postman → Import →** drop in that file (or paste its raw GitHub URL)
2. Open the collection's **Variables** tab and paste your API key into `apiKey`
3. Optionally change `profileUrl` to any LinkedIn profile
4. Open **2 · Fetch profile** and hit **Send**

`baseUrl` and `auth_id` are pre-filled; the key is the only thing you supply.

Seven requests are included — the happy path, section filtering, the GET alias, and three deliberate error cases (401, 403, 400). **Every request carries assertions**, so the Test Results tab reports whether the response contract, the error envelope, and the security headers are all correct. Running the whole collection takes a few seconds and exercises the API's behaviour rather than just its availability.

> `apiKey` ships empty on purpose. This project keeps credentials out of version control, and an API key is a credential — committing a working one to a public repository would contradict the practice the rest of the codebase follows.

---

## Quick start

**Requirements:** Python 3.12+ and [`uv`](https://docs.astral.sh/uv/). `uv` provisions the interpreter, so a system Python of any version is fine.

```bash
git clone <repo-url> && cd tross-assignment
uv sync
cp .env.example .env      # then fill it in, see below
```

### Configuration

All configuration is environment variables. Nothing sensitive is ever committed.

| Variable | Required | Description |
| --- | --- | --- |
| `API_KEYS` | yes | Comma-separated keys that callers present in `X-API-Key`. Invent your own. |
| `LINKEDIN_LI_AT` | yes | The backend LinkedIn session cookie. |
| `LINKEDIN_JSESSIONID` | yes | Source of the `csrf-token` header. Looks like `"ajax:1234567890123456789"`; surrounding quotes are stripped for you. |
| `CACHE_TTL_SECONDS` | no | Default `900`. |
| `RATE_LIMIT_PER_MINUTE` | no | Default `30`. |

**Obtaining the two cookies:** sign in to LinkedIn in Chrome, then **DevTools → Application → Cookies → `https://www.linkedin.com`** and copy the `li_at` and `JSESSIONID` values.

`li_at` is `HttpOnly`, so it cannot be read by page JavaScript — that is a deliberate LinkedIn defence against session theft, and it is why this is a manual step rather than an automated one. Treat the value like a password: it grants full account access without needing one. Revoke it at any time with **LinkedIn → Settings → Sign out of all sessions**.

### Verify and run

```bash
uv run python -m scripts.mint_session   # confirms the session is live
uv run pytest                           # 40 tests, no network, no credentials needed
uv run uvicorn app.main:app --port 8000
```

Then open **`http://127.0.0.1:8000/docs`** for interactive API documentation generated from the schema, or `/redoc` for a reading layout.

---

## API reference

**Base path:** `/api/integrations/linkedin`
**Authentication:** `X-API-Key: <key>` on every request.

There is no version segment in any path. See [Design decisions](#design-decisions).

### `POST /api/integrations/linkedin/fetch-profile`

The primary operation.

**Request**

```jsonc
{
  "input": {
    "profileUrl": "https://www.linkedin.com/in/thevishantshah/",
    "sections": ["experience", "education", "skills", "certifications", "languages"]
  },
  "auth_id": "b3f1c2e4-8a90-4d21-9f77-2ce1d0a4b512"
}
```

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `input.profileUrl` | string | yes | Any LinkedIn profile URL form, or a bare identifier. See [accepted forms](#accepted-url-forms). |
| `input.sections` | string[] | no | Which optional sections to include. Defaults to all five. Response shaping only — see the note below. |
| `auth_id` | string | yes | Opaque handle to a stored LinkedIn session. Never a credential. |

Valid `sections` values: `experience`, `education`, `skills`, `certifications`, `languages`. Core identity fields — name, headline, location, about, profile image — are always returned.

> **`sections` does not reduce upstream cost.** LinkedIn returns the entire profile in a single call, so requesting fewer sections produces a smaller response but performs exactly the same upstream work. This was measured, not assumed; see [Design decisions](#design-decisions).

**Response — `200 OK`**

```json
{
  "profile": {
    "publicIdentifier": "thevishantshah",
    "firstName": "Vishant",
    "lastName": "Shah",
    "headline": "AI Software Engineer@Flytbase",
    "location": {
      "country": "India",
      "city": "Pune District, Maharashtra",
      "full": "Pune District, Maharashtra, India"
    },
    "about": "Hello Geeks, Vishant here, a full-stack web developer, better at …",
    "profilePicture": {
      "original": "https://media.licdn.com/dms/image/v2/D4D03AQGdSqbDCA…",
      "sizes": ["… 4 sizes, smallest first"]
    },
    "experience": [
      {
        "title": "Software Engineer",
        "company": "FlytBase",
        "companyUrn": "urn:li:fsd_company:13256881",
        "location": "Pune District",
        "description": "Autonomous drone-operations platform, 56 microservices. …",
        "dates": { "start": "2025-07" }
      }
    ],
    "education": [
      {
        "school": "Parul University",
        "degree": "Bachelor's degree",
        "fieldOfStudy": "Computer Science",
        "dates": { "start": "2020-04", "end": "2024-04" }
      }
    ],
    "skills": ["RabbitMQ", "Docker", "Airbyte", "n8n", "Redis"],
    "certifications": [
      {
        "name": "Introduction To Internet Of Things",
        "authority": "NPTEL",
        "url": "https://drive.google.com/file/d/1UZ3…",
        "dates": { "start": "2023-11" }
      }
    ],
    "languages": []
  },
  "warnings": [
    {
      "code": "SECTION_UNAVAILABLE",
      "section": "languages",
      "message": "No languages were returned. The profile may not list any, or they may not be visible to the backend session."
    }
  ],
  "fetchedAt": "2026-08-30T09:14:22.481203Z"
}
```

Fields absent from the upstream response are omitted rather than returned as `null`.

**Dates are deliberately imprecise.** LinkedIn frequently supplies only a year, or a year and month. Values are rendered at whatever precision was actually received — `"2025"`, `"2025-07"` or `"2025-07-14"` — rather than padded to a full ISO date. Padding would fabricate precision the source never provided.

### `GET /api/integrations/linkedin/fetch-profile`

A convenience alias taking `profileUrl`, `auth_id` and repeated `sections` as query parameters. Returns the identical contract.

```bash
curl -G https://<host>/api/integrations/linkedin/fetch-profile \
  -H "X-API-Key: $API_KEY" \
  --data-urlencode "profileUrl=https://www.linkedin.com/in/thevishantshah/" \
  --data-urlencode "auth_id=b3f1c2e4-8a90-4d21-9f77-2ce1d0a4b512"
```

POST is the primary method. GET exists because it is what people reach for first, but note that query parameters land in access logs, browser history and `Referer` headers — so POST is preferable for anything handling personal data.

### `GET /health`

Liveness, plus whether the backend LinkedIn session is still usable. Requires no API key.

```json
{ "status": "ok", "sessionValid": true, "checkedAt": "2026-08-30T11:47:43.007587Z" }
```

When the session has expired it says so, and says what to do about it:

```json
{
  "status": "degraded",
  "sessionValid": false,
  "checkedAt": "2026-09-03T11:47:43.007587Z",
  "detail": "The backend LinkedIn session is no longer valid and must be renewed.",
  "remedy": "Renew LINKEDIN_LI_AT and LINKEDIN_JSESSIONID in the environment. See the README section 'If the session expires'."
}
```

**It always returns `200`.** The service is running either way; an expired credential is an operator task, not a caller error or a crashed process. Returning `503` would cause a platform health check to restart a container that has nothing wrong with it.

The probe calls `/voyager/api/me` — about 2.8 kB, against roughly 12 kB for the smallest profile projection — and asks the semantically correct question, *"is this session still me?"*, without fetching a third party's profile to find out. **The result is cached for 60 seconds**, so uptime monitors, keep-warm pings and a reviewer hitting refresh cannot themselves become the traffic that gets the session flagged.

### Warnings

A warning means *the request succeeded but you should know something*. Warnings never accompany a non-2xx response.

| Code | Meaning |
| --- | --- |
| `SECTION_UNAVAILABLE` | A requested section returned nothing. The profile may not list any, or the backend session may not be permitted to see it. |
| `SECTION_PARTIAL` | A section was returned incompletely. |
| `UNRESOLVED_REFERENCE` | An object referenced by the upstream payload was not present in it. That section is empty; the rest of the profile is unaffected. |

This exists because the brief asks for fields *"when available"*, and because LinkedIn genuinely discloses different amounts of a profile depending on the viewer's relationship to it. A section that is not visible is a normal condition, not a failure.

### Errors

Every failure — including request validation — returns the same envelope.

```json
{
  "error": {
    "code": "LINKEDIN_SESSION_EXPIRED",
    "message": "The backend LinkedIn session is no longer valid and must be renewed.",
    "retryable": false,
    "requestId": "req_40f05b18ef824c2790ef"
  }
}
```

| Code | HTTP | Retryable | Cause |
| --- | --- | --- | --- |
| `INVALID_API_KEY` | 401 | no | Missing or unrecognised `X-API-Key`. |
| `INVALID_REQUEST` | 422 | no | Body did not match the schema. |
| `INVALID_PROFILE_URL` | 400 | no | Not a LinkedIn profile URL. |
| `PROFILE_NOT_FOUND` | 404 | no | LinkedIn has no profile at that identifier. |
| `LINKEDIN_SESSION_EXPIRED` | 502 | **no** | The backend session died. Retrying cannot help; a human must renew it. |
| `UPSTREAM_UNAVAILABLE` | 502 | yes | LinkedIn was unreachable, rate-limiting, or returned something unusable. |
| `RATE_LIMITED` | 429 | yes | Caller exceeded their allowance. Accompanied by `Retry-After`. |
| `INTERNAL_ERROR` | 500 | yes | Unexpected. Quote `requestId` when reporting. |

`retryable` is explicit so callers do not have to infer retry behaviour from a status code. Every response also carries an `X-Request-Id` header.

### Accepted URL forms

All of these resolve to the identifier `thevishantshah`:

```
https://www.linkedin.com/in/thevishantshah/
https://www.linkedin.com/in/thevishantshah
http://www.linkedin.com/in/thevishantshah/
https://linkedin.com/in/thevishantshah/
www.linkedin.com/in/thevishantshah
linkedin.com/in/thevishantshah
https://in.linkedin.com/in/thevishantshah          # regional subdomains
https://www.linkedin.com/in/thevishantshah/?originalSubdomain=in
https://www.linkedin.com/in/thevishantshah/details/experience/
thevishantshah                                      # bare identifier
```

Rejected with `INVALID_PROFILE_URL`: non-LinkedIn hosts, lookalike hosts such as `linkedin.com.evil.example`, and non-profile paths such as `/company/…` and `/feed/`.

---

## Approach — how the API was reverse engineered

A fuller write-up with evidence is in [`docs/approach.html`](docs/approach.html), and the endpoint survey is in [`docs/section-map.md`](docs/section-map.md).

### The page is not the product

Loading `linkedin.com/in/<slug>` does not deliver a finished page. The browser receives a mostly-empty shell whose JavaScript then requests the profile data separately, receives clean typed JSON, and paints it into HTML.

The structured data therefore already exists upstream of anything visible. Those requests go to paths under `/voyager/api/` — **Voyager** being LinkedIn's internal API, the one their own front end uses. It is undocumented and unsupported; its existence is known only because its traffic is observable.

This matters because the brief asks for LinkedIn's *APIs* to be reverse engineered, not for a page to be scraped. Those produce very different systems.

> **Not to be confused with LinkedIn's official Developer API.** That one is documented, partner-gated and OAuth-authenticated — and it cannot return an arbitrary person's profile at all, only the authenticated user's own or those of people who explicitly authorise the calling application. It cannot satisfy this brief under any configuration.

### Discovery

Endpoints were found by observation: open a profile in a logged-in browser, filter the network inspector on `/voyager/`, and read what the page requests of its own accord. One page load produced six such calls; most are presence polling, notification counts and telemetry. Separating signal from noise is most of the work.

Six candidate endpoints were then probed directly:

| Candidate | Result |
| --- | --- |
| `/voyager/api/identity/profiles/{id}/profileView` | **410 Gone** — retired. This is what most published scraping guides still target. |
| `identity/dash/profiles` + `WebTopCardCore-6` | 200, 12 KB — identity fields only |
| **`identity/dash/profiles` + `FullProfileWithEntities-63`** | **200, 114 KB — the entire profile** |
| `identity/dash/profileCards?q=deferredCards` | 404 |
| `…/profileCards?…&sectionType=skills` | 404 |
| `…/profileComponents?q=entitiesByProfileAndSection` | 404 |

One call returns everything the brief asks for. There is no per-section fan-out.

### Authentication

Two cookies, defending two different things:

- **`li_at`** is the session. Without it, LinkedIn responds `302 → /login`.
- **`JSESSIONID`** supplies the `csrf-token` header. Without it, LinkedIn responds `403` even with a perfectly valid session — because the session cookie alone cannot prove the request originated from a real LinkedIn page rather than from another site riding the user's cookies.

Two further headers are required, and each was verified by removing it:

| Header | Removed | Effect |
| --- | --- | --- |
| `cookie` | | `302 → /login` |
| `csrf-token` | | `403` |
| `accept: application/vnd.linkedin.normalized+json+2.1` | | `200`, but a nested shape instead of the flat graph |
| `x-restli-protocol-version: 2.0.0` | | `400` — URN and list parameters parsed under the older grammar |

The `accept` header is the subtle one: it is what produces the flattened `included[]` representation the entire resolver is built around.

### The response format is the real work

Voyager speaks **Rest.li**, LinkedIn's own RPC framework. Responses are not nested documents. They are a flat array of typed objects that reference one another by URN:

```jsonc
{
  "data": { "*elements": ["urn:li:fsd_profile:ACoAADF3cUc…"] },   // a pointer, not a person
  "included": [
    { "$type": "…identity.profile.Profile",
      "firstName": "Vishant",
      "*profilePositionGroups": "urn:li:fsd_…",                   // an address
      "*profileEducations":     "urn:li:fsd_…" },
    { "$type": "…common.CollectionResponse", "*elements": ["urn:li:fsd_position:…"] },
    // … 90 more, all siblings
  ]
}
```

**The governing rule: a field name beginning `*` holds an address, not a value.** A person's jobs are not inside the person.

A real capture contained **92 objects**: 20 `Skill`, 12 `Company`, 10 `Certification`, 4 `Position`, 4 `PositionGroup`, 4 `Geo`, plus `Education`, `School`, `Profile` and others.

Reassembling that into one nested document is what [`app/voyager/resolver.py`](app/voyager/resolver.py) does, and it is the substantive engineering of this project. Three details are worth naming:

1. **Resolution is two hops.** A pointer on the profile names a `CollectionResponse`; that collection's `*elements` then names the actual items. A single-hop implementation silently returns nothing.
2. **Experience is nested a further level.** `*profilePositionGroups` yields `PositionGroup` records which reference their own `Position` records, because several roles at one company are modelled as a group.
3. **Images are not URLs.** `profilePicture` holds a `vectorImage` with a `rootUrl` and a list of artifacts; a usable URL is the concatenation of the two.

### Transport: no browser

Headless browsers exist to execute JavaScript and build a page. **Voyager returns JSON — there is nothing to render.** The only thing a browser would contribute is request realism, and there is a far smaller tool for that.

Bot detection begins at the **TLS handshake**, before a single header is parsed. The cipher suites a client offers, their order and the extension set form a recognisable pattern hashed into a **JA3 fingerprint**. A default Python HTTP client produces a JA3 that identifies it as Python, and no amount of setting a browser `User-Agent` conceals that.

[`curl_cffi`](https://github.com/lexiforest/curl_cffi) resolves this directly — it is a binding over a patched libcurl that reproduces a real browser's TLS and HTTP/2 handshake:

```python
from curl_cffi import requests
r = requests.get(url, headers=HEADERS, impersonate="chrome")
```

| | Headless browser | `curl_cffi` |
| --- | --- | --- |
| Memory | ~1 GB resident | ~50 MB |
| Cold start | seconds | instant |
| Extra code | session lifecycle, crash recovery | none |
| Detection surface | TLS **and** `navigator.webdriver`, GPU stack, client hints | TLS and HTTP/2 only, matched to Chrome |

No browser appears anywhere in `app/`. A test asserts this.

### For comparison: the reference implementation

The brief cites PhantomBuster's LinkedIn Profile Scraper. Its own public API discloses its inputs — `linkedinprofileurl`, `linkedinliatsessioncookie` and `useragent`. Requiring the third is informative: a real browser supplies its own User-Agent, so asking the user for it indicates requests are being constructed by hand and replayed server-side.

Their product page also states that scraper does not return profile pictures, full work history, skills or endorsements, which are split into a separate product. This API returns all of them from one endpoint.

---

## Design decisions

The response schema was ours to design. Rather than invent conventions, it follows Tross's own — verified across five documented operations (`tn/fetch-patient-info`, `tn/fetch-clinician-details`, `ecw/create-telephonic-encounter`, `ecw/fetch-appointments`, `availity/fetch-claims`) — and fills their documented gaps from Sean Goedecke's [*Good API Design*](https://www.seangoedecke.com/good-api-design/).

Goedecke's opening principle is that good APIs are *boring*: familiar enough to understand before reading the documentation. Mirroring an existing house style is that principle applied, not imitation for its own sake.

### Adopted from Tross's documentation

| Convention | Evidence |
| --- | --- |
| `POST` for every operation, reads included | All five documented operations are POST, including three `fetch-*` |
| `/api/integrations/{vendor}/{verb-noun}` | kebab-case, verb first |
| No version segment | No Tross path carries one |
| `X-API-Key` header | Identical across all five |
| `{ "input": {…}, "auth_id": "…" }` request envelope | Identical across all five |
| Response keyed by one domain noun, **no generic `data` wrapper** | `{patient, patient_statistics}`, `{encounters: […]}`, `{claims: […]}`, `{clinician: {…}}` |
| `warnings` array | `create-telephonic-encounter` returns `{encounterId, created, warnings}` |
| camelCase response fields, ISO dates | Their output convention throughout |

Two details are deliberate rather than accidental. **`auth_id` keeps its snake_case name** beside otherwise camelCase fields, because that is exactly what Tross does. And their *inputs* are inconsistently named across integrations while their *outputs* never are — the implied philosophy being to normalise what you return and mirror what you receive.

### Adopted from *Good API Design*

Their public operation pages document no error format, status codes, pagination, rate limiting, versioning or idempotency. Those gaps are filled from the article, two of whose rules independently corroborate choices Tross already makes — plain API keys, and treating versioning as a last resort.

- **Never break userspace.** Documented fields are never removed; changes are additive.
- **Rate limiting with metadata.** `Retry-After` and `X-Limit-Remaining`. Not decorative — LinkedIn rate-limits *us*, so throttling protects the single session the service depends on.
- **Idempotency keys: deliberately absent.** The rule *explicitly exempts reads and deletes*. This endpoint is a read, so omitting the key is compliance with the rule rather than a deviation from it.
- **Cursor pagination: not applicable.** A single object is returned. Cursor pagination would be the design if a batch endpoint were added.

### Two decisions that were reversed mid-build

These are recorded because the reasoning is more useful than the outcome.

**A weighted rate limiter was designed, approved, and then withdrawn.** The reasoning had been that `input.sections` varies upstream cost, so the limiter should charge by weight rather than by request. Measurement then showed that one call returns every section — upstream cost is flat regardless of what is requested. The weighting was removed rather than shipped. A limiter modelling a cost that does not exist would be exactly the checklist-following the design set out to avoid.

**A credential-registration endpoint was proposed, then dropped.** `POST /api/integrations/linkedin/auth` is the conventional SaaS pattern for multi-tenancy. But Tross has no such route: no endpoint in their entire public API accepts a credential, and `auth_id` is documented only as *"Auth id"* with provisioning happening entirely out-of-band. Adding one would have been a deviation from their model, not an extension of it — and an API with no endpoint that accepts credentials has none that can leak them.

### On `auth_id`

Every Tross operation requires an `auth_id` whose provisioning is invisible from their public API. This service takes the same posture: `auth_id` is an opaque handle resolved server-side, and no route accepts a LinkedIn credential.

Here it resolves to a single operator-held session supplied through the environment — which is precisely what the brief specifies: *"You may use your own LinkedIn credentials in the backend."*

Multi-credential support would be a change to [`app/credentials.py`](app/credentials.py) alone; the wire contract does not move. It would additionally require `auth_id` in the cache key, since LinkedIn discloses different amounts of a profile depending on the viewing account and a shared cache would otherwise serve one session's data to another. It is deliberately not built — holding third-party session cookies demands encryption at rest and key management beyond this exercise's scope, and building that badly would be worse than scoping it out.

---

## Known limitations

**Data visibility is bounded by the backend account.** Every caller receives the *operator's* view of LinkedIn, not their own. Connection degree and the subject's privacy settings determine what is returned, so two callers requesting the same profile receive identical data regardless of their own networks.

**A missing profile is currently misreported.** LinkedIn returns `403` for a profile identifier that does not exist — the same status it uses for a rejected session — so such a request currently surfaces as `LINKEDIN_SESSION_EXPIRED` rather than `PROFILE_NOT_FOUND`. The two cases differ by scope rather than by status: a dead session fails every request, a missing profile fails only one. The fix is to probe the session before concluding it has expired.

**`/health` does not verify the session.** It returns `sessionValid: null`. A real upstream probe using the cheap top-card call is implemented in `fetch_top_card` but not yet wired in.

**Caching and rate limiting are specified but not implemented.** Both are designed; neither is in the request path yet. The cache matters most in practice — it is what prevents repeated interactive requests from exhausting a single session.

**`/docs` cannot send an authenticated request.** The API key is not declared as an OpenAPI security scheme, so Swagger's "Try it out" returns `401` unless the header is added manually.

**The decoration version will drift.** `FullProfileWithEntities-63` was verified on 2026-08-27. The suffix increments over time; adjacent versions (`60`–`67`) are probed and the working one remembered per process, but the range will eventually need widening.

**GraphQL persisted queries are not implemented.** LinkedIn's newer surface accepts only a query *name plus hash* (`queryId=voyagerPremiumDashFeatureAccess.c87b20da…`), never query text. Valid hashes must be harvested from observed traffic and are rotated by LinkedIn. Since the REST surface returns everything required, this path was documented rather than built.

**The session expires and must be replaced by hand.** This is the most operationally significant limitation.

`li_at` is issued with a fixed lifetime — decoding the token on this deployment suggested an issue/expiry pair roughly **21 days** apart, and the browser's cookie inspector shows the authoritative date. It **cannot renew itself**: LinkedIn reissues `bcookie` and `lidc` on API responses but never `li_at`, so using the service does not extend its credential. There is also **no credential-free fallback** — an unauthenticated request returns HTTP `999` behind an authwall with no usable content, so there is nothing to degrade to.

When it lapses, every request returns `LINKEDIN_SESSION_EXPIRED` with `retryable: false`, and `/health` reports `sessionValid: false` with a remedy. Recovery is a single environment-variable change requiring no redeploy — see [If the session expires](#if-the-session-expires).

Because a hosted demonstration is typically opened some days after it is handed over, the session should be re-minted immediately before deployment so that its full lifetime starts then rather than partway through.

**Single session, single point of failure.** If the backing account is restricted, every request returns `LINKEDIN_SESSION_EXPIRED`. The service degrades to a clear error rather than to partial or wrong data.

**Not built for volume.** No proxy rotation, no account pooling. Throughput is deliberately limited to what one session can sustain safely.

**Undocumented endpoints carry no contract.** There is no deprecation window and no changelog. Anything here may change without notice.

---

## Legal and ethical posture

Following *hiQ Labs v. LinkedIn*, accessing public profile data is not a criminal matter under the Computer Fraud and Abuse Act. It nonetheless **breaches LinkedIn's Terms of Service** as a contractual matter, and LinkedIn enforces that both technically and through litigation.

In *LinkedIn Corp. v. Nubela Pte. Ltd. / Proxycurl LLC* (N.D. Cal., filed January 2025), LinkedIn alleged the creation of hundreds of thousands of fake accounts to scrape millions of profiles including non-public data, resold through an API. The defendants settled, agreed to delete all data obtained, accepted a permanent injunction, and shut the service down in July 2025.

The conduct that drew that suit was **fake-account creation at industrial scale combined with commercial redistribution**. This project uses one genuine account belonging to its author, performs no automated account creation, resells no data, and is presented as a technical demonstration rather than a production service. That is a materially different posture — though still a Terms of Service violation, and stated here rather than glossed over.

### If the session expires

`/health` will show `sessionValid: false`. Recovery takes under a minute and needs no code change, no redeploy and no `git push`.

1. Sign in to LinkedIn in Chrome. If the session lapsed rather than being revoked, **sign out and back in** — that mints a fresh cookie with a full lifetime rather than inheriting the remainder of the old one.
2. **DevTools → Application → Cookies → `https://www.linkedin.com`**, copy the new `li_at` and `JSESSIONID` values. The `Expires / Max-Age` column shows exactly how long the new one lasts.
3. Update `LINKEDIN_LI_AT` and `LINKEDIN_JSESSIONID` in the host's environment settings and save. Most platforms restart the service automatically.
4. Confirm with `curl https://<host>/health` — `sessionValid` should read `true`.

Locally, update `.env` and run `uv run python -m scripts.mint_session` to verify.

---

## Project layout

Every module corresponds to one component in the architecture diagram, and nothing exists that is not on it.

```
app/
├── main.py           Entry point. One exception handler for every failure,
│                     requestId middleware, /health.
├── config.py         Settings from the environment. Never the repo.
├── errors.py         Error codes and typed exceptions → the error envelope.
├── schemas.py        The public contract as Pydantic models.
├── security.py       API gateway. X-API-Key; fails closed if unconfigured.
├── routes.py         fetch-profile handler. POST primary, GET alias.
├── credentials.py    Credential vault. auth_id → session; repr redacts.
└── voyager/
    ├── client.py     curl_cffi transport. Upstream status → typed errors.
    ├── endpoints.py  Voyager REST paths, decoration probing, URL parsing.
    └── resolver.py   Rest.li graph resolver. Pure function, no I/O.

scripts/              Development tools. Never imported by the application.
├── mint_session.py   Instructions for obtaining a session, then verifies it.
└── probe.py          Prints a raw Voyager payload; --save writes a fixture.

tests/                40 tests. Fully offline.
docs/                 approach.html, section-map.md, IMPLEMENTATION-PLAN.md
```

### Security properties

- **`.env` is gitignored and mode `600`.** `.env.example` carries empty placeholders. Repository history has been audited for leaked session values.
- **`LinkedInSession.__repr__` redacts both cookie values**, so a stray log line or traceback cannot leak the session.
- **No route accepts a credential.** The credential-theft attack surface is absent from the API rather than defended.
- **Fixture capture refuses to write** if a configured session value appears in the payload, because fixtures are committed.
- **Profile URLs travel in the request body** on the primary method, keeping personal data out of access logs and `Referer` headers.
- **The gateway fails closed.** A deployment with no `API_KEYS` configured refuses every request rather than running open.

---

## Testing

```bash
uv run pytest          # 40 tests
uv run pytest -v       # with names
```

**Every test is hermetic.** The single upstream network call is stubbed with a captured fixture; everything beneath it — the resolver, schema serialisation, error handling — runs for real. No credentials and no network are required, and running the suite never consumes the backend session's rate-limit budget.

Beyond the happy path, some tests exist to protect specific decisions:

| Test | What it guards |
| --- | --- |
| `test_broken_pointer_warns_and_still_returns_a_profile` | Corrupts a URN to a dangling reference. Asserts the section empties, a warning appears, and the request still returns `200`. |
| `test_resolver_is_pure_no_http_client_imported` | Greps the resolver's own source for `curl_cffi`, `requests`, `httpx`. Keeps the hardest component offline-testable permanently. |
| `test_partial_dates_render_without_a_fake_day` | Asserts date strings are 4, 7 or 10 characters, so no refactor invents precision. |
| `test_no_version_segment_in_any_route` | Enforces the no-`/v1/` decision. |
| `test_empty_payload_does_not_raise` | A hostile empty payload returns a profile with warnings, not a `500`. |
| `test_rejects_anything_that_is_not_a_profile` | Blocks lookalike hosts and non-profile paths. |

---

## Deployment

The service is a standard ASGI application with no persistent state and no browser dependency, so it runs anywhere Python does.

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Set `API_KEYS`, `LINKEDIN_LI_AT` and `LINKEDIN_JSESSIONID` in the host's environment configuration. They are never read from the repository.

> **Note on free hosting tiers.** Several free tiers idle instances after a period of inactivity, in which case the first request may take up to a minute while the instance wakes. Subsequent requests are fast.

---

## Acknowledgements

- Tross's public API documentation — [app.ontross.com/docs](https://app.ontross.com/docs)
- Sean Goedecke, [*Good API Design*](https://www.seangoedecke.com/good-api-design/)
- [`curl_cffi`](https://github.com/lexiforest/curl_cffi)
