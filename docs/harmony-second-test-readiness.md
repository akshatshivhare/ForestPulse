# Second Sundarbans observation: request readiness

**READY for one bounded second-scene extraction experiment, pending explicit user authorization.** No second Harmony job was submitted, and processing remains **false**. **Scientific suitability for comparison is NOT VERIFIED.** Matching acquisition metadata and overlapping footprints do not establish valid common pixels or comparable backscatter.

Fresh preflight UTC window: **2026-11-15T08:02:25.742089Z – 2026-11-15T08:02:30.815935Z**, or **13:32:25–13:32:30 IST on 15 November 2026**. [Sanitized evidence](harmony-second-test-readiness.json) records the exact dry-run plan, current metadata for both scenes, source timestamps and canonical-JSON SHA-256 hashes.

## Request-level checks

| Check | Result |
| --- | --- |
| Second source | **G4405182121-ASF**, revision **1**, GCOV |
| Acquisition UTC | **2026-11-04T23:29:18.000000Z – 2026-11-04T23:29:52.999342Z** |
| Exact collection | **C3622241360-ASF / NISAR_L2_GCOV_V1**, collection version **1** |
| Product version | **1.0.20** |
| Requested layer | **`/science/LSAR/GCOV/grids/frequencyA/HHHH`** |
| Variable concept | **V4137651715-ASF** |
| Associated service | **S4389714698-ASF**, **Harmony GDAL Adapter 4.0.0** |
| Service capability | Bounding-box and variable extraction, **HDF5 → COG**, MIME **`image/tiff`** |
| Requested WGS84 subset, W/S/E/N | **[88.75, 21.85, 88.78, 21.88]**, unchanged |
| Second metadata-polygon subset coverage | **100%**; actual polygon, not its bounding rectangle |
| Both metadata footprints' common subset coverage | **100%** of this small box |
| First reference | Revalidated cached COG, preserved and registered locally; hash verified |
| Execution flag | **`HARMONY_PROCESSING_ENABLED=false`** before and after |
| New local / remote jobs | **0 / 0**; local job count **1 before / 1 after** |

Exact second producer identifier:

```text
NISAR_L2_PR_GCOV_034_170_A_013_4005_DHDH_A_20261104T232918_20261104T232952_P05036_N_F_J_001
```

### Proposed processing request — constructed only, NOT SENT

```text
GET https://harmony.earthdata.nasa.gov/C3622241360-ASF/ogc-api-coverages/1.0.0/collections/V4137651715-ASF/coverage/rangeset?granuleId=G4405182121-ASF&subset=lon%2888.75%3A88.78%29&subset=lat%2821.85%3A21.88%29&format=image%2Ftiff&forceAsync=true&maxResults=1&ignoreErrors=false
```

One exact granule, one variable, asynchronous processing, maximum one input and `ignoreErrors=false`. No output CRS, resizing, resampling or reprojection parameters are added. The native second output grid must be measured after a later authorized job. The backend dry-run used:

```json
{"granule_id":"G4405182121-ASF","bbox":[88.75,21.85,88.78,21.88],"dry_run":true}
```

The retained study pilot is still **[88.4, 21.55, 89.1, 22.25]**. The 100% figure above applies only to the small extraction box, not the whole pilot. Neither location was changed.

## Geometry and polarization — PARTIALLY VERIFIED compatibility

Both exact granule records were refreshed from CMR, rather than assuming the previously saved metadata still applies. All known screening fields match; the existing screener's overall result remains **`unknown`**, with **`analysis_ready=false`**, because incidence angles are missing.

| Metadata | First: 23 October 2026 | Second: 4 November 2026 | Assessment |
| --- | --- | --- | --- |
| Instrument | L-SAR | L-SAR | Match |
| Pass | ASCENDING | ASCENDING | Match |
| Relative track / frame | 170 / 13 | 170 / 13 | Match |
| Look direction | LEFT | LEFT | Match |
| Absolute orbit | 6497 | 6670 | Different as expected for repeat acquisitions; not an incompatibility |
| Reported orbit type | MOE | MOE | Match; no orbit-accuracy inference |
| Frequencies | A and B | A and B | Match |
| Polarization in A | HH, HV | HH, HV | Match |
| Polarization in B | HH, HV | HH, HV | Match |
| Bandwidth in A / B | 40 / 5 MHz | 40 / 5 MHz | Match |
| Collection / product version | 1 / 1.0.20 | 1 / 1.0.20 | Match |
| PGE | GCOV_L_PGE, R05.03.2 | GCOV_L_PGE, R05.03.2 | Match |
| Numeric incidence angle | **Missing** | **Missing** | **UNKNOWN** |
| Actual output CRS / grid | EPSG:32645, 10 m, measured | **Not generated or measured** | **UNKNOWN** |

The acquisitions are 12 days apart at the same UTC start time. That does not prove matching tide height, soil/canopy moisture or incidence geometry. CMR's orbit-domain records provide the orbit numbers but no numeric local incidence/heading comparison. Equal track/frame/look metadata is a candidate-screening result, not per-pixel geometry equivalence.

### Variables and actual coverage: verification limits

**VERIFIED in current collection capabilities:** frequency A and B each advertise **HHHH** and **HVHV** diagonal covariance variables. The second scene's actual acquisition metadata lists HH/HV in both sub-bands. Its related visualization metadata includes the source-specific **`..._NATIVE_A_HHHH.png`** name. This corroborates the preferred frequency-A HH power layer.

**PARTIALLY VERIFIED:** The geometrically valid actual CMR polygon contains the full requested AOI. Its vertices in longitude/latitude are:

```text
[(90.46695,21.99603), (89.89525,24.07273),
 (87.41771,23.46222), (88.02476,21.39758),
 (90.46695,21.99603)]
```

