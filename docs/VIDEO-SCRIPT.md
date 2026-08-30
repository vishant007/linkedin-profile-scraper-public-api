# Video walkthrough script

A 3 to 4 minute explanation of how the service fetches LinkedIn profile data and how it runs publicly, presented against the flow diagram.

**Diagram:** https://app.eraser.io/workspace/ygRvBA4WKv02WtZ43bQc?diagram=e4AIISCHu09JqEOhePXJ&layout=canvas
**Length:** roughly 3:40 at a normal speaking pace

---

## Before recording

Four labels on the diagram are out of date. Fix at least the first one, since the script says the cache is built.

| Node | Change |
|---|---|
| Profile Cache (PLANNED) | Remove "(PLANNED)", restore the solid style. Lines: `6h TTL, LRU bounded`, `key includes auth_id`, `X-Cache: HIT \| MISS`. Set both its arrows back to solid. |
| Voyager GraphQL (PLANNED) | Rename to `Voyager GraphQL — NOT BUILT`. Last line: `rejected, not deferred`. Keep it dashed. |
| Credential Vault | Add a line: `verifies the key owns the handle (403)` |
| API Gateway | Lines: `validates X-API-Key — fails closed`, `HSTS + nosniff on every response`, `rate limiting — PLANNED` |

---

## Script

*Stage directions in italics.*

### 0:00 to 0:20 — what it does

> This service takes a LinkedIn profile URL and returns that profile as structured JSON. Name, headline, location, about, experience, education, skills, certifications, languages, and profile images.
>
> I'll walk through where that data actually comes from, and then how the whole thing runs publicly over HTTPS.

### 0:20 to 0:55 — where the data comes from

*Point at Zone 3, the LinkedIn side.*

> When you open a LinkedIn profile, the browser receives a mostly empty page. The JavaScript on that page then calls an internal LinkedIn API to fetch the profile data, and paints it into the HTML you see.
>
> That internal API is called Voyager. It sits under `/voyager/api/`. LinkedIn has never documented it, so I found it the only way you can: open DevTools, load a profile, and read the requests the page makes on its own.
>
> The important consequence is that the data already exists as clean JSON before the page renders anything. So I don't parse HTML. I ask for the JSON directly.

### 0:55 to 1:25 — the endpoint

*Point at Voyager REST.*

> The endpoint I use is `identity/dash/profiles`, with a parameter called a decoration ID that selects how much of the profile comes back.
>
> With the full profile decoration, one request returns 114 kilobytes and 92 objects. That covers every field in the brief. There is no per-section fan-out and no second call.
>
> That decoration ID carries a version number, and LinkedIn increments it over time. So the client probes a small range of adjacent versions on the first call and remembers whichever one answers.

### 1:25 to 1:50 — authentication

*Point at Credential Vault.*

> Voyager only answers an authenticated request. Two cookies do that work.
>
> `li_at` is the session itself. Without it LinkedIn redirects to the login page. `JSESSIONID` supplies a CSRF token that has to be echoed back in a header, and without that LinkedIn returns 403 even when the session is valid.
>
> Both live in environment variables and never go near the repository. Callers never see them. They send an API key and an opaque handle, and the service resolves that handle to the session on its own side.

### 1:50 to 2:40 — rebuilding the response

*Point at Rest.li Graph Resolver.*

> This is where most of the work is.
>
> Voyager doesn't return a document. It returns a flat list of about ninety objects that point at each other by ID. Nothing is nested. A person's jobs are not inside the person.
>
> A field name starting with an asterisk holds an address rather than a value. And following one takes two steps, because the pointer names a collection and the collection then names the items.
>
> Experience goes one level deeper again. Several roles at the same company are grouped, so a position group holds positions, and the resolver flattens that.
>
> This part is a pure function. It takes the payload and returns a profile, with no network calls of its own. So I captured one real response as a fixture and built and tested the whole thing offline against it, without touching LinkedIn again.

### 2:40 to 3:05 — no browser

*Point at HTTP Client.*

> There's no browser anywhere in this service.
>
> A headless browser exists to run JavaScript and build a page. Voyager returns JSON, so there's nothing to render. The only thing a browser would add is looking like a real client to LinkedIn.
>
> That part matters, but it happens lower down than most people expect. LinkedIn can tell what software you are from the TLS handshake, before it reads a single header. So I use `curl_cffi`, which replays Chrome's actual TLS fingerprint from a normal HTTP client. That costs about 50 megabytes of memory instead of a gigabyte, and it starts instantly.

### 3:05 to 3:35 — running it publicly

*Point at Zone 2, then Zone 1.*

> Because there's no browser, the whole service is a small Python process. It runs on Render's free tier in 512 megabytes, built with plain `pip install` and started with one uvicorn command. Render terminates TLS, so it's HTTPS from the outside.
>
> The four secrets go into Render's environment settings, not the repository. Deploys happen on push to main.
>
> In front of that, the gateway checks an API key and refuses every request if none is configured. There's a cache with a six hour lifetime, which is mostly there to protect the session: ten people asking for the same profile is one call to LinkedIn, not ten.
>
> And FastAPI generates interactive documentation from the schema, so `/docs` on the live URL is a working API browser.

### 3:35 to 3:50 — how it degrades

*Point at Health Probe and the error path.*

> Two things worth mentioning about failure.
>
> LinkedIn shows different amounts of a profile depending on who is looking. So a section the account can't see comes back as a warning alongside a 200, rather than failing the request. The brief asks for these fields "when available", and that's what that means.
>
> And if the session expires, `/health` says so directly. It reports `sessionValid: false` and names the environment variable to renew, so anyone hitting the API can tell a stale credential from a broken service.
>
> That's the whole system.

---

## Numbers, in case you're asked

| | |
|---|---|
| Upstream calls per profile | 1 |
| Response size | 114,694 bytes, 92 objects |
| Fields returned | all 10 the brief lists |
| Tests | 67, none of which touch the network |
| Memory | around 50 MB |
| Cache | 6 hours, LRU bounded, keyed on the handle |
| Health probe | `/voyager/api/me`, 2.8 kB, cached for 60 seconds |

## What I'd do next

Rate limiting comes first. Then fixing a real bug: LinkedIn returns 403 both for a profile that doesn't exist and for a dead session, and right now the service reports the second for both. After that, supporting more than one credential, which is a storage change behind the same interface plus adding the handle to the cache key.
