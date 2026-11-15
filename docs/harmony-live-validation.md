# Harmony live validation — authentication endpoint timeout

Check date: **15 November 2026**, Asia/Calcutta.

**Latest backend integration, 11:44:56–11:45:00 IST: VERIFIED.** The actual backend transport, explicitly selecting `earthdata_password`, returned authenticated jobs-list HTTP 200 after three trusted NASA redirects in **3.219 seconds**. [Integration report and remaining processing checklist](harmony-backend-authentication.md); [sanitized evidence](harmony-backend-password-auth.json). No bearer was used. Processing stayed disabled, no job was submitted, and no satellite data was downloaded. Earlier timeout and standalone-probe records below are retained as history; token acceptance remains unconfirmed.

**Latest username/password flow, 11:32:07–11:32:11 IST: VERIFIED.** One bounded read-only Harmony-Py login followed three trusted NASA redirects (303 → 302 → 307 → **200**) and received an authenticated jobs list in **3.797 seconds**. Explicit EDL username/password was used; no token was used. Session cookies stayed in memory and were cleared after the test. Processing stayed false and no job was submitted. [Completed-flow details](harmony-password-auth-test.md) and [sanitized live evidence](harmony-password-redirect-test.json). Earlier Bearer timeout evidence below remains historical; token acceptance is still unconfirmed, and the unchanged application transport remains Bearer-only.

**Explicit username/password test, 11:21:26–11:21:28 IST:** One read-only Harmony GET using Harmony-Py 1.8.0's explicit username/password mode returned **HTTP 303** in **2.25 seconds**. No token, retry or redirect-following was used; processing stayed false. Authentication is **unconfirmed**, because a 303 response is not a completed login or an explicit credential rejection. [Password-mode details](harmony-password-auth-test.md) and [sanitized evidence](harmony-password-auth-test.json) are separate from the unchanged token implementation and earlier token diagnostics.

Latest detailed diagnostic: **00:49:22–00:49:39 IST**, equivalent to `2026-11-14T19:19:22.691556Z` through `2026-11-14T19:19:39.179962Z`. [Sanitized DNS/TLS/HTTP/SDK evidence](harmony-auth-diagnostics.json) is the current diagnostic record. The earlier single-test attempt below is retained as history; it never submitted processing.

**Independent Earthdata follow-up, 15 November 2026, 01:08:28–01:08:30 IST:** The official scoped user-profile API returned **HTTP 401**, not a timeout, in **1.422 seconds**. [Sanitized evidence](earthdata-auth-independent.json) records no profile or private UID. The token was not accepted for that scoped API; global user-token validity and Harmony authentication remain **unconfirmed**. The user confirmed that the computer is still on the **original network**, so no alternative-network request has been performed or claimed. See the follow-up assessment at the end of this document.

**BLOCKED: the token is now present locally, but authenticated NASA access could not be verified because requests timed out.** This supersedes the earlier missing-token check. No real processing request was submitted and live processing was not enabled. Phase 1 and application runtime code were not modified.

The recorded main attempt ran at **00:28:55–00:30:29 IST on 15 November 2026**, corresponding to `2026-11-14T18:58:55.282721Z` through `2026-11-14T19:00:29.385268Z`. See [redacted machine-readable evidence](harmony-live-validation.json) for exact timestamps and the later read-only access diagnostic. A separate Phase 2 live-validation runner records gated first-scene attempts without exporting credentials or signed asset URLs.

## Configuration inspected

Read `docs/harmony-integration.md`, the existing backend configuration, `.env.example` and `scripts/verify_harmony.py`. Loaded the effective backend settings without printing the token or inspecting its value in output.

| Check | Actual local result |
| --- | --- |
| Project-root `.env` exists | Yes |
| Nonempty `EARTHDATA_TOKEN` configured | Yes; value not exposed |
| `HARMONY_PROCESSING_ENABLED` | False |
| Maximum output file size | 64 MiB |
| Maximum cache size | 256 MiB |
| Job deadline | 1,200 seconds |
| Cache retention | 86,400 seconds |
| Maximum retained job records | 50 |

Authentication verification was attempted using the existing transport's bounded retries against the documented read-only `GET /jobs?limit=1` endpoint. It timed out. The gated validation runner also stopped at that authenticated precheck. No transformation, processing-job polling or output retrieval was attempted.

A final synchronous comparison returned **HTTP 303** for unauthenticated jobs access and **ReadTimeout** for authenticated jobs access. Separately, the public collection-capabilities endpoint returned **HTTP 200 JSON**. Thus public Harmony metadata is reachable, while authenticated access remains unverified. These results do not prove that the token is invalid, expired or unauthorized.

