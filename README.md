# LinkedIn Profile API

Takes a LinkedIn profile URL, returns the profile as structured JSON. The data comes from LinkedIn's **internal Voyager API**, not from scraping the rendered page.

Returns name, headline, location, about, experience, education, skills, certifications, languages and profile images — in **one upstream call**.

---

## Try it live

The service is deployed and running. Nothing to install.

**Base URL** — `https://tross-assignment-ihro.onrender.com`

```bash
curl -X POST https://tross-assignment-ihro.onrender.com/api/integrations/linkedin/fetch-profile \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input":{"profileUrl":"https://www.linkedin.com/in/thevishantshah/"}}'
```

Swap the URL for any LinkedIn profile. The API key is supplied alongside this repository; it is not committed here, because an API key is a credential.

```jsonc
// what comes back
{ "profile":   { "publicIdentifier": "thevishantshah",
                 "firstName": "Vishant", "lastName": "Shah",
                 "headline": "AI Software Engineer@Flytbase",
                 "location": {…}, "about": "…", "profilePicture": {…},
                 "experience": [ …4 roles… ], "education": [ … ],
                 "skills": [ …20… ], "certifications": [ …10… ],
                 "languages": [] },
  "warnings":  [ { "code": "SECTION_UNAVAILABLE", "section": "languages", … } ],
  "fetchedAt": "2026-08-30T09:14:22Z" }
```

### Browse it in the browser

