# Phase 2B: gated NASA Harmony GCOV extraction

**Second-scene preparation, 15 November 2026: READY, awaiting explicit authorization.** The 4 November candidate's exact dry-run and known geometry/polarization metadata passed. Incidence and scientific comparability remain unknown. The revalidated first COG is now registered locally with an original-record backup; no second job was created and processing remains false. [Second request, resource bounds and unresolved risks](harmony-second-test-readiness.md). Prior notes about the locked first-reference gate are historical.

**Spatial revalidation update: VALID.** The existing first-job COG passes the new CRS-aware crop checks, with all 102,933 positive centers inside the AOI and only documented subpixel boundary loss. [Spatial evidence and limits](harmony-spatial-validation.md). Processing remains false; the historical job record and scene-two lock were not automatically promoted. No new job or scientific comparison was performed. Earlier INVALID notes describe the superseded geographic-envelope rule.

**First live test, 15 November 2026: INVALID under the existing extent validator.** Exactly one authorized NASA job completed successfully and its COG was retrieved: 380,888 bytes, EPSG:32645, 313 × 334, 102,933 positive finite unmasked pixels. Its geographic envelope failed the current tolerance; no first output was accepted and scene two remains locked. Processing is false again. [Actual job, retrieval fix, statistics and failure](harmony-first-live-test.md). Earlier preparation/authentication notes below are historical.

**First-test preparation, 15 November 2026:** The first-scene public dry-run has been refreshed, local password mode prepared without changing secrets, and the existing subset confirmed inside the actual CMR polygon. **READY for one bounded extraction experiment, awaiting explicit authorization.** Valid radar pixels remain unverified; processing stays false and local jobs remain zero. [Exact request, limits, coverage caveat and readiness report](harmony-first-test-readiness.md).

**Authentication update, 15 November 2026:** The backend now supports explicit `earthdata_password` and `earthdata_token` modes. The integrated Harmony-Py password session is **LIVE VERIFIED**: read-only jobs-list HTTP 200 after three trusted NASA redirects in **3.219 seconds**, with no bearer use. [Implementation, sanitized evidence and first-test checklist](harmony-backend-authentication.md). The existing token transport remains available; its earlier live timeouts are unresolved. Processing remains disabled, and no processing job or COG has been verified.

Implementation and public preflight: **14 November 2026**. This adds technical extraction to the existing ForestPulse application. The Phase 1 discovery/calendar/map/screening flow remains in place. No mangrove classifier, disturbance measurements, calibrated change analysis or scientific readiness claim is implemented.

## What is genuinely working

| Label | Evidence / limitation |
| --- | --- |
| **IMPLEMENTED** | Explicit server-side password-session or bearer authentication; default dry-run; live CMR/service preflight; one-variable small-subset request construction; persisted job queue and provenance; automatic submission/polling; bounded retries, cancellation and deadline; streamed output cache; Rasterio COG inspection; second-scene gate and technical grid-alignment check; dashboard processing panel. |
| **TESTED WITH MOCKS** | Synthetic Harmony responses and explicitly synthetic COG fixtures exercise successful extraction, second-scene alignment, missing/invalid output, remote failures, cancellation, timeout, uncertain submission, persistence/recovery, process exclusion, size/storage limits, credential redaction, auth redirects, retry backoff and API errors. Synthetic pixels are never application observations. |
| **LIVE VERIFIED** | Public preflight; password authentication; exactly one successful first-scene NASA job; real COG retrieval, metadata and pixel statistics. The output failed the current extent rule; see [first live test](harmony-first-live-test.md). |
| **BLOCKED** | Processing is false again. The first output was not accepted because west/east envelope differences exceeded the existing tolerance. Scene two remains locked; grid alignment and scientific comparison remain unverified. No replacement job is authorized. |

The original processing test was not attempted when its two server gates were off. Authentication has since been verified in password mode, but live processing remains deliberately disabled. The first real extraction must pass before the second can be submitted. A successful COG is technical evidence only; `analysis_ready` always remains false.

## Exact NASA inputs and live preflight

The current evidence was captured at **2026-11-14T17:57:21.710863+00:00**. Acquisition times are UTC and distinct from metadata publication/ingestion.