The evidence's `backend_http_status: 502` is the local sanitized error mapping (`harmony_unavailable`) after timeout; it is **not an observed HTTP 502 response from NASA**. User identity, credentials, redirect URLs and signed URLs were not exported. There were no existing tracked local jobs, and the recorded number of transformation submission attempts is **zero**.

Full current granule/variable/subset preflight was not repeated after the authentication stop condition. Earlier public preflight evidence remains in `docs/harmony-verification.json` and is not presented as fresh authenticated request acceptance.

## Intended first test — not executed

- Candidate: `G4405780437-ASF`, acquisition beginning `2026-10-23T23:29:18.000000Z` (previously verified NASA metadata).
- Proposed subset: `[88.75,21.85,88.78,21.88]`, WGS84 west/south/east/north.
- Variable: `/science/LSAR/GCOV/grids/frequencyA/HHHH`.
- Real NASA job ID: **none**.
- Submission/completion timestamps: **not applicable; no submission**.
- COG metadata, valid pixels and pixel statistics: **unavailable; no output retrieved**.
- Second candidate: **not submitted**.
- Scientific change detection: **not performed**.

## Next action

The requested local token configuration is now present. **Keep `HARMONY_PROCESSING_ENABLED=false`.** Authenticated Harmony access must succeed before enabling the single extraction. Retry when the authenticated service is reachable. If NASA subsequently returns an explicit authentication rejection, review token validity and Earthdata application authorization locally; this timeout alone does not justify declaring the token bad or replacing it.

Do not paste the token into chat, a browser field, a command URL or a `VITE_` variable. For this diagnostic task, use only the read-only command below. It refuses to run if processing is enabled; it never changes `.env`, enables processing, creates a job or controls an existing job. Token rotation is not performed.

```powershell
.venv\Scripts\python.exe -m scripts.diagnose_harmony_auth
```

## Tests

**TESTED WITH MOCKS:** Two targeted backend tests passed (27 deselected), confirming that both server gates are required before any real request and credential-free dry-run does not submit processing. The existing Starlette/httpx deprecation warning remains. These tests do not establish live NASA authentication or processing success.

After the token recheck, the complete backend regression suite also passed: **48 passed, 1 opt-in network test skipped**, with the same deprecation warning. No real job was submitted by these tests. Live COG validation and pixel statistics remain **NOT VERIFIED**.

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_harmony.py -q -p no:cacheprovider -k "real_requests_require_both_gates_before_network or dry_run_exact_supported_request_without_credentials"
```

## Exact request and documented production contract

The existing backend authenticates against **`GET https://harmony.earthdata.nasa.gov/jobs?limit=1`**, the documented jobs-list category, not a transformation endpoint. Its request uses JSON Accept, the ForestPulse Client-Id, and a server-side Bearer authentication header; no header value is reproduced here. The production origin and Bearer method are confirmed by [NASA's Harmony documentation](https://harmony.earthdata.nasa.gov/docs), including its Getting Started and jobs-list sections.

The existing client sets `follow_redirects=False` and an HTTPX 30-second timeout (connect/read/write/pool). Its default allows three attempts and waits 1 then 2 seconds between failed attempts. Several failures become the same sanitized local 502 error; both raw 401 and 403 become the existing application authentication-required state. No completed feature was changed. The separate diagnostic reports the actual response code or timeout stage before this application mapping.

The diagnostic allows **GET only** to a fixed small jobs-list or collection-capabilities route. It uses 4-second connect/write, 6-second read and 2-second pool limits, **no automatic retries**, and a 15-second outer subprocess deadline. It permits at most two same-origin, allowlisted read-only redirects and detects repeated destinations. Login redirects stop without forwarding credentials; untrusted hosts, HTTP downgrade, unexpected query parameters, transformation routes and job-control routes are blocked. Response bodies are capped at 64 KiB and never stored. DNS/TLS subprocesses have 10-second outer deadlines. Request logging and raw exception output are suppressed.

## Latest actual connectivity and acceptance results