| | |
| --- | --- |
| **[`/docs`](https://tross-assignment-ihro.onrender.com/docs)** | Interactive documentation, generated from the schema. Expand `POST /fetch-profile`, hit **Try it out**, edit the profile URL and **Execute** against the live service. Add the `X-API-Key` header when prompted. |
| **[`/redoc`](https://tross-assignment-ihro.onrender.com/redoc)** | The same content laid out for reading rather than for calling. Better for scanning the response schema top to bottom. |
| **[`/openapi.json`](https://tross-assignment-ihro.onrender.com/openapi.json)** | The machine-readable spec both pages are generated from. |
| **[`/health`](https://tross-assignment-ihro.onrender.com/health)** | Liveness and whether the backend LinkedIn session is still valid. No key needed. |
| **[`/`](https://tross-assignment-ihro.onrender.com/)** | Landing page listing the operations. |

**Finding the schema:** on `/docs`, scroll to **Schemas** at the foot of the page and expand `Profile`. Every model is there with its field types — `Experience`, `Education`, `Certification`, `Language`, `Location`, `ProfilePicture`, `ProfileWarning` and the `ErrorBody` envelope. Nothing in that page is hand-written; it is generated from the Pydantic models the service validates against, so it cannot drift from the code.

### Or in Postman

Import [`postman/LinkedIn-Profile-API.postman_collection.json`](postman/LinkedIn-Profile-API.postman_collection.json), open the collection's **Variables** tab, paste the key into `apiKey`, and send. Six requests covering the happy path, section filtering, the `GET` alias and three error cases. Each carries assertions, so the Test Results tab shows whether the response contract, the error envelope and the security headers are all correct.

> First request after a quiet period may take up to a minute while the free instance wakes. Everything after that is fast.

---

## Setup — running it yourself

To run your own instance. Needs Python 3.12+ and [`uv`](https://docs.astral.sh/uv/):

```bash
uv sync && cp .env.example .env       # then fill in the three values below
uv run python -m scripts.mint_session # verifies the LinkedIn session is live
uv run uvicorn app.main:app --port 8000
```

| Variable | Description |
| --- | --- |
| `API_KEYS` | Comma-separated keys callers present in `X-API-Key`. |
| `LINKEDIN_LI_AT` | LinkedIn session cookie. Chrome → DevTools → Application → Cookies. |
| `LINKEDIN_JSESSIONID` | Source of the `csrf-token` header, like `"ajax:1234567890"`. |

`li_at` is `HttpOnly` — page JavaScript cannot read it, which is why this step is manual. Treat it like a password. Optional: `CACHE_TTL_SECONDS` (default 21600), `RATE_LIMIT_PER_MINUTE` (default 30).

**Deploy** — no browser, no persistent state, so any Python host works. Build `pip install .`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, health `/health`. Secrets go in the host's environment; [`render.yaml`](render.yaml) declares them `sync: false` so they are never committed.

**If the session expires** — `/health` reports `sessionValid: false` and names the fix. Sign out and back in on LinkedIn, copy the two cookies, update them in the host's environment. No redeploy, no code change.

---

## API documentation

`POST /api/integrations/linkedin/fetch-profile` · `X-API-Key` header · no version segment in any path.

```jsonc
// request
{ "input": { "profileUrl": "…", "sections": ["experience","skills"] } }

// 200
{ "profile":   { "publicIdentifier": "…", "firstName": "…", "headline": "…",
                 "location": {…}, "about": "…", "profilePicture": {…},
                 "experience": […], "education": […], "skills": […],
                 "certifications": […], "languages": [] },
  "warnings":  [ { "code": "SECTION_UNAVAILABLE", "section": "languages",
                   "message": "…" } ],
  "fetchedAt": "2026-08-30T09:14:22Z" }

// any failure, including validation
{ "error": { "code": "LINKEDIN_SESSION_EXPIRED", "message": "…",
             "retryable": false, "requestId": "req_40f0…" } }
```

`sections` is optional and defaults to all five. It shapes the response but does not reduce upstream work, because LinkedIn returns the whole profile in one call. That was measured, not assumed.

**Dates keep the precision LinkedIn gave** — `"2025"`, `"2025-07"` or `"2025-07-14"`. Padding to a full date would invent precision the source never had.

| Errors | HTTP | Retryable |
| --- | --- | --- |
| `INVALID_API_KEY` | 401 | no |
| `INVALID_REQUEST` | 422 | no |
| `INVALID_PROFILE_URL` | 400 | no |
| `PROFILE_NOT_FOUND` | 404 | no |
| `LINKEDIN_SESSION_EXPIRED` | 502 | no — a human must renew it |
| `UPSTREAM_UNAVAILABLE` | 502 | yes |
| `RATE_LIMITED` | 429 | yes — carries `Retry-After` |
| `INTERNAL_ERROR` | 500 | yes |

`retryable` is explicit so callers need not infer retry behaviour from a status code.

**Also:** `GET` alias on the same path with query parameters. `GET /health` reports liveness and session validity, no key needed. `GET /` serves a landing page to browsers, JSON to clients. Response headers carry `X-Cache`, `X-Limit-Remaining` and `X-Request-Id`.

`profileUrl` accepts ten URL forms including bare identifiers, regional subdomains and `/details/…` suffixes, and rejects lookalike hosts such as `linkedin.com.evil.example`.

---

## Approach

### One call, not many

The profile is assembled from ten separate sections — identity, about, location, image, experience, education, skills, certifications, languages. **All of them arrive in a single request.**

That is the central engineering result. The obvious implementation issues one call per section, or falls back to fetching and parsing the rendered page when a section resists. Either way the cost is roughly one upstream request per section, per profile, and each is a separate parser that breaks on its own schedule.

Finding one endpoint that returns the entire graph collapses that to a single request and a single resolver. On a service whose whole risk is one account being rate-limited or flagged, request count per profile is the variable that matters most — a sevenfold reduction in upstream traffic is not an optimisation, it is the difference between a demo that survives review and one that does not. It also removes nine parsers and nine failure modes.

The rest of this section is how that endpoint was found and what had to be done with what it returns.

### Finding the data

A LinkedIn profile page arrives as an empty shell. Its JavaScript then calls an internal API — Voyager, under `/voyager/api/` — which returns typed JSON that the page paints into HTML. **The structured data exists before anything renders.** Voyager is undocumented; you find it by opening DevTools and reading what the page requests of itself.

Six candidate endpoints, probed directly:

| | |
| --- | --- |
| `identity/profiles/{id}/profileView` | **410 Gone** — retired, and what most published guides still target |
| `identity/dash/profiles` + `WebTopCardCore-6` | 200, 12 kB — identity only |
| **`identity/dash/profiles` + `FullProfileWithEntities-63`** | **200, 114 kB — the whole profile** |
| `profileCards` / `profileComponents` variants | 404 |

One call, every field. The decoration carries a version suffix LinkedIn increments, so the client probes adjacent versions and remembers which answers.

Two cookies authenticate it, and each of four headers was verified by removing it: no `cookie` → `302 /login`; no `csrf-token` → `403`; no `accept: …normalized+json+2.1` → `200` but a nested shape instead of the flat graph; no `x-restli-protocol-version` → `400`.

### Rebuilding the response

Voyager speaks Rest.li. It returns a **flat bag of ~90 objects referencing each other by URN** — nothing is nested, and a person's jobs are not inside the person.

```jsonc
{ "data": { "*elements": ["urn:li:fsd_profile:ACoAA…"] },      // a pointer, not a person
  "included": [
    { "$type": "…profile.Profile", "firstName": "Vishant",
      "*profilePositionGroups": "urn:li:fsd_…" },              // an address
    { "$type": "…CollectionResponse", "*elements": ["urn:li:fsd_position:…"] }
  ] }
```

A key beginning `*` holds an address. Resolution takes **two hops** — the pointer names a collection, the collection names the items — and a single-hop implementation silently returns nothing. Experience nests one level further, since roles at one company are grouped. Images are not URLs but a `rootUrl` plus artifact segments.

Reassembling that graph is the substantive work, in [`app/voyager/resolver.py`](app/voyager/resolver.py). It is a **pure function** with no network calls, so one captured response was enough to build and verify the whole component offline.

### No browser

Headless browsers exist to run JavaScript. Voyager returns JSON, so there is nothing to render. The only thing a browser would add is looking like a real client — and detection starts at the **TLS handshake**, before a single header is read. A default Python client's JA3 fingerprint says "Python", and setting a browser `User-Agent` does not change that.

[`curl_cffi`](https://github.com/lexiforest/curl_cffi) replays Chrome's actual TLS and HTTP/2 handshake from an ordinary HTTP client: **~50 MB instead of ~1 GB**, instant cold start, no session lifecycle to manage. No browser is imported anywhere in `app/`.

### Contract

`POST` is the primary method with a documented `GET` alias. A profile URL in a query string lands in access logs, browser history and `Referer` headers; a body keeps it out. The alias exists because `GET` is what people reach for first.

Arguments are wrapped in `input` so the envelope has room to grow without disturbing them, and the response is keyed by one domain noun — `{"profile": …}` — rather than a generic `data` wrapper, so a reader can tell what they asked for from the response alone.

No path carries a version segment. Fields are added, never removed or retyped, so callers written today keep working.

### Decisions worth naming

**`warnings`, not failures.** LinkedIn discloses different amounts of a profile depending on who is looking. A section it will not show returns a warning alongside a `200`, never an error. The brief asks for these fields *"when available"*; this is what that means.

**Two things were measured, then the design changed.** A rate limiter weighted by requested sections was designed and withdrawn once measurement showed upstream cost is flat. `sections` survives as response shaping with its rationale corrected rather than quietly kept.

**The cache protects the session, not just latency.** Six-hour TTL, LRU-bounded. Ten requests for one profile become one call to LinkedIn — which matters when every request rides a single account.

**Honest timestamps.** A cached response keeps its original `fetchedAt`; `/health` reports when its probe last ran, not when the reply was written. A cached answer must not claim to be fresh.

**`/health` always returns 200.** An expired credential is an operator task, not a crashed process. A `503` would make a platform health check restart a container with nothing wrong with it.

### Security

Failed authentication is logged as a SHA-256 fingerprint, never the key — credential stuffing is visible only in the pattern of rejections. The gateway **fails closed**: no keys configured means every request is refused, not that the service runs open. No route accepts a credential, so the credential-theft surface is absent rather than defended. `Strict-Transport-Security` and `X-Content-Type-Options` on every response including errors. Profile URLs travel in the body, keeping personal data out of access logs and `Referer` headers. Input validation uses a host **allowlist**, not a denylist.

---

## Known limitations

**The session expires and must be replaced by hand.** `li_at` cannot renew itself — LinkedIn reissues `bcookie` and `lidc` on API responses but never `li_at`. There is no credential-free fallback either: an unauthenticated request returns HTTP `999` behind an authwall with nothing usable. Both were tested. Recovery is one environment variable.

**A missing profile is misreported.** LinkedIn returns `403` both for a profile that does not exist and for a rejected session, so a mistyped identifier currently surfaces as `LINKEDIN_SESSION_EXPIRED`. They differ by scope — a dead session fails every request, a missing profile fails one — so the fix is to probe the session before concluding it expired. **This is the one open bug.**

**Every caller sees the operator's view of LinkedIn, not their own.** Visibility depends on the backing account's network, so two callers requesting the same profile get identical data.

**One credential, single point of failure.** Supporting several would mean a request field naming which to use, resolution in `credentials.py`, and the caller identity in the cache key — a breaking change, plus encryption at rest for third-party cookies.

**The decoration version drifts.** `FullProfileWithEntities-63` was verified 2026-08-27. Adjacent versions are probed, but the range will eventually need widening.

**GraphQL persisted queries are not implemented.** LinkedIn's newer surface accepts only a query name plus a hash, which must be harvested from live traffic and which LinkedIn rotates. REST returns everything needed, so this was documented rather than built.

**API keys alone, no OAuth.** A long-lived key keeps the API reachable to anyone who can send an HTTP request. OAuth would mean running an authorisation server and a token lifecycle for a single read endpoint, which is more machinery than this needs.

**Not built for volume.** No proxy rotation, no account pooling. Undocumented endpoints carry no contract, no deprecation window and no changelog.

**Legal position.** After *hiQ Labs v. LinkedIn*, accessing public profile data is not a CFAA matter, but it does breach LinkedIn's Terms of Service, and LinkedIn litigates — in *LinkedIn v. Nubela/Proxycurl* (N.D. Cal. 2025) the defendants settled, deleted the data and shut down after allegedly creating hundreds of thousands of fake accounts. This uses one genuine account belonging to its author, creates no accounts, resells no data, and is a technical demonstration.
