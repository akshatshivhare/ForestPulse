# Explicit username/password authentication test

**Backend integration update, 15 November 2026:** The verified SDK approach is now integrated behind an explicit server authentication selector and passed its own read-only HTTP 200 check in **3.219 seconds**. [Current implementation, evidence and readiness checklist](harmony-backend-authentication.md). The standalone diagnostic and its historical evidence below are retained. Processing remains disabled; no job or satellite download has been performed.

## Completed trusted-redirect test — VERIFIED

**15 November 2026, 11:32:07–11:32:11 IST** (`2026-11-15T06:02:07.228389+00:00` through `2026-11-15T06:02:11.166027+00:00`). One logical, read-only authentication attempt completed successfully using **EDL_USERNAME / EDL_PASSWORD**, Harmony-Py **1.8.0**, and its native authenticated session and redirect handling. **EARTHDATA_TOKEN was not used.** The authenticated jobs-list response was HTTP **200** with a JSON `jobs` list. Its contents and user identity were not retained. Measured SDK flow duration: **3.797 seconds**. See [sanitized live evidence](harmony-password-redirect-test.json).

The first HTTP 303 destination was the documented **`https://urs.earthdata.nasa.gov/oauth/authorize`** endpoint. Its parameters were checked in memory for authorization-code flow, a nonempty client identifier, and the exact HTTPS Harmony callback. The callback's state was checked against the authorization request. Parameter values, authorization codes, state, cookies and full redirect URLs were not recorded.

| Actual step | Public origin and path only | HTTP | Cumulative seconds | Trusted destination |
| --- | --- | --- | --- | --- |
| Initial jobs-list GET | `https://harmony.earthdata.nasa.gov/jobs` | 303 | 1.188 | Earthdata `/oauth/authorize` |
| Earthdata authorization | `https://urs.earthdata.nasa.gov/oauth/authorize` | 302 | 2.500 | Harmony `/oauth2/redirect` |
| Harmony OAuth callback | `https://harmony.earthdata.nasa.gov/oauth2/redirect` | 307 | 3.360 | Harmony `/jobs` |
| Authenticated jobs-list GET | `https://harmony.earthdata.nasa.gov/jobs` | **200** | **3.797** | Complete |

The initial and final jobs-list requests use `limit=1`. All four exchanges were GET requests in **one** login attempt, with **three redirects and zero retries**. No processing, cancellation, download or other job-control path was permitted. Processing was **false before and after**; no job was submitted. This ran on the existing network; no alternative-network comparison is claimed. Password authentication succeeded there, so the earlier timeout does not establish a general inability to reach Harmony. Bearer-token acceptance and the cause of its earlier timeouts remain unconfirmed.

### Official flow and safety limits