**NOT VERIFIED:** Actual finite/unmasked positive second-scene radar pixels inside that AOI, source HDF5 array contents, focusing/subswath-mask coverage and the two scenes' common valid-data footprint. No image, HDF5 or second COG was downloaded. Thus the task's valid-pixel intersection cannot be established before extraction within this no-processing preparation; footprint containment is the available evidence, not a substitute pixel-validity claim.

[ASF's Harmony guide](https://nisar-docs.asf.alaska.edu/harmony/) confirms GCOV spatial/variable extraction to COG and warns that collection variable lists can include layers absent from an individual file. [ASF's GCOV guide](https://nisar-docs.asf.alaska.edu/gcov/) explains covariance terms and the separate mask/number-of-looks layers. The HHHH-only request is a technical extraction test, not a complete scientific QA package.

## First-scene preservation and reference reconciliation

The [spatial audit](harmony-spatial-validation.md) had passed, but deliberately left the original application job record at its historical `failed/extent_mismatch` state. Consequently the existing second-scene gate was initially locked. After the new dry-run and known-metadata checks passed, this preparation reconciled that existing first record with its actual validated COG; it did not bypass the gate.

- The original audit file remains intact at `artifacts/harmony-spatial-audit/first-real-cog.tif`.
- The exact original job-record bytes were backed up to [first-job-before-reference-registration.json](../artifacts/harmony-spatial-audit/first-job-before-reference-registration.json). Backup SHA-256: **`3d2991f364f5349e54db8124b215591315df58ca46276eae648d38049cdecddb`**.
- The existing first COG was inspected again with the actual observed source filename, copied into its normal managed-cache path, and both hashes checked. Audit and managed-reference copies retain SHA-256 **`f9f232f2743c2839835d59726456a7d2eaa3bf7c04188d5a2d5d87cfd650df5d`**, **380,888 bytes** each.
- The same local job **52a89f3e-c229-4900-9246-f39aa928278f** and same NASA job **c9136c2d-e1ec-4669-b738-4a455f3b8f66** now carry the successful local revalidation. The previous status/error and original-record hash are retained in an appended provenance field. The historical first-test and spatial-audit JSON evidence was not overwritten.
- The original raster, source IDs, requested bounds, creation/submission history and credentials were preserved. There is still only **one** local job record and no second job.
- The existing first-output eligibility gate is now satisfied, while the independent real-processing flag remains **false**. The dry-run's initial setup snapshot preceded reconciliation; the evidence records both the before/after gate values.

This is local, reversible reference preparation. It does not grant processing permission, establish scientific suitability or modify the dashboard design.

## Expected resources and remaining science gates

| Resource | Bound / estimate |
| --- | --- |
| Requested subset | Approximately **3.10 × 3.34 km**, same as first scene |
| Expected nominal posting | **10 m** from the 40 MHz frequency-A metadata; actual second grid not measured |
| Illustrative uncompressed samples | Approximately **414,160 bytes / 0.395 MiB** for one float32 layer, excluding COG overhead |
| Actual second COG file size | **Unknown**; no file or pixel statistics exist yet |
| Maximum returned file | **64 MiB** |
| Maximum local cache | **256 MiB** |
| Maximum job duration | **1,200 seconds / 20 minutes** |
| Concurrent jobs | **1** |
| Raster validation limit | **4,000,000 pixels** |
| Retention / maximum records | **24 hours / 50** under existing recovery safeguards |

Expected result after a separately authorized successful extraction: one HHHH COG plus job/status metadata. Its CRS, affine, dimensions, nodata, valid pixels, source identity, CRS-aware AOI validation and file size must be checked. Both actual files must then pass common-grid/common-valid-footprint checks; metadata overlap alone does not establish alignment.

**Scientific risks still unresolved:** incidence/local viewing geometry; second-scene valid-data and focusing/subswath QA; co-registration; actual grid alignment; tide and wetness differences; versioned baseline mangrove-mask intersection; radiometric consistency; uncertainty and independent ecological validation. No measured disturbance or two-date comparison was produced. Both observations' scientific suitability remains **unconfirmed**.

## Reproducibility and regression evidence

Fresh public sources:

- [Second granule](https://cmr.earthdata.nasa.gov/search/granules.umm_json?concept_id=G4405182121-ASF&page_size=1) and [first granule](https://cmr.earthdata.nasa.gov/search/granules.umm_json?concept_id=G4405780437-ASF&page_size=1).
- [Collection discovery](https://cmr.earthdata.nasa.gov/search/collections.umm_json?keyword=NISAR&page_size=200).
- [Current Harmony capabilities](https://harmony.earthdata.nasa.gov/capabilities?collectionId=C3622241360-ASF).
- [Associated service](https://cmr.earthdata.nasa.gov/search/services.umm_json?concept_id=S4389714698-ASF).

The helper `scripts/prepare_second_harmony_test.py` uses the existing dry-run builder with a transport that blocks authentication, processing/job-control paths and all downloads. Public CMR uses no bearer value in its isolated child process; the real `.env` and credentials are unchanged. It never starts a worker or queues a live job. The exact request is checked against the selected candidate/AOI/variable, and reference registration keeps an immutable backup and refuses to overwrite differing raster data.

- Backend regressions: **148 passed, 1 opt-in public-metadata test skipped**, **7.61 seconds**; existing Starlette/httpx warning only.
- Frontend regressions: **9 passed**, two files.
- New mocked tests cover the second-scene scope, explicit unknown incidence, rejection of known incompatibility, lossless/idempotent reference registration, conflicting data protection and disabled-processing enforcement.

**STOP: READY for an authorized extraction only.** Processing remains disabled. No second job ID, second COG, second-scene statistics or scientific comparison result exists. Wait for explicit user authorization before enabling or submitting the second job.
