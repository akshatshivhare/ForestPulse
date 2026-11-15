# First Sundarbans GCOV-to-COG test preparation

**Execution follow-up:** The user subsequently authorized one test. That single NASA job succeeded, but its retrieved COG failed the existing extent tolerance: **INVALID**, with valid pixels present. Processing is false again, no replacement was submitted, and the authorization is consumed. [Actual job, metadata and statistics](harmony-first-live-test.md). The READY assessment below is historical.

**Decision: READY for one bounded technical extraction test, pending explicit user authorization. No processing job has been submitted.** This is not a claim of valid-pixel coverage or scientific readiness. The first output must establish those pixel-level facts; they cannot be confirmed from the public footprint alone.

Latest public preflight: **15 November 2026, 12:00:03–12:00:08 IST**, or `2026-11-15T06:30:03.341611+00:00` through `2026-11-15T06:30:08.460578+00:00`. [Sanitized dry-run evidence](harmony-first-test-readiness.json) contains the exact plan, actual source polygon, selected variable/service metadata, source timestamps and SHA-256 hashes of canonical JSON responses. A prior metadata-only pass at 11:57 IST was refreshed after correcting a browse-filename check to ASF's actual `NATIVE_A_HHHH` naming. Neither pass made an authentication, transformation or imagery-download request.

## Configuration and safety — VERIFIED

- Local `.env` now selects **`HARMONY_AUTH_MODE=earthdata_password`**. Only that non-secret selector was changed; username, password, token and all other settings were preserved. A separate fresh backend-settings process confirmed password mode and configured credentials without exposing values.
- **`HARMONY_PROCESSING_ENABLED=false`** before and after. The existing local authorization gate returned `processing_disabled`; no real submission was attempted to test the gate.
- Actual local job records: **0 before / 0 after**. Cache usage: **0 bytes**. No worker was started. No job was submitted, retried or canceled, and no satellite/browse/raw HDF5 file was downloaded.
- Existing pilot **[88.4, 21.55, 89.1, 22.25]**, both selected candidate IDs, calendars, discovery, API job architecture and dashboard remain unchanged. The second candidate remains **G4405182121-ASF**; no second-scene preflight or processing was initiated here.
- Integrated password authentication remains supported by the earlier real HTTP 200 [backend evidence](harmony-backend-password-auth.json), captured at 11:44:56–11:45:00 IST. No fresh login was needed or claimed in this public preflight. Actual processing/application authorization will still be tested by the first separately authorized job.

The readiness runner removes the unused bearer value **only from its isolated child environment**, so public CMR metadata uses no Authorization header. The real token was preserved in `.env` and token mode remains available. This does not change Phase 1's existing CMR implementation. The dry-run transport blocks authenticated requests, every Harmony path except public capabilities, and all downloads. It calls only the existing backend `submit(...dry_run=True)`, never `worker`, `run`, cancellation or live submission.

If an existing backend process has not reloaded since the selector was changed, restart it before a later authorized experiment so it reads the prepared configuration. No service was stopped or started by preparation.

## Exact candidate, variable and service — VERIFIED metadata

| Field | Current public metadata / plan |
| --- | --- |
| Granule | **G4405780437-ASF**, revision **1** |
| Acquisition start/end UTC | **2026-10-23T23:29:18.000000Z / 2026-10-23T23:29:52.999342Z** |
| Collection | **C3622241360-ASF / NISAR_L2_GCOV_V1**, collection version **1** |
| Product version | **1.0.20** |
| Orbit / pass / track / frame | **6497 / ASCENDING / 170 / 13** |
| Requested layer | **`/science/LSAR/GCOV/grids/frequencyA/HHHH`** |
| Variable concept | **V4137651715-ASF**, Frequency A HHHH |
| Acquisition band | Frequency **A**, **HH/HV**, **40 MHz** |
| Associated service | **S4389714698-ASF**, **Harmony GDAL Adapter 4.0.0** |
| Advertised operations | Bounding-box and variable subsetting, **HDF5 → COG**, output MIME **`image/tiff`** |
| Proposed subset, WGS84 W/S/E/N | **[88.75, 21.85, 88.78, 21.88]** |
| Output projection | Native; no reprojection/resampling/grid parameters requested |

Exact source producer identifier:

```text
NISAR_L2_PR_GCOV_033_170_A_013_4005_DHDH_A_20261023T232918_20261023T232952_P05036_N_F_J_001
```

The existing roughly **3.10 × 3.34 km** extraction box is retained, not a new selected study area. It requests one layer and about one hundred thousand nominal pixels rather than the full multi-layer product. It is already small relative to the enforced limits; no automatic AOI replacement or expansion was made.

Public sources refreshed through the existing backend:

