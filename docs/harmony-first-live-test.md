# One authorized Sundarbans Harmony test

**Later spatial audit: VALID.** The same job's COG now passes documented CRS-aware pixel-grid and valid-footprint validation; the earlier degree-envelope rule caused a false rejection. [Exact geometry, tolerances and regression evidence](harmony-spatial-validation.md). No new job was submitted. The initial test outcome and evidence below remain historical and unchanged.

**Result: INVALID under the existing extent validator.** NASA successfully completed **exactly one** real GCOV-to-COG job. Its retrieved COG contained **102,933 finite, unmasked positive radar-power pixels**, but its WGS84 envelope exceeded the existing extent tolerance. Processing is disabled again. No replacement, second scene or forest-change analysis was performed.

[Sanitized real evidence](harmony-first-live-test.json) retains the request, timestamps, all 15 status observations, retrieval recovery and actual output diagnostics. The failed local provenance record is retained for idempotency; the invalid raster was removed. No credentials, cookies, signed URLs or raw remote payloads are stored in evidence.

## Actual job and timing — LIVE VERIFIED

| Field | Actual evidence |
| --- | --- |
| NASA job ID | **`c9136c2d-e1ec-4669-b738-4a455f3b8f66`** |
| Local provenance ID | **`52a89f3e-c229-4900-9246-f39aa928278f`** |
| Granule | **G4405780437-ASF**, revision 1 |
| Acquisition UTC | **2026-10-23T23:29:18.000000Z – 2026-10-23T23:29:52.999342Z** |
| Collection / product | **C3622241360-ASF / NISAR_L2_GCOV_V1**, collection v1; GCOV product v1.0.20 |
| Variable | **V4137651715-ASF**, `/science/LSAR/GCOV/grids/frequencyA/HHHH` |
| Requested WGS84 bounds | **[88.75, 21.85, 88.78, 21.88]** |
| Authentication verified UTC | **2026-11-15T06:49:49.292167Z**, explicit password session, no bearer |
| Process-local enablement UTC | **2026-11-15T06:50:03.417000Z** |
| Client submission journal UTC | **2026-11-15T06:50:04.242144Z** |
| Submission HTTP / transport count | **303**, **one GET**, **zero submission retries** |
| Job ID received UTC | **2026-11-15T06:50:05.156995Z** |
| NASA creation UTC | **2026-11-15T06:50:03.650Z** |
| NASA successful-state update UTC | **2026-11-15T06:51:19.847Z** |
| Success observed UTC | **2026-11-15T06:51:25.814568Z**, **100%** |
| NASA processing duration | **76.197 seconds**, using NASA's own timestamps |
| Initial runner exit / processing restored false UTC | **2026-11-15T06:51:32.580415Z** |
| Same-job COG download completed UTC | **2026-11-15T06:57:03.884607Z** |
| Retrieval/validation finished UTC | **2026-11-15T06:57:03.999190Z** |

Initial runner window: **12:19:46–12:21:32 IST on 15 November 2026**. Retrieval/validation finished at **12:27:03 IST**. Server/client clocks differ slightly: NASA's creation time precedes the client journal. The duration above uses a single clock source.

Exact request sent once:

```text
GET https://harmony.earthdata.nasa.gov/C3622241360-ASF/ogc-api-coverages/1.0.0/collections/V4137651715-ASF/coverage/rangeset?granuleId=G4405780437-ASF&subset=lon%2888.75%3A88.78%29&subset=lat%2821.85%3A21.88%29&format=image%2Ftiff&forceAsync=true&maxResults=1&ignoreErrors=false
```

The runner reused the integrated Harmony-Py password session, preflight, admission journal and processing core. It checked the exact authorized scope, disabled submission retries and held the worker lock across queueing/execution. Its authorization journal prevents repeating the submission command. Enablement was process-local; `.env` stayed false and was not modified. The unused token was excluded only from this command's environment. No credential was changed.

## Output retrieval recovery — same job only

The initial runner observed NASA `successful`, then hit local **`unsafe_asset_url`**. Three bounded output-retrieval attempts were blocked at the host allowlist before COG transfer. They were not replacement processing submissions.

A read-only inspection confirmed one `image/tiff` asset on the exact Harmony HTTPS origin. That authenticated output route returned **307** to **`dqzb5lcolc8fj.cloudfront.net`**, outside the original S3-only allowlist. An additional diagnostic retrieval recorded only the hostname and again stopped before downloading COG bytes.

