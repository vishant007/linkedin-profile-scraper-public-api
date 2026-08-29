# LinkedIn Profile API — Phased Implementation Plan

## Context

The Tross hiring challenge asks for a publicly hosted API that takes a LinkedIn profile URL and returns the profile as structured JSON, obtained by reverse engineering LinkedIn's internal APIs. **Deadline is 31 August; today is 27 August.**

Research and design are complete and are recorded in `docs/approach.html`, `docs/intercept-lexicon.html` and the [Eraser flow diagram](https://app.eraser.io/workspace/ygRvBA4WKv02WtZ43bQc?diagram=e4AIISCHu09JqEOhePXJ&layout=canvas). **No code exists yet** — the repository has one commit, no remote, and only documentation.

The explicit goal of this plan is that implementation does not drift from that design. Section 1 freezes the decisions; every milestone carries a conformance check back to them.

**Stack: Python 3.12 + FastAPI, managed with `uv`.** Chosen because `curl_cffi` is Python-first and FastAPI generates live OpenAPI docs at `/docs` for free.

---

## 1. Anchors — frozen decisions

Do not revisit these mid-build. If one genuinely must change, update `docs/approach.html` and the Eraser diagram **first**, then the code.

### 1.1 The contract

```
POST /api/integrations/linkedin/fetch-profile
X-API-Key: <key>

{ "input": { "profileUrl": "...", "sections": ["experience","education",...] },
  "auth_id": "<uuid>" }
```

```jsonc
// 200
{ "profile": { ... }, "warnings": [ ... ], "fetchedAt": "<ISO 8601>" }

// error
{ "error": { "code": "...", "message": "...", "retryable": bool, "requestId": "..." } }
```

| Rule | Source |
|---|---|
| `POST` primary, documented `GET` alias | Tross uses POST for reads; GET keeps URLs out of logs |
| No `/v1/` version segment | No Tross path has one; Goedecke rule 4 |
| `X-API-Key` header | Tross convention; Goedecke rule 7 |
| `{input, auth_id}` request envelope | Tross convention, every operation |
| Response keyed by one domain noun (`profile`) — **no generic `data` wrapper** | `{patient…}`, `{claims:[…]}`, `{encounters:[…]}` |
| `warnings: []` for partial data | Tross `create-telephonic-encounter` |
| camelCase fields, ISO dates | Tross output convention |
| `X-Limit-Remaining` + `Retry-After` on 429 (flat — cost measured, see §1.4) | Goedecke rule 9 |
| `input.sections` — expensive fields opt-in | Goedecke rule 11 |
| **No** idempotency key, **no** pagination | Goedecke rule 8 **explicitly exempts reads**; pagination is inapplicable to a single object |

> **Do not add a credential-registration endpoint.** Tross has none — no route in their entire public API accepts a credential, and provisioning is out-of-band by design. A `POST …/auth` would be a deviation from their model, not an extension of it. `auth_id` stays an opaque handle resolved server-side.

### 1.2 Transport

- `curl_cffi` with `impersonate="chrome"`. **No headless browser at runtime, ever.**
- Four headers on every Voyager call: `cookie`, `csrf-token`, `accept: application/vnd.linkedin.normalized+json+2.1`, `x-restli-protocol-version: 2.0.0`.
- Voyager **REST** (`identity/dash/profiles` + `decorationId`) is primary; **GraphQL** persisted queries are fallback only.
- `li_at` lives in an environment variable. Never committed.

### 1.3 Diagram node → module map

This is the primary anti-drift device. **Every box in the Eraser diagram is exactly one module. No module exists that is not on the diagram.**

| Diagram node | Module |
|---|---|
| API Gateway | `app/security.py` (API key), `app/ratelimit.py` |
| fetch-profile Handler | `app/routes.py` |
| Profile Cache | `app/cache.py` |
| Credential Vault | `app/credentials.py` |
| HTTP Client (curl_cffi) | `app/voyager/client.py` |
| Voyager REST | `app/voyager/endpoints.py` |
| Voyager GraphQL (fallback) | `app/voyager/graphql.py` — **optional after Phase 0: document, don't build** |
| Rest.li Graph Resolver | `app/voyager/resolver.py` |
| Error path | `app/errors.py` |
| Session Minting (dev-time only) | `scripts/mint_session.py` — **not imported by the app** |
| — | `app/schemas.py` (Pydantic contract), `app/config.py` |

### 1.4 Compliance gaps to close

Audited against all twelve recommendations in Sean Goedecke's *Good API Design*: **7 of the 9 applicable rules are honoured by design, 3 do not apply, and 2 are open.** Both open items are tracked here and must be closed before submission.

| Gap | Rule | Status |
|---|---|---|
| **A — rate limits ignore request cost** | 9: *"tighter constraints for expensive operations"* | **Resolved by measurement** — cost is flat; see below |
| **B — product completeness unverified** | 5: *"success depends entirely on the product"* | **Closed by Phase 0** — every required field reachable |

> Both gaps closed 2026-08-27 by the Phase 0 spike — see `docs/section-map.md`.

**Gap A — resolved, but not as planned.** The original reasoning was that `input.sections` varies upstream cost, so the limiter should be weighted. **Phase 0 disproved the premise:** `FullProfileWithEntities-63` returns every section in a single call, so upstream cost is flat regardless of how many sections a caller requests.

The weighted bucket is therefore **withdrawn**. `input.sections` remains as a **response-shaping filter** (smaller payloads, caller control), and the README states plainly that per-section cost was measured and found flat, so weighting would model a cost that does not exist. Rule 9 is satisfied by a plain limit, honestly explained. *Measuring before optimising is the point; shipping a limiter that reflects nothing would be the checklist-following this design set out to avoid.*

**Gap B — closed favourably.** Every field the brief names is reachable from one endpoint. There is no unreachable-section limitation to declare.

Two framings worth carrying into the README, since they turn compliance into argument:

- **Rule 1 ("good APIs are boring") is the justification for mirroring Tross.** Familiarity to the reading audience is an applied design principle, not imitation.
- **Rule 6 is deliberately inverted.** Voyager is an awkward internal resource whose flat URN graph leaks LinkedIn's storage model; the resolver exists precisely so that awkwardness never reaches our callers.

---

## 2. Phases and milestones

### Phase 0 — Reachability spike *(do first; blocks schema design)*

**The one real risk.** The single verified call used `decorationId=…WebTopCardCore-6` and returned name, headline, location, and URN pointers to experience/education. The brief also requires **about, skills, certifications, languages and profile images**, none of which is confirmed reachable.

**M0.1** — Probe each required section from the logged-in browser session; record endpoint + `decorationId` + whether it works.

**Done when:** a table exists at `docs/section-map.md` with one row per required field: `field | endpoint | decorationId | status | notes`.

**Drift check:** any field marked unreachable goes straight into the approach doc's Known Limitations — never silently dropped from the schema.

**Why this is first (Gap B, Goedecke rule 5):** the article's point is that an API's success depends on the product behind it, not the interface. Here the product *is* data completeness. Verifying it before writing code is the difference between an honest limitations section and a nasty surprise on day three.

> Timebox: 45 minutes. If a section resists, mark it `unreachable` and move on — an honest limitation beats a missed deadline.

---

### Phase 1 — Skeleton and contract

**M1.1 Project scaffold** — `uv init`, Python 3.12, add `fastapi`, `uvicorn`, `curl_cffi`, `pydantic-settings`, `pytest`. Create `.gitignore` (covering `.env`, `.DS_Store`, `request.json`) and `.env.example` with **empty** placeholders.

**M1.2 The contract in code** — `app/schemas.py`: Pydantic models for the request envelope, `Profile`, `Warning`, `ErrorBody`. `app/errors.py`: exception classes → the error envelope, with a stable code enum (`LINKEDIN_SESSION_EXPIRED`, `PROFILE_NOT_FOUND`, `INVALID_PROFILE_URL`, `UPSTREAM_UNAVAILABLE`, `RATE_LIMITED`).

**M1.3 Endpoint stub** — `POST` route returning a hardcoded valid response; `GET` alias; `X-API-Key` dependency.

**Done when:** `uv run uvicorn app.main:app` serves `/docs`, and `curl` with a valid key returns a schema-valid stub; without a key returns the 401 error envelope.

**Drift check:** response JSON matches §1.1 byte-for-byte in shape. No `data` wrapper. No `/v1/`.

---

### Phase 2 — Voyager client

**M2.1 Credentials** — `app/config.py` + `app/credentials.py`: read `LINKEDIN_LI_AT` / `LINKEDIN_JSESSIONID` from env; `auth_id` resolves to a session. Single-session stub, but the interface takes an `auth_id`.

**M2.2 The client** — `app/voyager/client.py`: `curl_cffi` session with `impersonate="chrome"`, the four headers, `csrf-token` derived from `JSESSIONID`. Maps upstream 302→`LINKEDIN_SESSION_EXPIRED`, 404→`PROFILE_NOT_FOUND`, 429→`UPSTREAM_UNAVAILABLE`.

**M2.3 Endpoints + URL parsing** — `app/voyager/endpoints.py`: one function per section from the Phase 0 map. Extract `publicIdentifier` from any LinkedIn URL form; reject non-LinkedIn URLs with `INVALID_PROFILE_URL`.

**M2.4 Capture golden fixtures** — save real responses to `tests/fixtures/*.json` (scrubbed of session values). These make Phase 3 testable offline.

**Done when:** `uv run python -m scripts.probe <url>` prints raw Voyager JSON for a real profile, and fixtures are committed.

**Drift check:** no browser import anywhere in `app/`. Grep for `playwright|selenium` must return nothing.

---

### Phase 3 — The graph resolver *(the core deliverable)*

This is the substantive engineering. Build it **test-first** against the Phase 2 fixtures — it is a pure function, no network needed.

**M3.1 URN index** — build `{entityUrn: object}` from `included[]`.

**M3.2 Pointer resolution** — walk `*`-prefixed keys, resolve single URNs and URN lists, handle missing targets gracefully (→ a warning, not an exception). Guard against reference cycles.

**M3.3 Section mappers** — one small pure function per section (`map_experience`, `map_education`, `map_skills`, …) turning resolved Rest.li objects into the clean schema.

**M3.4 Assembly** — compose into `Profile`, collecting a `SECTION_UNAVAILABLE` warning for anything absent. Unknown upstream fields pass through rather than being dropped (Goedecke rule 2).

**Done when:** `uv run pytest` is green, including a test asserting that a fixture with a deliberately broken URN yields a warning and a **200**, not a 500.

**Drift check:** resolver is pure — it imports no HTTP client. Partial data produces warnings, never failures.

---

### Phase 4 — Wire it up

**M4.1** Route calls credentials → client → resolver; `input.sections` controls which upstream calls fire (default: core set only).
**M4.2** `requestId` generated per request, echoed in errors and logged. Logs never contain `li_at`.
**M4.3** Populate `fetchedAt`.

**Done when:** a real end-to-end `curl` against a live LinkedIn profile returns the full contract.

**Drift check:** requesting fewer sections demonstrably makes fewer upstream calls.

---

### Phase 5 — Hardening

**M5.1 Cache** — `app/cache.py`: in-memory TTL keyed by `(publicIdentifier, sections)`. Protects the single session as much as it speeds responses.
**M5.2 Rate limit** — `app/ratelimit.py`: **flat** inbound cap per API key → 429 + `Retry-After` + `X-Limit-Remaining`; outbound throttle so LinkedIn is never hammered.

Deliberately *not* weighted by section count — Phase 0 measured upstream cost as flat (one call regardless of sections requested), so weighting would model a cost that does not exist. Record that measurement in the README; the reasoning is the point, not the mechanism.
**M5.3 Health** — `GET /health` reporting whether the LinkedIn session is still valid, so a reviewer can self-diagnose a dead session.

**Done when:** exceeding the limit returns 429 with both headers; a repeat request is served from cache.

**Drift check:** all three boxes exist on the diagram. Nothing added that isn't on it.

---

### Phase 6 — Deploy

> **Render or Railway, not Fly.io** — Docker and `flyctl` are not installed locally, and both alternatives build straight from a connected GitHub repo with automatic HTTPS.

**M6.1** *(human)* `gh auth login`, then create the **public** repo and push.
**M6.2** *(human)* Connect the repo on Render; set env vars in their dashboard.
**M6.3** Verify the public HTTPS URL end-to-end from outside the machine.

**Done when:** a `curl` from anywhere against the public `https://…` URL returns a real profile.

**Drift check:** `git log -p | grep -i "li_at\|AQEDA"` returns nothing. Requirement 7 is pass/fail.

---

### Phase 7 — README and submission

**M7.1 README** — the four required sections: **setup instructions**, **API documentation**, **approach**, **known limitations**. Approach and limitations are largely transcribable from `docs/approach.html`.
**M7.2** Add the legal/ethical posture section (post-*hiQ*; the Proxycurl outcome; one real account, no resale, no fake accounts).
**M7.3** Link the Eraser diagram and commit the design docs.
**M7.4** *(human)* Submit at `https://tally.so/r/KYK6qg`.

**Done when:** every box in §3 is ticked.

---

## 3. Requirement traceability

Check this table before submitting — it is the actual grading sheet.

| # | Requirement | Satisfied by |
|---|---|---|
| 1 | Deploy publicly over HTTPS | Phase 6 |
| 2 | Accept a LinkedIn profile URL as input | M1.2, M2.3 |
| 3 | Return name, headline, location, about, experience, education, skills, certifications, languages, profile images | Phase 0 map → Phase 3; gaps documented in M7.1 |
| 4 | May use own LinkedIn credentials in backend | M2.1 |
| 5 | Public GitHub repo with complete source | M6.1 |
| 6 | README: setup, API docs, approach, limitations | M7.1 |
| 7 | Keep credentials and secrets out of the repository | M1.1 + M6.3 drift check |

Plus the two Goedecke gaps from §1.4: **Gap A** closed by M5.2, **Gap B** closed by Phase 0.

---

## 4. Schedule

| Day | Phases |
|---|---|
| **27 Aug** (today) | 0, 1 |
| **28 Aug** | 2, 3 |
| **29 Aug** | 4, 5 |
| **30 Aug** | 6, 7 |
| **31 Aug** | Buffer + submit |

Phase 3 is the long pole; Phase 6 has the most external dependencies. If time runs short, cut `input.sections` granularity and the GraphQL fallback — **never** the resolver, the README, or the deploy.

## 5. Steps only you can do

1. `gh auth login` (M6.1)
2. Copy `li_at` from DevTools → Application → Cookies (M2.1)
3. Create the Render account and set env vars (M6.2)
4. Submit the Tally form (M7.4)

---

## 6. Verification

**Per phase:** `uv run pytest` green, plus each milestone's "Done when".

**End-to-end, against the deployed URL:**

```bash
curl -X POST https://<host>/api/integrations/linkedin/fetch-profile \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"input":{"profileUrl":"https://www.linkedin.com/in/thevishantshah/"},
       "auth_id":"<uuid>"}'
```

Confirm: `profile` populated · `warnings` present and honest · `fetchedAt` set · no `data` wrapper · repeat call hits cache · bad key → 401 envelope · over-limit → 429 with `Retry-After` and `X-Limit-Remaining` · `/docs` renders · `/health` reports session state.

**Anti-drift audit before submitting:**
- Every module in §1.3 exists; nothing extra that isn't on the diagram
- `grep -ri "playwright\|selenium\|puppeteer" app/` → empty
- Response shape matches §1.1 exactly
- `git log -p | grep -i "li_at\|AQEDA"` → empty

---

## First action on approval

Write this plan to **`docs/IMPLEMENTATION-PLAN.md`** (plan mode currently prevents writing outside this file), then begin Phase 0.
