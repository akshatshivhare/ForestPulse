# Draft NASA Earthdata / Harmony support report

**Prepared only; not sent. Alternative-network comparison is pending.** No credentials, private user identifiers, authentication headers, cookies, signed URLs or response bodies are included.

**Subject:** Production Harmony authenticated jobs-list GET times out; public HTTPS works; scoped EDL profile GET returns 401

We are diagnosing read-only authentication for a local NISAR GCOV prototype. Processing is disabled, and no transformation or job-control request has been submitted.

**Endpoints:**

- Harmony: `GET https://harmony.earthdata.nasa.gov/jobs?limit=1`.
- Public control: Harmony collection capabilities for `C3622241360-ASF`.
- Independent EDL check: `GET https://urs.earthdata.nasa.gov/api/users/{uid}`; private UID and profile omitted. This is the scoped profile mechanism described in the EDL FAQ, not a general user-token introspection API.

**Observed evidence (UTC):**

| Time window | Result |
| --- | --- |
| 2026-11-14 19:19:22.691556–19:19:39.179962 | Harmony/EDL DNS and certificate-verified TLS 1.3 passed. Public capabilities HTTP 200 (1.125 s). Unauthenticated jobs-list HTTP 303 to the EDL login category (0.735 s), not followed. |
| Same window | Authenticated HTTPX jobs-list requests timed out waiting for response headers: 6.422 s with environment handling and 6.438 s with it disabled. No HTTP status was received. Harmony-Py authenticated session also produced ReadTimeout (7.000 s overall). |
| 2026-11-14 19:38:28.735242–19:38:30.576956 | Independent scoped EDL profile GET: HTTP 401 after 1.422 s; no redirect followed. Token was not accepted for that profile API. Scope/application authorization prevents treating this alone as proof of global user-token invalidity. |

**Network:** Original network, confirmed by the user; transport/ISP details not supplied. No Python-discovered proxies or HTTP proxy/CA override environment variables were found in the saved diagnostic. The computer has **not** switched networks, so this report makes no cross-network or NASA-outage claim.

**Clients:** Windows, Python 3.12.13; HTTPX 0.28.1; isolated Harmony-Py 1.8.0, Requests 2.34.2, urllib3 2.8.0, certifi 2026.10.23. The supplied bearer token was passed in memory only. Harmony-Py Client construction was not counted as validation; the actual read-only jobs GET was tested.

**Bounds and security:** No automatic retries in the diagnostic probes. HTTP connect/read limits 4/6 seconds; 15-second outer subprocess deadline; 64 KiB body limit. Redirects are stopped before sending credentials to another origin. Token, profile and raw request/response headers are never recorded. No token was generated, renewed, revoked or rotated. No credential file was created or modified.

**Reproduction in the project:** With the existing local token configured privately and `HARMONY_PROCESSING_ENABLED=false`, run:

```powershell
.venv\Scripts\python.exe -m scripts.diagnose_harmony_auth
.venv\Scripts\python.exe -m scripts.harmony_auth_followup --mode edl
```

The first performs bounded read-only controls plus authentication checks; the second performs one scoped EDL-profile GET. An alternative-network test is still required and will be recorded separately only after the user connects to a trusted alternative network.

**Questions for support:** Is the configured Earthdata user-token class supported directly by the scoped profile API, or does that endpoint require different OAuth application authorization? Is there a documented read-only validation mechanism specifically for Earthdata user tokens? Could Harmony's production bearer-authentication path explain response-header timeouts for the UTC windows above?

**Attachments available:** `harmony-auth-diagnostics.json` and `earthdata-auth-independent.json`, both sanitized. Do not attach `.env`, `.netrc`, cookie jars, raw HTTP traces or token-bearing commands.