The [official NASA service-results source](https://github.com/nasa/harmony/blob/main/services/harmony/app/frontends/service-results.ts) documents signed-object **307** redirects. [Harmony documentation](https://harmony.earthdata.nasa.gov/docs) describes staged output links. The exact distribution was established by the live TLS-verified NASA redirect; it was not independently named in the public documentation checked. Only that exact host was added—no CloudFront wildcard. A fresh anonymous client sends **no Earthdata Authorization header or session cookie** to it.

After mocked security checks passed, a retrieval-only helper downloaded the **same successful job's one COG** under the existing **64 MiB** limit. Processing stayed false. This helper has no submit, worker or cancel path. No new job or raw HDF5 download occurred.

## Rasterio results — actual measurements

| Check | Actual result |
| --- | --- |
| File size | **380,888 bytes**, approximately **0.363 MiB** |
| COG structure | Passed the existing GTiff/tiled/COG-layout checks before the later extent failure |
| CRS | **EPSG:32645**, WGS84 / UTM zone 45N |
| Dimensions / readable pixels | **313 × 334 / 104,542** |
| Bands / dtype | **1 / float32** |
| Resolution | **10 × 10 m** |
| Native bounds W/S/E/N, metres | **[680810.0, 2417260.0, 683940.0, 2420600.0]** |
| WGS84 envelope | **[88.74964975241748, 21.84974895616848, 88.78030086029081, 21.880234889089312]** |
| Nodata | **NaN**; JSON uses `nodata: null`, `nodata_is_nan: true` |
| GDAL-masked pixels | **1,609** |
| Finite GDAL-unmasked pixels | **102,933** |
| Positive finite GDAL-unmasked pixels | **102,933** |
| Unmasked nonfinite pixels | **0** |
| Source / radar variable identity | Passed the independent output-identity check before extent validation failed |
| Final acceptance | **FAILED: `extent_mismatch`** |

The inspector compares the full producer identifier and `frequencyA/HHHH` against actual output filename/tag/band evidence, not the request alone. It reached its extent error only after that check passed. An initial diagnostic flag marked identity false for all extent failures; reporting was corrected using this executed control flow and a regression test. No acceptance criterion was relaxed and the result remains INVALID.

The WGS84 envelope and edge diagnostics were reproduced locally from the recorded actual CRS/native bounds/dimensions with Rasterio `transform_bounds(..., densify_pts=21)`, matching the validator. This required no additional NASA request or output download.

### Exact extent failure

Existing tolerance: **0.00029378058664528893 degrees**, three times the larger geographic span-per-pixel. Absolute edge differences from the requested bounds:

| Edge | Absolute difference, degrees | Pass |
| --- | --- | --- |
| West | **0.0003502475825172269** | **No** |
| South | **0.00025104383152196874** | Yes |
| East | **0.00030086029080678145** | **No** |
| North | **0.00023488908931312835** | Yes |

The native UTM rectangle's geographic envelope and grid rounding are plausible contributors; this is an **inference**, not a verified diagnosis of NASA cropping. No AOI, request or tolerance was changed. Projection-aware extent validation could be reviewed locally in a future task; this test stops with the current rule's **INVALID** verdict.

### Actual pixel statistics

Population: all **102,933 finite GDAL-unmasked pixels**, all positive. Values are linear GCOV HH power, not dB or a mangrove-only population. No separate GCOV focusing/subswath mask or baseline mangrove mask was applied.

| Statistic | Measured value |
| --- | --- |
| Minimum | **0.002036839723587036** |
| Maximum | **3.030181884765625** |
| Mean | **0.1530429612423082** |
| Population standard deviation | **0.12685261433299033** |

This was **not a no-valid-pixels result**. Pixel availability was demonstrated, while complete technical acceptance failed. These values are not forest-change measurements or scientific validation.

## Final safety and tests

- Exactly **one** processing submission and one NASA job ID. No replacement/retry submission or cancellation was sent.
- Processing **false** after the runner, throughout retrieval recovery and in a fresh final settings check. Password mode and original credentials retained; `.env` unchanged by this test.
- One local provenance record; **zero cached `.tif` files and zero `.part` files** after invalid-output cleanup. Measured metadata/statistics retained in sanitized JSON. Scene two remains **locked**.
- Backend acceptance criteria were unchanged. Only exact output-host compatibility and diagnostic evidence were corrected. Discovery, calendars, selected pilot and dashboard architecture were preserved.
- Final backend tests: **131 passed, 1 opt-in public-metadata test skipped**, **5.56 seconds**. Existing Starlette/httpx deprecation warning remains.
- Frontend tests: **9 passed**, two files. No frontend bundle changed; production build was not repeated for this test task.

**Stop condition reached: INVALID.** This one-shot authorization is consumed. Any later processing submission requires new explicit authorization. No scene-two processing or forest-change analysis was added.
