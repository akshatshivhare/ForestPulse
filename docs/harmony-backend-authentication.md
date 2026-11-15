# Integrated Earthdata password authentication

**Later live execution:** Password authentication has now been used for one authorized real transformation. NASA completed that job; its retrieved COG failed the current extent validator (**INVALID**). Processing is false again and no further submission is authorized. [Actual first-test evidence](harmony-first-live-test.md). The history below predates that execution.

**Preparation follow-up, 15 November 2026:** Password mode has now been persisted in the local `.env` without changing credentials, and the first-scene public preflight refreshed. Processing remains false; no job or imagery download has occurred. [Current first-test readiness report](harmony-first-test-readiness.md). A running backend must reload the prepared setting before any later authorized experiment.

## Outcome and actual live evidence

**LIVE VERIFIED — 15 November 2026.** One read-only call through the actual backend `Transport.json`, using explicit **`earthdata_password`**, completed the trusted NASA login flow and returned HTTP **200** with a JSON jobs list. No processing worker was started. The jobs payload and user identity were discarded. [Sanitized machine-readable evidence](harmony-backend-password-auth.json).

UTC window: **`2026-11-15T06:14:56.480074+00:00` → `2026-11-15T06:15:00.903898+00:00`**, equivalent to **11:44:56–11:45:00 IST**. The network/session flow took **3.219 seconds**; the outer window also includes backend startup. The existing network was used; this was not an alternative-network comparison.

| Exchange | Public endpoint without OAuth parameter values | HTTP | Cumulative seconds |
| --- | --- | --- | --- |
| Initial read-only GET | `https://harmony.earthdata.nasa.gov/jobs?limit=1` | 303 | 0.640 |
| Earthdata authorization | `https://urs.earthdata.nasa.gov/oauth/authorize` | 302 | 1.922 |
| Harmony callback | `https://harmony.earthdata.nasa.gov/oauth2/redirect` | 307 | 2.547 |
| Authenticated jobs-list GET | `https://harmony.earthdata.nasa.gov/jobs?limit=1` | **200** | **3.219** |

**One logical attempt, four GETs, three redirects, zero retries.** Bearer token use: **false**. Cookie jar populated: **true**, memory only. Processing enabled: **false**. Submissions: **zero**. Satellite downloads: **zero**. No token, password, username, authorization header, cookie, OAuth code/state value or signed URL is in the evidence.

The live check command below was executed once. It selects password mode for that process; it does not edit `.env` or silently change the server's configured default. It invokes the same transport used by the API's processing manager, not the historical standalone probe:

```powershell
.venv\Scripts\python.exe -m scripts.verify_backend_password_auth --auth-mode earthdata_password
```

This command requires processing to be disabled and has a **30-second outer child-process deadline**. It does not poll or submit jobs, inspect other accounts, or download outputs. Re-running it would make a new live authentication attempt.

## Implemented

`Settings` accepts **`HARMONY_AUTH_MODE=earthdata_password`** or **`earthdata_token`**. Unknown values fail with a fixed message. The default remains `earthdata_token` for backward compatibility. Password mode requires both `EDL_USERNAME` and `EDL_PASSWORD`; it never falls back to a configured token. Token mode preserves the existing Bearer transport and its bounded status retries. Credentials are excluded from settings representations and never accepted from browser requests.

`backend/app/earthdata_session.py` ports the safeguards from the [verified password diagnostic](harmony-password-auth-test.md) into a reusable backend session. It uses the same official **Harmony-Py 1.8.0** call, `Client(auth=(username, password), token=None, should_validate_auth=False)`, and that client's authenticated session. Constructor validation is disabled to avoid a hidden extra request. Native SDK redirect authentication rebuilding and Requests cookie handling perform the actual login. This follows [NASA Harmony documentation](https://harmony.earthdata.nasa.gov/docs) and the [official SDK authentication implementation](https://github.com/nasa/harmony-py/blob/main/harmony/auth.py); no substitute password exchange, token creation or manual OAuth token exchange was added.

Login is bootstrapped only through **`/jobs?limit=1`**. Every authentication hop is checked before sending: HTTPS; exact production Harmony/Earthdata hosts; only jobs-list, authorization/login and callback paths; matching registered callback; authorization-code flow; matching OAuth state. Untrusted hosts, insecure redirects, mismatched state, loops and unexpected authentication methods are blocked. Each login permits at most **four redirects / five GETs**, **zero adapter retries**, **4-second connect / 6-second read timeouts**, a **20-second shared elapsed-time budget**, **64 KiB per login/redirect body** and a **64-cookie guard**. The elapsed budget is checked before sends and between body chunks; an in-flight socket read can run until its bounded timeout. Environment proxy/netrc substitution is disabled for password sessions. No credential file is read as a fallback or written.

One session is reused per transport and serialized with a nonblocking lock; concurrent access returns a sanitized busy error rather than racing the cookie jar. Cookies are kept only in memory. Sessions have a **900-second maximum reuse age**, checked on use; expired/error sessions are cleared and closed, and shutdown closes the transport. Cookies that expire earlier are respected by Requests. Credentials remain server-side in environment/settings, as required for later reauthentication.