[NASA Harmony documentation](https://harmony.earthdata.nasa.gov/docs), the [Earthdata SSO overview](https://urs.earthdata.nasa.gov/documentation/for_users/sso_process_overview), the [official Harmony EDL application guide](https://github.com/nasa/harmony/blob/main/docs/edl-application.md), and [Harmony-Py's authentication source](https://github.com/nasa/harmony-py/blob/main/harmony/auth.py) describe the supported password/session and OAuth redirect flow. The installed 1.8.0 SDK implementation was also inspected. This diagnostic uses `Client(auth=(username, password), token=None, should_validate_auth=False)` and the client's authenticated session; disabling constructor validation prevents a hidden additional request. Requests follows redirects through Harmony-Py's native `rebuild_auth` implementation.

The diagnostic adds a guard before every network send: HTTPS only, exact production Harmony/Earthdata hosts and authentication/jobs paths, GET only, Basic-only prepared authentication, a maximum of **four redirects / five GETs**, a **20-second shared flow budget**, **4-second connect / 6-second read limits**, a **25-second outer process deadline**, **64 KiB per response body**, and a **64-cookie jar limit**. Unexpected destinations, nested callback destinations, mismatched OAuth state, loops and processing paths are blocked before they can receive credentials. SDK redirect handling removes the Basic header when returning from Earthdata to Harmony. Environment proxies and netrc substitution are disabled for this diagnostic.

The SDK's session cookie jar was populated and preserved **in memory throughout the login flow**, enabling the final authenticated request. Cookies were cleared and the session closed at completion; no credential/cookie file was created or modified. No credentials, headers, signed URLs, OAuth parameter values or response payloads were logged or written to evidence. The existing token implementation, runtime configuration and selected AOI remain unchanged.

### Implementation, regression tests and next action

**IMPLEMENTED:** Separate bounded diagnostic in `scripts/harmony_password_redirect_flow.py`, invoked through `scripts/test_harmony_password_flow.py`. The prior single-request diagnostic remains unchanged. Re-running the command below makes a new live login attempt; it was run **once** for this evidence:

```powershell
.venv\Scripts\python.exe -m scripts.test_harmony_password_flow --auth-method username-password
```

**TESTED WITH MOCKS:** **18 SDK diagnostic tests passed**, covering the prior single-request mode plus the trusted multi-hop flow, cookie preservation, credential stripping, token exclusion, rejection, timeouts, forbidden destinations, callback/state checks, loops, redirect limits, shared deadline and processing-disabled enforcement:

```powershell
artifacts\harmony-auth-env\Scripts\python.exe -m unittest scripts.test_password_redirect_unit scripts.test_password_probe_unit -q
```

The existing backend regression suite passed: **88 passed, 1 opt-in network test skipped**, in **3.67 seconds**, with the existing Starlette/httpx deprecation warning. The initial restricted Windows run stalled and was stopped; the completed run used the permissions previously needed by the offline suite. It did not perform another live authentication attempt.

```powershell
.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider
```

**LIVE VERIFIED:** Read-only Harmony access with explicit username/password and an authenticated session. This resolves the earlier 303-only uncertainty for this method.

**Historical readiness assessment at this diagnostic:** The username/password authentication prerequisite was satisfied, while the application transport was still Bearer-only. That integration gate has since been completed in the [backend integration](harmony-backend-authentication.md). Processing still requires separate authorization and validation; no processing job, output raster or scientific result has been verified.

## Historical single-request test — redirect not followed

Test date: **15 November 2026**. Recorded UTC window: `2026-11-15T05:51:26.093932+00:00` to `2026-11-15T05:51:28.495802+00:00` (11:21:26–11:21:28 IST).

**Result: authentication unconfirmed; HTTP 303 redirect, not a timeout.** The single read-only request did not establish success or return an explicit 401/403 rejection. A complete Earthdata redirect/cookie login flow would require additional HTTP exchanges; none was attempted under this one-request test.

## Selected method and isolation

The selected mode was explicitly **username/password**, sourced from the locally configured `EDL_USERNAME` and `EDL_PASSWORD`. The new test does not read `EARTHDATA_TOKEN` or fall back to it. It uses the officially supported Harmony-Py `Client(auth=(username, password), token=None, should_validate_auth=False)` branch and its authenticated session. An adapter checks that the prepared request uses Basic authentication and blocks any other method before network access. No header value or credential is exported.

The [official Harmony-Py authentication implementation](https://github.com/nasa/harmony-py/blob/main/harmony/auth.py) supports the explicit username/password tuple. [NASA Harmony documentation](https://harmony.earthdata.nasa.gov/docs) describes Earthdata username/password authentication and its redirect/cookie flow. Constructor validation is disabled so that it cannot make an extra hidden request; the one actual jobs-list GET is the test.

This is a separate diagnostic mode. Existing token authentication code, application behavior, dependencies, `.env`, credential files and the selected Sundarbans AOI were not changed. No netrc/password fallback was used. `session.trust_env=False` prevents environment proxy/netrc substitution for the explicit authentication choice.

## Actual request and result

| Field | Actual result |
| --- | --- |
| Endpoint category | Read-only production Harmony jobs list |
| Method/path | `GET https://harmony.earthdata.nasa.gov/jobs?limit=1` |
| Client | Harmony-Py 1.8.0 in the existing isolated SDK environment |
| Authentication method | Explicit username/password; token argument None |
| Token used | False |
| HTTP status | **303** |
| Measured probe duration | **2.25 seconds**, including client setup |
| Requests sent | **1** |
| Automatic retries | **0** |
| Redirects followed | **0** |
| Authentication confirmed | **No** |
| Processing enabled before/after | **False / False** |
| Processing submitted | **No** |

Connect/read limits were 4/6 seconds, with a 15-second outer subprocess deadline and a 64 KiB response-body limit. Only the single HTTPS GET to the exact production jobs-list path was allowed. No transformation or job-control endpoint was allowed. Redirect location, cookies, response bodies, usernames, passwords and authentication headers were not retained. See [sanitized JSON evidence](harmony-password-auth-test.json).

The 303 is a different symptom from the previously recorded Bearer response-header timeouts. It does not prove that the username/password is correct or incorrect, and does not demonstrate a complete authenticated session. Any future complete-flow test should separately bound and allowlist trusted Earthdata/Harmony redirects; this test did not add those exchanges.

## Explicit test command

```powershell
.venv\Scripts\python.exe -m scripts.test_harmony_password_auth --auth-method username-password
```

The method flag is required. Missing password/username blocks the request instead of using a token. Processing must remain disabled. The command stores only sanitized evidence; no credential file is created or modified.

## Regression checks

Six SDK-environment unit tests passed using fake credentials and mocked HTTP responses. They check explicit tuple selection even when a token is present, Basic-only prepared authentication, one-request/zero-retry behavior, 401 handling, read timeouts, non-followed redirects, processing-disabled enforcement, and prevention of token fallback when a password is missing.

```powershell
artifacts\harmony-auth-env\Scripts\python.exe -m unittest scripts.test_password_probe_unit -v
```

The existing backend regression suite also passed: **88 passed, 1 opt-in network test skipped**, with the existing Starlette/httpx deprecation warning. No test result is represented as successful live authentication.