| Field | First candidate | Second candidate |
| --- | --- | --- |
| Granule concept / source | [G4405780437-ASF](https://cmr.earthdata.nasa.gov/search/concepts/G4405780437-ASF.umm_json) | [G4405182121-ASF](https://cmr.earthdata.nasa.gov/search/concepts/G4405182121-ASF.umm_json) |
| Beginning UTC | 2026-10-23T23:29:18.000000Z | 2026-11-04T23:29:18.000000Z |
| Ending UTC | 2026-10-23T23:29:52.999342Z | 2026-11-04T23:29:52.999342Z |
| CMR concept revision | 1 | 1 |
| Absolute orbit | 6497 | 6670 |
| Pass / track / frame | ASCENDING / 170 / 13 | ASCENDING / 170 / 13 |
| Frequency / polarizations | A: HH, HV; B: HH, HV | A: HH, HV; B: HH, HV |
| Range bandwidth | A: 40 MHz; B: 5 MHz | A: 40 MHz; B: 5 MHz |
| Look / reported orbit type | LEFT / MOE | LEFT / MOE |
| Incidence angle | **Missing in CMR** | **Missing in CMR** |

Both are L-SAR GCOV product version **1.0.20**, in **C3622241360-ASF / NISAR_L2_GCOV_V1**, collection version **1**, whose published title identifies it as validated. This collection title is not validation of these scenes for ecological change analysis.

Exact producer identifiers:

```text
NISAR_L2_PR_GCOV_033_170_A_013_4005_DHDH_A_20261023T232918_20261023T232952_P05036_N_F_J_001
NISAR_L2_PR_GCOV_034_170_A_013_4005_DHDH_A_20261104T232918_20261104T232952_P05036_N_F_J_001
```

The live preflight rechecked both actual CMR polygons; their coordinates and attributes are embedded in `candidates[].scene` in the evidence JSON. Shared coverage is **approximately 91.49%** of the unchanged pilot `[88.4,21.55,89.1,22.25]`. The existing screening remains `unknown` for incidence. Footprint overlap does not establish valid pixel coverage or grid alignment.

The extraction proposal is **`[88.75,21.85,88.78,21.88]`**, WGS84 west/south/east/north. This is about a 3 km sector inside the audited central-forest proposal, not a new selected pilot or an authoritative mangrove boundary. Both published scene polygons fully contain this small box. Its actual mangrove fraction remains unverified. Server validation confines custom subsets to `[88.65,21.7,88.9,21.95]`, with each side between 0.001 and 0.05 degrees.

The first test requests just **`/science/LSAR/GCOV/grids/frequencyA/HHHH`**, variable concept **V4137651715-ASF**, corresponding to HH diagonal radar power. CMR reports frequency-A HH in both acquisitions, and the feasibility audit recorded matching HHHH browse-layer artifacts. Actual source-array presence and extraction still require the real test.

## Verified service contract and constructed requests

Primary references checked:

- [Official ASF NISAR Harmony guide](https://nisar-docs.asf.alaska.edu/harmony/): GCOV variable/spatial extraction to COG; possible collection variables can be absent in individual products.
- [Official NASA Harmony API documentation](https://harmony.earthdata.nasa.gov/docs): bearer-header authentication, OGC coverages parameters, async job/status/cancel behavior.
- [Official Harmony-Py client source](https://github.com/nasa/harmony-py/blob/main/harmony/client.py): coverages route construction and **GET** `/jobs/{jobID}/cancel`.
- [Live collection capabilities](https://harmony.earthdata.nasa.gov/capabilities?collectionId=C3622241360-ASF) and associated [service metadata S4389714698-ASF](https://cmr.earthdata.nasa.gov/search/concepts/S4389714698-ASF.umm_json): Harmony GDAL Adapter **4.0.0**, variable and bounding-box subset, **HDF5 → COG**, MIME `image/tiff`. The PNG browse service is not used.

The implementation checks the service association and explicit COG reformatting at preflight. It uses the advertised variable concept in the documented coverages variable path. Native output projection is requested by omitting reprojection parameters; actual grids are inspected after download.

The exact **constructed first request**, recorded from live metadata but **not submitted**, is:

```text
GET https://harmony.earthdata.nasa.gov/C3622241360-ASF/ogc-api-coverages/1.0.0/collections/V4137651715-ASF/coverage/rangeset?granuleId=G4405780437-ASF&subset=lon%2888.75%3A88.78%29&subset=lat%2821.85%3A21.88%29&format=image%2Ftiff&forceAsync=true&maxResults=1&ignoreErrors=false
```

The second constructed dry-run request is identical except `granuleId=G4405182121-ASF`. Both exact URLs, collection details, variable/service IDs and source geometry are in [harmony-verification.json](harmony-verification.json). These URLs contain no credentials. Local preflight success does not prove server acceptance of a transformation.

## Authentication and live-test setup

Public discovery and dry-run work without credentials. Select `HARMONY_AUTH_MODE=earthdata_password` to use the verified Harmony-Py session with `EDL_USERNAME` / `EDL_PASSWORD`. Alternatively select `earthdata_token` (the backward-compatible default) and configure `EARTHDATA_TOKEN` from [official token management](https://urs.earthdata.nasa.gov/documentation/for_users/user_token). No fallback occurs between modes. Configure credentials **only** in the backend environment or ignored project-root `.env`; restart the backend after changes. Earthdata/ASF application authorization may also be required. See [session lifecycle and exact live evidence](harmony-backend-authentication.md).

The server reads:

```dotenv
HARMONY_AUTH_MODE=earthdata_password
EDL_USERNAME=
EDL_PASSWORD=
# Used only with HARMONY_AUTH_MODE=earthdata_token:
EARTHDATA_TOKEN=
HARMONY_PROCESSING_ENABLED=false
```

Keep real processing off while reviewing the dry-run. The browser has no credential field. Credentials must never use a `VITE_` prefix or enter a URL. Token mode sends its bearer header only to the exact Harmony origin. Password mode uses the official SDK session and trusted Earthdata login redirects; cookies remain in memory and are cleared on expiry/error/shutdown. HTTP-library debug logging is disabled. Raw upstream exception text/messages and signed output links are not exposed or persisted. Processing validation errors do not echo accidentally supplied input. `.env*` files are ignored except the blank `.env.example`.

Manual steps for the **one** initial real test:

1. Follow the README setup and install updated backend dependencies. This workspace already has Rasterio **1.5.2** installed and pinned in the backend lock.
2. Run `.venv\Scripts\python.exe -m scripts.verify_harmony` with live processing disabled to refresh the public preflight. It writes `docs/harmony-verification.json`; it cannot submit a job unless both server gates are configured.
3. Only in a separately authorized processing task, configure the selected server authentication mode and deliberately enable `HARMONY_PROCESSING_ENABLED=true` for one test. Do not paste credentials into chat, browser forms or commands that will be logged. Credential presence does not prove authorization. Keep the flag false during authentication-only validation.
4. Run the same verification command for **one first-candidate extraction**, or start the backend and use **Date Comparison → Prepare a small radar subset → Validate dry run → Submit one real extraction**. Use one workflow, not a batch. The CLI never submits scene two. A process lock and persisted idempotency prevent the CLI/API workers from duplicating the same tracked submission.
5. Inspect the actual result. If it is blocked/failed, stop and resolve that evidence. Do not call the second scene successful or unlock it manually. Once the first is truly verified, the API/UI permits a separate second-candidate request for the same subset and checks both outputs on a common grid.
6. Turn live processing off again when the experiment is complete. No raw HDF5 upload or manual data download is required.

The verification script overwrites its dated evidence with the actual outcome, including real source/request/raster metadata when available. It contains no synthetic success fallback. If a submission is ambiguous, it retains `submission_unknown` and does not blindly retry. Before retrying an uncertain job, reconcile it using NASA's jobs interface; retain/cancel any actual remote job first. The local prototype intentionally has no shortcut to bypass this safety block.

## API and UI

| Endpoint | Behavior |
| --- | --- |
| `GET /api/processing/capabilities` | Selected method and configuration flag, in-memory password-session verification flag, bounded subset/variable, limits, second-scene gate; no credentials, cookies or signed URLs |
| `POST /api/processing/jobs` | `granule_id`, optional bounded `bbox`, `dry_run` (defaults **true**); validates current metadata/services before queueing |
| `GET /api/processing/jobs` | Persisted local job list, at most 50 retained records |
| `GET /api/processing/jobs/{local-id}` | Local state/progress, sanitized error, plan/provenance, remote ID if confirmed, validated raster metadata if available |
| `POST /api/processing/jobs/{local-id}/cancel` | Queued cancellation or request for remote cancellation; no optimistic remote-success claim |
| `GET /api/processing/jobs/{local-id}/raster` | Verified metadata and alignment only; returns 409 until a verified cached raster exists |

Example safe request body:

```json
{"granule_id":"G4405780437-ASF","bbox":[88.75,21.85,88.78,21.88],"dry_run":true}
```

The UI adds a panel to Date Comparison without replacing its calendars, map or conservative screening. It shows setup/authentication errors, dry-run provenance, job stages, polling, cancellation and verified raster metadata. It never automatically submits a live job. The second dropdown choice remains disabled until a real first output is verified; the backend independently enforces this gate and same-subset requirement.

## Job lifecycle, storage and recovery

- Typical stages: `queued → submitting → running → downloading → validating → verified`. `verified` means technical COG validation, never ecological validation. `paused`, `cancel_pending`, `authentication_required`, `failed`, `timed_out`, `canceled` and `submission_unknown` are explicit.
- The FastAPI lifespan runs the automatic worker; use the README's single-worker local Uvicorn command. The prototype is a trusted local service, not a multi-user public job platform. OS file locks serialize admission and processing, including CLI/API contention.
- Job IDs/provenance are journaled to JSON before submission. Confirmed remote jobs resume polling after restart. An interrupted unconfirmed submission becomes `submission_unknown`, never an automatic second submission. Repeated identical submissions return the existing tracked job. A definitive auth rejection without a remote job can be retried after fixing setup.
- Polling normally waits **5 seconds**. Idempotent status/capability requests and output downloads retry at most three attempts with bounded exponential waits. The potentially non-idempotent transformation submission is sent once; timeouts/ambiguous responses block further work. Remote errors or `complete_with_errors` do not count as success.
- Public preflight has a **40-second** overall deadline. The job deadline is **20 minutes from queue creation**, including download; a bounded remote cancel is attempted on timeout. Failed status handling also attempts cancellation when the remote job might remain active. Remote cancellation must be confirmed before assuming NASA stopped. Unresolved remote work prevents additional jobs.
- A file is limited to **64 MiB**, aggregate cache to **256 MiB**, raster reads to **4 million pixels**, and retained job records to **50**. Downloads stream to UUID-named `.part` files and check both declared and actual byte counts. No server filename becomes a filesystem path. Failed/canceled partial data is removed.
- Cache location: ignored **`artifacts/harmony/`**. Resolved terminal jobs/files expire after **24 hours**; cleanup runs with the worker and API reads, also removing stale orphan files. Active reference rasters are protected while scene two uses them. Uncertain submission/unconfirmed remote work retains small provenance records until reconciled and blocks admission; safety takes precedence over deleting unresolved evidence. Full storage rejects new work rather than growing unboundedly.
- Signed asset links stay in memory. Downloads allow only HTTPS Harmony and `harmony-prod-*` regional S3 hosts; tokens are never sent to S3. Every redirect is checked. An unexpected legitimate staging host will be **blocked**, and must be reviewed against actual NASA evidence before changing the allowlist. No actual asset host has yet been observed in a real job.

## Raster validation and grid checks

For a downloaded first output, Rasterio must establish: GTiff with COG layout marker and tiled organization; CRS; expected small geographic extent (within three output pixels); non-rotated finite transform and positive spacing; exactly one float32 band; bounded dimensions; nodata (including NaN), mask flags and overviews; readable blocks and finite unmasked positive power. Metadata records actual dimensions, extent, resolution, band/dtype, mask counts, file size and SHA-256. This is a Rasterio layout/readability check, not an independent complete OGC byte-offset conformance certification.

The validator requires the exact source producer identifier and frequency-A HHHH evidence in the returned asset name, band description or raster tags. It rejects contradictory band descriptions. The request alone cannot establish actual radar variable identity. If real output naming/tags provide insufficient evidence, validation fails closed pending inspection of actual provenance. No real identity evidence is invented here.

The second candidate requires a verified first COG for the **same subset**. Both outputs are bounded and inspected. The alignment routine computes their intersection in the first CRS, snaps a common grid to the first pixel origin/resolution, and actually reprojects both into that grid in memory. It records whether native grids already matched and whether shared finite positive samples remain. Shifted grids are exercised by synthetic tests. This is technical alignment; nearest-neighbor sampling is not a scientifically selected radar comparison/aggregation method.

**Actual output metadata in this audit: none.** `live_result` is null and `processing_submitted` is false in the evidence. There are no real COG dimensions, image statistics or alignment results to report.

## Scientific requirements still unresolved

Continue to treat these observations as candidates. The existing incidence-angle field remains null. The radar-grid incidence cube is not among the advertised 2D extraction variables, so this one-layer COG integration does not resolve incidence geometry. Acquisition-time tides, recent rainfall/wetness, calibration/RFI/noise and focusing QA, valid GCOV subswath masks, co-registration accuracy, baseline mangrove masks, local uncertainty and independent disturbance validation remain unresolved. The COG internal mask is not a replacement for the GCOV science mask. See the [feasibility audit](sundarbans-data-feasibility.md) for the proposed GMW baseline and scientific gates.

No loss/gain threshold, classifier, biomass inference, ecological accuracy, or measured forest-change report is provided. Those belong to Phase 3 after the outstanding evidence is obtained.

## Validation commands and evidence

```powershell
.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider
npm.cmd test
npm.cmd run build
.venv\Scripts\python.exe -m scripts.verify_harmony
```

The opt-in public integration pytest uses `FORESTPULSE_LIVE_METADATA_TEST=true` and never submits transformations. It is skipped in the default offline suite; the equivalent public preflight above was run successfully against NASA. Actual credentialed processing remains gated and blocked in this workspace.

Final regression evidence: **48 backend tests passed**, with **1 opt-in network test skipped**; **9 frontend tests passed**; TypeScript/Vite production build passed. The existing Starlette/httpx deprecation and large JavaScript bundle warnings remain. Frontend validation covers build/type checks and processing-gate unit tests; no new visual/browser interaction verification is claimed.