Ordinary authenticated requests use cookies and suppress Basic headers. They do not follow OAuth redirects automatically. A safe jobs/status read can recover from a 401 or trusted login redirect with **at most one fresh read-only login and one replay**. A 403, malformed login, timeout or untrusted redirect stops safely. No credentials or raw remote error strings enter API errors. Read-only status errors retain bounded backoff; the one live verification used `retry=False`.

Transformation submission and cancellation GETs are classified as operations with side effects. They never automatically replay, even if a caller supplies the default retry flag. Their authentication is established first through the read-only jobs endpoint; an expiry response after sending the operation stops it for reconciliation. A supported job-ID redirect is parsed without following it as another operation.

Protected Harmony output retrieval reuses this session; approved signed S3 redirects use the existing **anonymous** downloader, with no EDL cookie or authorization header. Existing size/cache limits remain enforced. These download and processing paths were tested with mocks only. Async cancellation waits for bounded synchronous SDK I/O before closing the session or cleaning partial files, preventing a background writer from racing cleanup.

The processing manager now checks credentials for the selected method. Its provenance, queue, idempotency, retry/cancel architecture, candidate/AOI restrictions and second-scene gate are preserved. Capabilities add only the selected method and a Boolean for a currently verified password session; they expose no credentials or cookie values. The verification flag is process-local, false after a restart until successful authentication, and is not a claim about live COG readiness. Phase 1 CMR behavior, calendars, discovery and the dashboard layout are unchanged; the authentication setup text now covers either server method.

## Server setup and manual actions

Install the updated backend requirements or lock. Harmony-Py **1.8.0** and its dependencies are included in both. Set these names privately in the ignored server `.env` or environment, then restart the backend:

```dotenv
HARMONY_AUTH_MODE=earthdata_password
EDL_USERNAME=
EDL_PASSWORD=
HARMONY_PROCESSING_ENABLED=false
```

Blank credential values above are placeholders. The already configured credentials were used locally; their values are not shown. The authentication-integration task did not modify `.env`, the token or credential files; the later preparation task changed only the non-secret mode selector. The explicitly selected live-test mode did not change an already running server. `.env.example` retains the backward-compatible token default and documents both choices. Selecting `earthdata_token` uses `EARTHDATA_TOKEN` exclusively for Harmony. Never put any credentials in `VITE_` variables, frontend fields, URLs, exported reports or Git. No cookie file is needed.

## Validation and limits of the evidence

**MOCK TESTED:** The backend tests exercise explicit mode selection/no fallback, secret-safe settings and API output, cookie reuse, maximum session age, server expiry, one reauthentication limit, trusted/untrusted redirects and nested callbacks, OAuth state, redirect/body/deadline bounds, 401/403/503, connection/read/TLS failures, submission no-replay and job-ID redirect handling, concurrency, cancellation cleanup, protected output size limits and anonymous signed-S3 retrieval. The prior standalone diagnostic's **18 tests also passed**. Mock pixels and mock jobs are never live observations.

Final regression evidence:

| Check | Actual result |
| --- | --- |
| `.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider` | **116 passed, 1 opt-in public-metadata test skipped**, 4.54 seconds |
| Original SDK diagnostic unittest suites | **18 passed**, 0.110 seconds |
| `npm test` | **9 passed**, 2 files |
| `npm run build` | **Passed**, 1,974 modules, Vite build 10.47 seconds |

The build retains its large-chunk warning; backend tests retain the Starlette/httpx deprecation warning. The 28 new backend cases use fake credentials and mocked HTTP. No second live authentication request was made to test reuse or expiry; those behaviors are mock-tested only.

**BLOCKED / NOT LIVE VERIFIED:** Actual transformation submission, collection/application authorization for processing, async job completion, protected satellite output retrieval, real Rasterio metadata/pixels and two-scene alignment. The prior Bearer timeout cause and token acceptance remain unconfirmed. Password authentication success does not resolve those token-specific questions or establish scientific compatibility.

## Readiness checklist for one small Sundarbans COG test

- [x] Integrated password-session read-only authentication verified; no bearer fallback.
- [x] Server processing remains disabled; no processing or satellite download was performed.
- [x] Bounded cache, timeouts, idempotency and second-scene gate preserved; mocked regression checks pass.
- [x] Select `earthdata_password` in the actual backend configuration. Completed by the preparation follow-up; reload/restart any already running backend before its use.
- [x] Refresh the public dry-run/preflight for **G4405780437-ASF** (acquisition **2026-10-23**), collection **C3622241360-ASF**, variable **V4137651715-ASF** (`/science/LSAR/GCOV/grids/frequencyA/HHHH`) and proposed subset **[88.75, 21.85, 88.78, 21.88]**. Completed in the later preparation task; [fresh evidence and valid-pixel limitations](harmony-first-test-readiness.md). The pilot remains unchanged.
- [ ] Review the dry-run request, current service support, local job reconciliation and limits: **64 MiB/file, 256 MiB/cache, 1,200 seconds/job**, one concurrent job. Stop on unresolved prior submission.
- [ ] Obtain separate authorization for exactly one first-scene processing attempt; only then temporarily enable the processing flag. Do not enable it as a side effect of login.
- [ ] Record the actual remote job ID/timestamps, completion/error and Rasterio validation of CRS, extent, dimensions, resolution, dtype, nodata/masks, readable valid pixels and radar variable identity. Disable processing again afterward. Do not unlock scene two or infer disturbance before the first COG succeeds and later alignment/science checks are completed.

No forest-change classifier or measurements were added.
