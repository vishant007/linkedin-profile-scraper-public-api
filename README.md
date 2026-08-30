# LinkedIn Profile API

Accepts a LinkedIn profile URL and returns the profile as structured JSON, sourced from LinkedIn's internal Voyager API.

Request and response shapes mirror the conventions published at [app.ontross.com/docs](https://app.ontross.com/docs).

```bash
curl -X POST https://tross-assignment-ihro.onrender.com/api/integrations/linkedin/fetch-profile \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input":{"profileUrl":"https://www.linkedin.com/in/thevishantshah/"},
       "auth_id":"b3f1c2e4-8a90-4d21-9f77-2ce1d0a4b512"}'
```

- [Setup](#setup)
- [API documentation](#api-documentation)
- [Approach](#approach)
- [Known limitations](#known-limitations)

---

## Setup

### Try it without installing anything

The API runs at `https://tross-assignment-ihro.onrender.com`. Use the `curl` above with the key supplied alongside this repository, or open [`/docs`](https://tross-assignment-ihro.onrender.com/docs) for an interactive browser generated from the schema.

A Postman collection is at [`postman/LinkedIn-Profile-API.postman_collection.json`](postman/LinkedIn-Profile-API.postman_collection.json). Import it, open the collection's **Variables** tab, paste your key into `apiKey`, and send. Seven requests are included, covering the happy path, section filtering, the `GET` alias, and three error cases. Each carries assertions, so the Test Results tab reports whether the response contract, error envelope and security headers are all correct.

The `apiKey` variable ships empty. This project keeps credentials out of version control, and an API key is a credential.

### Run it yourself

Requires Python 3.12+ and [`uv`](https://docs.astral.sh/uv/). `uv` provisions the interpreter, so the system Python version does not matter.

```bash
git clone <repo-url> && cd tross-assignment
uv sync
cp .env.example .env
```

| Variable | Required | Description |
| --- | --- | --- |
| `API_KEYS` | yes | Comma-separated keys that callers present in `X-API-Key`. |
| `AUTH_ID` | yes | The opaque handle callers pass. Bound to the keys above. |
| `LINKEDIN_LI_AT` | yes | The backend LinkedIn session cookie. |
| `LINKEDIN_JSESSIONID` | yes | Source of the `csrf-token` header. Looks like `"ajax:1234567890123456789"`; surrounding quotes are stripped for you. |
| `CACHE_TTL_SECONDS` | no | Default `21600`, six hours. `0` disables caching. |
| `RATE_LIMIT_PER_MINUTE` | no | Default `30`. `0` disables rate limiting. |

**Obtaining the two cookies:** sign in to LinkedIn in Chrome, then **DevTools → Application → Cookies → `https://www.linkedin.com`** and copy the `li_at` and `JSESSIONID` values.

`li_at` is `HttpOnly`, so page JavaScript cannot read it. That is a LinkedIn defence against session theft, and it is why this step is manual. Treat the value like a password: it grants full account access without needing one. Revoke it at any time with **LinkedIn → Settings → Sign out of all sessions**.

```bash
uv run python -m scripts.mint_session   # confirms the session is live
uv run pytest                           # 74 tests, no network, no credentials
uv run uvicorn app.main:app --port 8000
```

Then open `http://127.0.0.1:8000/docs`.

### Deploy

A standard ASGI application with no persistent state and no browser dependency, so it runs anywhere Python does.

```
Build:  pip install --upgrade pip && pip install .
Start:  uvicorn app.main:app --host 0.0.0.0 --port $PORT
Health: /health
```

Set `API_KEYS`, `AUTH_ID`, `LINKEDIN_LI_AT` and `LINKEDIN_JSESSIONID` in the host's environment configuration. They are never read from the repository. A [`render.yaml`](render.yaml) blueprint is included; it declares the secrets with `sync: false` so they are entered in the dashboard rather than committed.

### If the session expires

`/health` reports `sessionValid: false`. Recovery needs no code change, no redeploy and no `git push`.

1. Sign in to LinkedIn in Chrome. If the session lapsed rather than being revoked, sign out and back in, which mints a cookie with a full lifetime rather than the remainder of the old one.
2. **DevTools → Application → Cookies → `https://www.linkedin.com`**, copy the new `li_at` and `JSESSIONID`. The `Expires / Max-Age` column shows how long the new one lasts.
3. Update the two variables in the host's environment settings and save. Most platforms restart automatically.
4. Confirm with `curl https://<host>/health`.

Locally, update `.env` and run `uv run python -m scripts.mint_session`.

---

## API documentation

**Base path:** `/api/integrations/linkedin`
**Authentication:** `X-API-Key: <key>` on every request.

No path carries a version segment.

### `POST /api/integrations/linkedin/fetch-profile`

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
| `input.sections` | string[] | no | Which optional sections to include. Defaults to all five. |
| `auth_id` | string | yes | Opaque handle to a stored LinkedIn session. Never a credential. |

Valid `sections` values: `experience`, `education`, `skills`, `certifications`, `languages`. Core identity fields, meaning name, headline, location, about and profile image, are always returned.

`sections` shapes the response and does not reduce upstream work. LinkedIn returns the entire profile in a single call, so requesting fewer sections produces a smaller response for the same upstream cost. This was measured rather than assumed.

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

**Dates keep their original precision.** LinkedIn frequently supplies only a year, or a year and month. Values render at whatever precision arrived, so `"2025"`, `"2025-07"` and `"2025-07-14"` are all valid. Padding to a full ISO date would fabricate precision the source never gave.

**Response headers**

| Header | Meaning |
| --- | --- |
| `X-Cache` | `HIT` or `MISS`. A cached response keeps its original `fetchedAt` rather than claiming to be freshly fetched. |
| `X-Limit-Remaining` | Requests left in the current window for this key. |
| `X-Request-Id` | Present on every response, including errors. Quote it when reporting a problem. |

### `GET /api/integrations/linkedin/fetch-profile`

A convenience alias taking `profileUrl`, `auth_id` and repeated `sections` as query parameters. Returns the identical contract.

```bash
curl -G https://tross-assignment-ihro.onrender.com/api/integrations/linkedin/fetch-profile \
  -H "X-API-Key: $API_KEY" \
  --data-urlencode "profileUrl=https://www.linkedin.com/in/thevishantshah/" \
  --data-urlencode "auth_id=b3f1c2e4-8a90-4d21-9f77-2ce1d0a4b512"
```

POST is the primary method. Query parameters land in access logs, browser history and `Referer` headers, so POST is preferable for anything handling personal data.

### `GET /health`

Liveness, plus whether the backend LinkedIn session is usable. Requires no API key.

```json
{ "status": "ok", "sessionValid": true, "checkedAt": "2026-08-30T11:47:43.007587Z" }
```

When the session has expired it says so, and says what to do:

```json
{
  "status": "degraded",
  "sessionValid": false,
  "checkedAt": "2026-09-03T11:47:43.007587Z",
  "detail": "The backend LinkedIn session is no longer valid and must be renewed.",
  "remedy": "Renew LINKEDIN_LI_AT and LINKEDIN_JSESSIONID in the environment. See the README section 'If the session expires'."
}
```

It always returns `200`. The service is running either way, and an expired credential is an operator task rather than a crashed process. Returning `503` would cause a platform health check to restart a container with nothing wrong with it.

The probe calls `/voyager/api/me`, about 2.8 kB against roughly 12 kB for the smallest profile projection, and asks the right question directly: is this session still me. The result is cached for 60 seconds, so uptime monitors and repeated refreshes cannot themselves become the traffic that gets the session flagged. `checkedAt` reports when the probe last ran, not when the reply was written.

### `GET /`

Serves a landing page to browsers and a JSON index of links to API clients, selected by the `Accept` header.

### Rate limiting

A token bucket per API key, refilling continuously, defaulting to 30 requests per minute. Bursts up to the full allowance are permitted, which suits interactive exploration better than a hard window.

Exceeding it returns `429` with `Retry-After` in seconds and `X-Limit-Remaining: 0`.

The limit is flat rather than weighted by requested sections, because upstream cost does not vary with them.

### Caching

Successful responses are cached for six hours, keyed on the handle, the profile identifier and the requested sections. The cache is bounded and evicts least-recently-used entries.

It exists mainly to protect the upstream session. Ten requests for the same profile become one call to LinkedIn.

### Warnings

A warning means the request succeeded and there is something the caller should know. Warnings never accompany a non-2xx response.

| Code | Meaning |
| --- | --- |
| `SECTION_UNAVAILABLE` | A requested section returned nothing. The profile may not list any, or the backend session may not be permitted to see it. |
| `UNRESOLVED_REFERENCE` | An object referenced by the upstream payload was not present in it. That section is empty; the rest of the profile is unaffected. |

This exists because the brief asks for fields "when available", and because LinkedIn discloses different amounts of a profile depending on the viewer's relationship to it. A section that is not visible is a normal condition, not a failure.

### Errors

Every failure, including request validation, returns the same envelope.

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
| `FORBIDDEN_AUTH_ID` | 403 | no | The `auth_id` is not available to this API key. |
| `PROFILE_NOT_FOUND` | 404 | no | LinkedIn has no profile at that identifier. |
| `LINKEDIN_SESSION_EXPIRED` | 502 | no | The backend session died. Retrying cannot help; a human must renew it. |
| `UPSTREAM_UNAVAILABLE` | 502 | yes | LinkedIn was unreachable or returned something unusable. |
| `RATE_LIMITED` | 429 | yes | Caller exceeded their allowance. Carries `Retry-After`. |
| `INTERNAL_ERROR` | 500 | yes | Unexpected. Quote `requestId` when reporting. |

`retryable` is explicit so callers need not infer retry behaviour from a status code.

An unknown `auth_id` and one belonging to another key return the identical error, so responses cannot be used to enumerate which handles exist.

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

## Approach

A fuller write-up with evidence is in [`docs/approach.html`](docs/approach.html), and the endpoint survey is in [`docs/section-map.md`](docs/section-map.md).

### The page is not the product

Loading `linkedin.com/in/<slug>` does not deliver a finished page. The browser receives a mostly-empty shell whose JavaScript then requests the profile data separately, receives typed JSON, and paints it into HTML.

The structured data therefore already exists upstream of anything visible. Those requests go to paths under `/voyager/api/`, Voyager being LinkedIn's internal API, the one their own front end uses. It is undocumented and unsupported; its existence is known only because its traffic is observable.

This matters because the brief asks for LinkedIn's APIs to be reverse engineered rather than for a page to be scraped. Those produce very different systems.

> **Not to be confused with LinkedIn's official Developer API.** That one is documented, partner-gated and OAuth-authenticated, and it cannot return an arbitrary person's profile at all, only the authenticated user's own or those of people who explicitly authorise the calling application.

### Discovery

Endpoints were found by observation: open a profile in a logged-in browser, filter the network inspector on `/voyager/`, and read what the page requests of its own accord. One page load produced six such calls; most are presence polling, notification counts and telemetry.

Six candidate endpoints were then probed directly:

| Candidate | Result |
| --- | --- |
| `/voyager/api/identity/profiles/{id}/profileView` | `410 Gone`, retired |
| `identity/dash/profiles` + `WebTopCardCore-6` | `200`, 12 kB, identity fields only |
| `identity/dash/profiles` + `FullProfileWithEntities-63` | `200`, 114 kB, the entire profile |
| `identity/dash/profileCards?q=deferredCards` | `404` |
| `…/profileCards?…&sectionType=skills` | `404` |
| `…/profileComponents?q=entitiesByProfileAndSection` | `404` |

One call returns everything the brief asks for. There is no per-section fan-out.

The decoration carries a version suffix that LinkedIn increments over time, so the client probes a small range of adjacent versions and remembers whichever answers.

### Authentication

Two cookies, defending two different things:

- `li_at` is the session. Without it, LinkedIn responds `302 → /login`.
- `JSESSIONID` supplies the `csrf-token` header. Without it, LinkedIn responds `403` even with a valid session, because the session cookie alone cannot prove the request came from a real LinkedIn page rather than another site riding the user's cookies.

Two further headers are required, and each was verified by removing it:

| Header | Removed | Effect |
| --- | --- | --- |
| `cookie` | | `302 → /login` |
| `csrf-token` | | `403` |
| `accept: application/vnd.linkedin.normalized+json+2.1` | | `200`, but a nested shape instead of the flat graph |
| `x-restli-protocol-version: 2.0.0` | | `400`, parameters parsed under the older grammar |

The `accept` header is the subtle one: it produces the flattened `included[]` representation the resolver is built around.

### The response format is the real work

Voyager speaks Rest.li, LinkedIn's own RPC framework. Responses are a flat array of typed objects that reference one another by URN:

```jsonc
{
  "data": { "*elements": ["urn:li:fsd_profile:ACoAADF3cUc…"] },   // a pointer, not a person
  "included": [
    { "$type": "…identity.profile.Profile",
      "firstName": "Vishant",
      "*profilePositionGroups": "urn:li:fsd_…",                   // an address
      "*profileEducations":     "urn:li:fsd_…" },
    { "$type": "…common.CollectionResponse", "*elements": ["urn:li:fsd_position:…"] }
    // … 90 more, all siblings
  ]
}
```

A field name beginning `*` holds an address, not a value. A person's jobs are not inside the person.

A real capture contained 92 objects: 20 `Skill`, 12 `Company`, 10 `Certification`, 4 `Position`, 4 `PositionGroup`, 4 `Geo`, plus `Education`, `School`, `Profile` and others.

Reassembling that into one nested document is what [`app/voyager/resolver.py`](app/voyager/resolver.py) does. Three details are worth naming:

1. **Resolution takes two hops.** A pointer names a `CollectionResponse`; that collection's `*elements` then names the items.
2. **Experience nests one level further.** `*profilePositionGroups` yields `PositionGroup` records referencing their own `Position` records, because several roles at one company are grouped.
3. **Images are not URLs.** `profilePicture` holds a `vectorImage` with a `rootUrl` and a list of artifacts; a usable URL is the concatenation.

The resolver is a pure function over a payload, with no network calls of its own, so a captured response serves as a fixture and the whole component is developed and tested offline.

### Transport

Headless browsers exist to execute JavaScript and build a page. Voyager returns JSON, so there is nothing to render. The only thing a browser would contribute is request realism, and there is a smaller tool for that.

Bot detection begins at the TLS handshake, before a single header is parsed. The cipher suites a client offers, their order and the extension set form a pattern hashed into a JA3 fingerprint. A default Python HTTP client produces a JA3 that identifies it as Python, and setting a browser `User-Agent` does not conceal that.

[`curl_cffi`](https://github.com/lexiforest/curl_cffi) is a binding over a patched libcurl that reproduces a real browser's TLS and HTTP/2 handshake:

```python
from curl_cffi import requests
r = requests.get(url, headers=HEADERS, impersonate="chrome")
```

| | Headless browser | `curl_cffi` |
| --- | --- | --- |
| Memory | ~1 GB resident | ~50 MB |
| Cold start | seconds | instant |
| Extra code | session lifecycle, crash recovery | none |
| Detection surface | TLS, plus `navigator.webdriver`, GPU stack, client hints | TLS and HTTP/2, matched to Chrome |

No browser appears anywhere in `app/`, and a test asserts it.

### Contract design

The response schema was ours to design. Rather than invent conventions, it follows Tross's own, verified across five documented operations (`tn/fetch-patient-info`, `tn/fetch-clinician-details`, `ecw/create-telephonic-encounter`, `ecw/fetch-appointments`, `availity/fetch-claims`), and fills their documented gaps from Sean Goedecke's [*Good API Design*](https://www.seangoedecke.com/good-api-design/).

Goedecke's opening principle is that good APIs are boring: familiar enough to understand before reading the documentation. Mirroring an existing house style is that principle applied.

| Convention | Evidence |
| --- | --- |
| `POST` for every operation, reads included | All five documented operations are POST, including three `fetch-*` |
| `/api/integrations/{vendor}/{verb-noun}` | kebab-case, verb first |
| No version segment | No Tross path carries one |
| `X-API-Key` header | Identical across all five |
| `{ "input": {…}, "auth_id": "…" }` request envelope | Identical across all five |
| Response keyed by one domain noun, no generic `data` wrapper | `{patient, patient_statistics}`, `{encounters: […]}`, `{claims: […]}`, `{clinician: {…}}` |
| `warnings` array | `create-telephonic-encounter` returns `{encounterId, created, warnings}` |
| camelCase response fields, ISO dates | Their output convention throughout |

Two details are deliberate. `auth_id` keeps its snake_case name beside otherwise camelCase fields, because that is what Tross does. And their inputs are inconsistently named across integrations while their outputs never are, implying a philosophy of normalising what you return and mirroring what you receive.

Their operation pages document no error format, status codes, pagination, rate limiting, versioning or idempotency. Those gaps are filled from the article, two of whose rules independently corroborate choices Tross already makes: plain API keys, and treating versioning as a last resort.

Idempotency keys are absent because the article explicitly exempts reads and deletes; this endpoint is a read, so omitting the key follows the rule rather than departs from it. Cursor pagination does not apply to a single returned object.

### On `auth_id`

Every Tross operation requires an `auth_id` whose provisioning is invisible from their public API. No route in their documentation accepts a credential.

This service takes the same posture. `auth_id` is an opaque handle resolved server-side, no route accepts a LinkedIn credential, and the handle is checked against the API key presenting it. Authentication proves who is calling; without that second check nothing would prove the handle is theirs to use.

Here it resolves to a single operator-held session supplied through the environment, which is what the brief specifies: "You may use your own LinkedIn credentials in the backend."

### Security properties

- `.env` is gitignored. Repository history has been audited for leaked session values.
- `LinkedInSession.__repr__` redacts both cookie values, so a stray log line or traceback cannot leak the session.
- Failed authentication is logged with a SHA-256 fingerprint of the presented key rather than the key itself. Credential stuffing is visible only in the pattern of rejections.
- No route accepts a credential, so the credential-theft attack surface is absent rather than defended.
- `Strict-Transport-Security` and `X-Content-Type-Options` are set on every response, including errors.
- Profile URLs travel in the request body on the primary method, keeping personal data out of access logs and `Referer` headers.
- The gateway fails closed: a deployment with no `API_KEYS` configured refuses every request rather than running open.
- Input validation uses a host allowlist rather than a denylist, with a length-bounded identifier.

### Project layout

```
app/
├── main.py           Entry point. One exception handler for every failure,
│                     requestId middleware, security headers, /health, /.
├── config.py         Settings from the environment.
├── errors.py         Error codes and typed exceptions.
├── schemas.py        The public contract as Pydantic models.
├── security.py       API key validation. Fails closed.
├── ratelimit.py      Token bucket per key.
├── cache.py          TTL cache, LRU bounded, keyed on auth_id.
├── routes.py         fetch-profile handler. POST primary, GET alias.
├── credentials.py    auth_id to session, with an ownership check.
└── voyager/
    ├── client.py     curl_cffi transport. Upstream status to typed errors.
    ├── endpoints.py  Voyager paths, decoration probing, URL parsing.
    └── resolver.py   Rest.li graph resolver. Pure function, no I/O.

scripts/              Development tools. Never imported by the application.
tests/                74 tests. Fully offline.
docs/                 approach.html, section-map.md
postman/              Importable collection with assertions
```

### Testing

```bash
uv run pytest
```

Every test is hermetic. The single upstream network call is stubbed with a captured fixture; the resolver, schema serialisation and error handling all run for real. No credentials and no network are required, and running the suite never consumes the session's rate-limit budget.

Some tests exist to protect specific decisions:

| Test | What it guards |
| --- | --- |
| `test_broken_pointer_warns_and_still_returns_a_profile` | Corrupts a URN to a dangling reference. The section empties, a warning appears, the request still returns `200`. |
| `test_resolver_is_pure_no_http_client_imported` | Greps the resolver's own source for HTTP clients, keeping it offline-testable. |
| `test_partial_dates_render_without_a_fake_day` | Date strings are 4, 7 or 10 characters, so no refactor invents precision. |
| `test_health_checked_at_reflects_the_probe_not_the_reply` | A cached health answer cannot claim to be freshly verified. |
| `test_key_separates_auth_ids` | Cache entries never cross handles. |
| `test_unknown_auth_id_is_forbidden` | The ownership check holds. |
| `test_tracked_keys_are_bounded` | Cycling API keys cannot grow the limiter without limit. |

---

## Known limitations

**The session expires and must be replaced by hand.** `li_at` is issued with a fixed lifetime, and the browser's cookie inspector shows the date. It cannot renew itself: LinkedIn reissues `bcookie` and `lidc` on API responses but never `li_at`, so using the service does not extend its credential. There is also no credential-free fallback, because an unauthenticated request returns HTTP `999` behind an authwall with no usable content. When it lapses, every request returns `LINKEDIN_SESSION_EXPIRED` and `/health` reports the remedy. Recovery is a single environment-variable change.

**Every caller receives the operator's view of LinkedIn, not their own.** Visibility depends on the backing account's relationship to the subject, so two callers requesting the same profile receive identical data regardless of their own networks.

**A missing profile is misreported.** LinkedIn returns `403` for a profile identifier that does not exist, the same status it uses for a rejected session, so such a request currently surfaces as `LINKEDIN_SESSION_EXPIRED` rather than `PROFILE_NOT_FOUND`. The two differ by scope: a dead session fails every request, a missing profile fails only one. The fix is to probe the session before concluding it has expired.

**Single session, single point of failure.** If the backing account is restricted, every request returns a clear error rather than partial or wrong data.

**One credential, not many.** `auth_id` resolves to a single operator-held session. The interface takes an opaque identifier, so multi-credential support would be a change to `credentials.py` alone plus adding the handle to the cache key, since LinkedIn discloses different amounts of a profile per viewing account and a shared cache would otherwise serve one session's data to another. Storing third-party session cookies demands encryption at rest and key management, which is outside this exercise.

**The decoration version drifts.** `FullProfileWithEntities-63` was verified on 2026-08-27. The suffix increments over time; adjacent versions are probed and the working one remembered per process, but the range will eventually need widening.

**GraphQL persisted queries are not implemented.** LinkedIn's newer surface accepts only a query name plus a hash, never query text. Valid hashes must be harvested from observed traffic and are rotated by LinkedIn. The REST surface returns everything required, so this path was documented rather than built.

**Authentication is API keys alone.** Common guidance recommends pairing keys with OAuth 2.0. Tross uses a bare `X-API-Key` header on every documented operation, Goedecke argues long-lived keys keep an API reachable to people who are not full-time engineers, and OAuth would require an authorisation server and token lifecycle for a single read endpoint.

**Not built for volume.** No proxy rotation, no account pooling. Throughput is limited to what one session can sustain safely.

**Undocumented endpoints carry no contract.** There is no deprecation window and no changelog. Anything here may change without notice.

**Legal position.** Following *hiQ Labs v. LinkedIn*, accessing public profile data is not a criminal matter under the Computer Fraud and Abuse Act. It nonetheless breaches LinkedIn's Terms of Service as a contractual matter, and LinkedIn enforces that both technically and through litigation. In *LinkedIn Corp. v. Nubela Pte. Ltd. / Proxycurl LLC* (N.D. Cal., filed January 2025), LinkedIn alleged the creation of hundreds of thousands of fake accounts to scrape millions of profiles including non-public data, resold through an API; the defendants settled, deleted the data, accepted a permanent injunction and shut down in July 2025. This project uses one genuine account belonging to its author, creates no accounts, resells no data, and is a technical demonstration rather than a production service.