- [Exact granule metadata](https://cmr.earthdata.nasa.gov/search/granules.umm_json?concept_id=G4405780437-ASF&page_size=1).
- [Live NISAR collection discovery](https://cmr.earthdata.nasa.gov/search/collections.umm_json?keyword=NISAR&page_size=200).
- [Current collection Harmony capabilities](https://harmony.earthdata.nasa.gov/capabilities?collectionId=C3622241360-ASF).
- [Associated service metadata](https://cmr.earthdata.nasa.gov/search/services.umm_json?concept_id=S4389714698-ASF).

## Coverage and remaining uncertainty

**VERIFIED:** The current actual CMR polygon is geometrically valid and contains the entire requested subset, with **100% subset footprint coverage**. The check used the polygon, not its bounding rectangle. The scene's frequency-A HHHH browse PNG is listed as `..._NATIVE_A_HHHH.png`; only its public metadata name was inspected, and the image was not downloaded.

**PARTIALLY VERIFIED:** These facts support the location and expected layer for a small extraction experiment. [ASF's Harmony guide](https://nisar-docs.asf.alaska.edu/harmony/) confirms GCOV layer/spatial extraction to COG, while warning that advertised collection variables need not occur in every individual file. No raw HDF5 array was inspected to independently confirm its contents.

**NOT VERIFIED:** Actual finite/unmasked positive radar pixels, subswath/focusing mask coverage, mangrove-mask intersection, exact grid/CRS, nodata and output size. Metadata containment does **not** satisfy a claim of valid radar-pixel coverage. Thus task-level valid-pixel confirmation remains unresolved before extraction; this report's READY label applies only to performing the bounded test that can establish it. A test returning no valid pixels must fail, not produce a forest-change claim. If valid-pixel proof is required before any extraction at all, that additional prerequisite is **BLOCKED** under the current no-processing/no-source-array access constraint.

Incidence metadata remains missing in CMR, and tides, mangrove fraction, radiometric consistency and later two-scene alignment remain science gates. They are not inferred from nominal repeat geometry or this preflight. `analysis_ready` stays **false**.

## Prepared request — constructed only, NOT SENT

```text
GET https://harmony.earthdata.nasa.gov/C3622241360-ASF/ogc-api-coverages/1.0.0/collections/V4137651715-ASF/coverage/rangeset?granuleId=G4405780437-ASF&subset=lon%2888.75%3A88.78%29&subset=lat%2821.85%3A21.88%29&format=image%2Ftiff&forceAsync=true&maxResults=1&ignoreErrors=false
```

The [official Harmony API](https://harmony.earthdata.nasa.gov/docs) documents these parameters. There is one exact granule ID, one exact variable ID, two `subset` dimensions, COG MIME `image/tiff`, **`forceAsync=true`**, **`maxResults=1`** and **`ignoreErrors=false`**. No broad temporal search, `all` variable extraction or second scene is included. No server-side output-size guarantee or cost estimate is inferred from these parameters.

After separate authorization, the API submission body would be:

```json
{"granule_id":"G4405780437-ASF","bbox":[88.75,21.85,88.78,21.88],"dry_run":false}
```

This body has **not** been sent. Keep the real processing flag false until authorization. The first test must use one entry point, not concurrent CLI and UI attempts.

## Expected files and resource limits

Expected result, conditional on successful extraction: **one single-band frequency-A HHHH COG**, plus asynchronous job/status metadata. Its actual remote name, job ID and creation time are unknown. Locally, the existing backend would journal `artifacts/harmony/<local-uuid>.json`, stream to `<local-uuid>.part`, then rename to `<local-uuid>.tif` only after successful validation. None exists from this preparation. No full HDF5 file is required locally; NASA's service may still read the large upstream product during processing.

| Item | Estimate / enforced bound |
| --- | --- |
| Nominal spacing assumption | **10 m**, derived from the live 40 MHz acquisition and [ASF's GCOV spacing table](https://nisar-docs.asf.alaska.edu/gcov/) |
| Approximate grid, not actual output | **310 columns × 334 rows = 103,540 pixels** |
| One float32 layer's raw samples | **414,160 bytes ≈ 0.395 MiB**, excluding all COG overhead |
| Actual COG dimensions/file size | **Unknown** until returned; projection, tile padding, masks, overviews and compression change the estimate |
| Per-output file cap | **64 MiB**; both declared and streamed size checked |
| Aggregate local cache cap | **256 MiB** |
| Raster validation cap | **4,000,000 pixels**, expected one float32 band |
| Job deadline / polling | **1,200 seconds / 5 seconds** |
| Concurrent jobs / retained job records | **1 / 50** |
| Cache retention | **86,400 seconds**, subject to existing unresolved-job protections |

Rasterio must confirm COG structure, source/variable identity from output evidence, CRS, extent within the existing tolerance, resolution/transform, dimensions, dtype, nodata/masks and actual readable positive finite pixels. The first real validation report must record actual values and statistics, not reuse these estimates. No scientific change detection or second-scene processing is authorized by readiness.

## Validation and remaining authorization

- Backend regressions: **123 passed, 1 opt-in public-metadata test skipped**, **4.45 seconds**. Existing Starlette/httpx deprecation warning remains.
- Frontend regressions: **9 passed**, two files. No dashboard/API runtime changes were needed.
- Seven preparation tests cover secret-byte preservation, selector-only changes, missing/unsafe configuration rejection and actual ASF browse naming. Test collection now isolates real credentials and default auth mode so the newly configured local password mode cannot leak into mocked regression tests.
- No production code or frontend bundle changed in this task, so the already passing production build was not repeated.

Preparation is complete. Remaining actions are **explicit user authorization**, ensuring the backend has loaded password mode, and only then deliberate temporary enablement for **one** first-scene job. Processing success, dataset authorization and valid output pixels remain unproven until that job returns. Do not submit, retry or cancel a real job as part of this preparation report.