| Probe | Observed result | Meaning |
| --- | --- | --- |
| Harmony DNS | Succeeded; 4 IPv4 addresses, no IPv6 returned | Resolver succeeded; public addresses omitted |
| Earthdata Login DNS | Succeeded; 1 IPv4 address, no IPv6 returned | Resolver succeeded |
| Harmony TCP/TLS | Succeeded; TLS 1.3; certificate hostname verified | Connection and certifi-based trust checks passed |
| Earthdata Login TCP/TLS | Succeeded; TLS 1.3; certificate hostname verified | Connection and certifi-based trust checks passed |
| Public Harmony collection capabilities | HTTP 200, about 1.125 s | Public HTTPS route reachable; not token acceptance |
| Jobs list without token | HTTP 303, about 0.735 s; Earthdata Login destination category | Expected login redirect; not followed; no loop observed |
| Authenticated jobs list, environment settings | ReadTimeout after about 6.422 s, **waiting for response headers** | No HTTP status received; token acceptance unknown |
| Authenticated jobs list, direct/no proxy environment | ReadTimeout after about 6.438 s, **waiting for response headers** | Same outcome with environment proxy handling disabled |
| Harmony-Py authenticated jobs-list session | ReadTimeout after about 7.000 s overall | Independent requests-based client also failed to obtain a response |

**No live 401, 403 or 5xx was received.** The authenticated probes timed out before response headers, so none of those codes may be inferred. No authenticated redirect loop was observed; no authenticated redirect response was received. The unauthenticated redirect was stopped at login, so the downstream login flow was not exercised.

The environment contained no HTTP/HTTPS/ALL proxy, NO_PROXY or CA-override variables. Python's discovered proxy configuration returned no proxy schemes. Direct and environment-enabled requests behaved the same. This does not rule out a transparent network appliance, VPN, endpoint-security interference or route-specific filtering; it rules out a demonstrated configured Python proxy as the cause. No proxy URL or private network configuration was exported.

## Official Harmony-Py cross-check

Installed **harmony-py 1.8.0** in the isolated, ignored `artifacts/harmony-auth-env/` environment; the project's installed dependencies and lock file were not changed. Used `Client(token=…, should_validate_auth=False)` and performed the actual read-only GET through its authenticated Requests session. A GET-only destination-guarded adapter enforced 4/6-second connect/read timeouts and **zero retries**; redirects were disabled, and environment/netrc credential fallback was disabled. The outer process deadline remained 15 seconds. No Client processing submission method was called.

The installed client's credential-validation function skips validation when a Bearer header is already present, consistent with the [official authentication source](https://github.com/nasa/harmony-py/blob/main/harmony/auth.py). Thus merely constructing a Client does not verify token acceptance. The real GET above was required, and it timed out. The [official client source](https://github.com/nasa/harmony-py/blob/main/harmony/client.py) also shows default session retries; these were explicitly replaced for this diagnostic.

## Conclusion and exact next safe action

**VERIFIED:** DNS, TCP, TLS certificate verification, public Harmony HTTPS and the unauthenticated login redirect work. The token is present locally, processing remained false before and after diagnostics, and tracked jobs stayed **0 → 0**.

**NOT VERIFIED:** Token acceptance, Earthdata application authorization and successful authenticated Harmony access. The timeout is not an invalid-token response. No credential was regenerated or rotated.

**Inference:** The failure is associated with the authenticated request path, rather than a general DNS/TLS failure or a demonstrated Python proxy issue. The same failure in HTTPX and Harmony-Py makes an HTTPX-only client defect less likely. Service authentication/token validation or route-specific network interference remains possible; the evidence does not locate the fault conclusively or establish a NASA outage.

**Next action:** Keep processing disabled and run the read-only diagnostic once from another trusted network. If authenticated requests time out there as well, give NASA Harmony/Earthdata support the sanitized UTC time window, jobs-list endpoint category and this diagnostic JSON. Do not send the token, header, cookies or signed URLs. A different-network success would point toward the original local route/security configuration. Revisit token/application authorization only if an explicit authentication rejection or other supporting evidence is obtained.

## Diagnostic regression coverage

Added tests distinguish raw 401, 403, 429 and 5xx from connect/read/write/pool timeouts; detect redirect loops; block login/untrusted/downgrade/processing redirects; enforce body/URL bounds; and verify that response bodies, fake tokens, cookies, signed URLs and exception text do not enter diagnostic output. Additional tests verify the unchanged processing client's sanitized timeout and untrusted-redirect handling.

**Final backend regression result: 75 passed, 1 opt-in network test skipped**, with the existing Starlette/httpx deprecation warning. All regression authentication responses are mocks. No frontend or completed Phase 1/2B runtime feature was modified or rebuilt.

```powershell
.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider
```

## Independent EDL validity check and network-comparison limitation

Reviewed [official EDL FAQ profile retrieval](https://urs.earthdata.nasa.gov/documentation/faq) and [User Token Management](https://urs.earthdata.nasa.gov/documentation/for_users/user_token). The FAQ documents read-only Bearer-authenticated `GET /api/users/{uid}` for an authorized application's accessible profile. Its scope restrictions matter: it is **not** a documented general-purpose introspection endpoint for every Earthdata user-token class. The documented token-list operation uses Basic credentials; creation, renewal and revocation are separate mutating operations. None of those operations was used.

One direct EDL profile GET was performed on the **original network** at `2026-11-14T19:38:28.735242Z`–`2026-11-14T19:38:30.576956Z`. The private path UID was selected in memory from the token's unverified claim only to address the profile request. JWT decoding itself was not treated as validation. The result was **HTTP 401 unauthorized**, response headers received in **1.422 seconds**, with **one attempt**, **no retries** and **no redirects followed**. The token and private profile/UID were not exported. Read/connect limits were 6/4 seconds, with a 15-second outer process deadline.

This establishes rejection for **the scoped profile API**, not that the token must be expired, revoked or invalid for Harmony. Different token classes or missing OAuth/application permissions remain possible. Harmony's previous symptom was a response-header timeout, whereas EDL now supplied an explicit HTTP response. The endpoints and outcomes must not be conflated.

**Alternative network: NOT TESTED.** The user explicitly confirmed that the computer has not switched networks. The network type is recorded as original network, transport unspecified; no SSID, ISP, public IP or invented hotspot label was recorded. No new Harmony authenticated GET was made during this follow-up, because it would not satisfy the requested alternative-network comparison. The earlier measurements remain unchanged.

## Harmony-Py and `.netrc` approaches evaluated

[NASA Harmony documentation](https://harmony.earthdata.nasa.gov/docs) supports both server-side Bearer tokens and Earthdata username/password via `.netrc` with the appropriate login/cookie redirect handling. [EDL's cURL/Wget guide](https://urs.earthdata.nasa.gov/documentation/for_users/data_access/curl_and_wget) also documents application authorization and protecting credential files. A `.netrc` path is an alternative credential source, not evidence that a failing token will work or that every redirect is safe.

The [official Harmony-Py authentication code](https://github.com/nasa/harmony-py/blob/main/harmony/auth.py) selects the supplied token before explicit username/password, environment-based credentials or netrc fallback. A Bearer header also causes its constructor validation function to skip the jobs validation request; only an actual authenticated response can confirm acceptance. The prior bounded test used Harmony-Py 1.8.0's real authenticated session and timed out, with netrc/environment credential fallback disabled. No new SDK request was needed in this follow-up.

No `.netrc`, `_netrc`, cookie jar or other credential file was created, read for credentials, or modified. Testing a new password/netrc login flow would require explicit user approval before creating/modifying credentials and a separate trusted redirect policy. We did not substitute credentials, change `.env`, rotate a token, relax redirect safeguards or modify the selected Sundarbans AOI.

## Cause assessment, prepared support draft and single next action

- **Authentication status:** Unconfirmed for Harmony and for general Earthdata user-token validity. The independent scoped profile API returned a real 401; no live Harmony 401/403 was observed.
- **Supported possibilities:** Token class/credential/application authorization mismatch is plausible given the EDL-profile 401, but not proved. Harmony's authenticated service path or route-specific local interference is also possible. Earlier DNS/TLS/public success and identical HTTPX/SDK results weaken a general connectivity or HTTPX-only explanation.
- **Not established:** A NASA outage, an invalid token for Harmony, or a local-network cause. There is no alternative-network measurement to separate those possibilities.
- **Support preparation:** [Concise sanitized NASA support draft](harmony-earthdata-support-report.md) includes endpoint categories, UTC timestamps, timings, client versions and reproducible steps. It is **prepared only, not sent**, and explicitly marks the network comparison as pending.

**Single safest next action:** Connect the computer to a trusted alternative network, then perform exactly one read-only Harmony jobs-list GET using the guarded command below. Select the network label truthfully; the confirmation is user-attested, not independent proof of network identity.

```powershell
.venv\Scripts\python.exe -m scripts.harmony_auth_followup --mode alternative --confirm-network-switch --network-type trusted_mobile_hotspot
```

Use `other_trusted_network` instead if that is the actual alternative. Do not run this command on the original network. It allows one GET, disables retries and redirect following, caps timeouts and body size, keeps processing false, and records sanitized results in a separate `docs/harmony-alternative-network.json`. No such result file has been fabricated in this follow-up. If the other network also times out, the prepared support report can be completed with that measured evidence; if it succeeds, report readiness but keep processing disabled.

**Follow-up regression tests:** 88 passed, 1 opt-in network test skipped; existing Starlette/httpx deprecation warning. New mocked checks cover scoped EDL 200/401, redirect isolation, UID/path privacy and injection protection, timeout classification, and the explicit alternative-network confirmation/single-GET gate. Existing features, tests and configuration are preserved.
