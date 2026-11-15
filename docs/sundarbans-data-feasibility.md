# Sundarbans real-data feasibility audit

Audit date: **14 November 2026**. Acquisition times below are **UTC**, copied from NASA CMR temporal metadata. Local dates can differ: 23:29 UTC is 04:59 IST the following day. This audit does not change the selected location or implement Harmony/raster processing.

## Decision and verification labels

- **VERIFIED:** Genuine repeat GCOV observations exist over the Indian Sundarbans. The preferred pair is **G4405780437-ASF / G4405182121-ASF**, acquired **23 October / 4 November 2026**, track 170, ascending, frame 13. Both have matching published acquisition-mode metadata and positive shared pilot coverage. An independent descending repeat pair is documented below.
- **VERIFIED:** The validated collection is associated with a live Harmony service advertising bounding-box and variable subsetting, HDF5-to-COG conversion, and suitable output projections. The specific proposed backscatter variables are advertised and both primary granules list corresponding browse-layer artifacts.
- **PARTIALLY VERIFIED:** These are potentially compatible, technically promising candidates for a bounded Phase 2 extraction experiment. The existing conservative screener returns **`unknown`**, because CMR does not report incidence angles. Footprints establish metadata coverage, not valid mangrove pixels.
- **NOT VERIFIED:** No scientifically ready pair is confirmed. No authenticated transformation, successful scene-specific COG, grid alignment, numeric incidence comparison, tide match, valid-pixel coverage, baseline-mask intersection, or mangrove disturbance result has been established. No Harmony job was submitted.

**Recommendation:** Keep the current pilot and proceed next only with a staged extraction/metadata-validation milestone. Do not yet claim change-detection feasibility at pixel level or measured forest loss. Candidate availability is sufficient to investigate Phase 2; scientific readiness remains conditional.

## Existing project inspected

Reviewed [README](../README.md), [original NASA verification](nasa-verification.json), [CMR adapter](../backend/app/cmr.py), [configuration](../backend/app/config.py), [normalization and screening](../backend/app/science.py), [API routes](../backend/app/main.py), and their tests.

The application dynamically discovers collections, retains acquisition timestamps, paginates scenes, uses actual CMR polygons where available, preserves unknown metadata, and always sets `analysis_ready: false`. Product, maturity/version, band, frequency/polarization/bandwidth, pass, relative track, frame, look direction, incidence and shared AOI coverage are screened. Absolute orbit numbers correctly need not match repeat acquisitions.

The original verification paired G4405182121-ASF with G4411480194-ASF: a track-170 observation and a track-98 observation. Its incompatible result is appropriate; that comparison was not a search for the best repeat pair. No application discovery fix is required for this audit. Collection discovery remains bounded to 200 keyword matches; all returned GCOV collections were examined. Coverage remains the application's approximate cylindrical equal-area polygon calculation; no precise geodesic or raster-validity claim is made.

**Location retained:** `[88.4, 21.55, 89.1, 22.25]` in west/south/east/north order, WGS84. No application code, frontend defaults, or Phase 1 verification evidence was replaced.

## Live CMR search and reproducibility — VERIFIED

Public collection discovery used [CMR collections](https://cmr.earthdata.nasa.gov/search/collections.umm_json?keyword=NISAR&page_size=200). Searches used no temporal restriction, so the results are catalog holdings at retrieval time, not a promised continuous acquisition series.

| Collection | Published title / maturity | Version | Existing pilot hits | Wider regional hits / loaded |
| --- | --- | --- | ---: | ---: |
| C3622241360-ASF / NISAR_L2_GCOV_V1 | NISAR Validated Geocoded Polarimetric Covariance Product | 1 | 10 | 14 / 14 |
| C2854338529-ASF / NISAR_L2_GCOV_PROVISIONAL_V1 | NISAR Provisional Geocoded Polarimetric Covariance Product | 1 | 66 | 94 / 94 |
| C3622214170-ASF / NISAR_L2_GCOV_BETA_V1 | NISAR Beta Geocoded Polarimetric Covariance Product | 1 | 5 | 10 / 10 |

The wider search envelope was `[88.15, 21.45, 89.2, 22.5]`, used only to examine nearby alternatives; it was not selected as the app AOI. All regional and pilot results fit one 200-record page. Counts are granules, not independent dates, forest-covered scenes or scientifically usable observations. Some regional granules have zero pilot intersection.

Example exact searches:

- [Validated collection, original pilot](https://cmr.earthdata.nasa.gov/search/granules.umm_json?collection_concept_id=C3622241360-ASF&bounding_box=88.4,21.55,89.1,22.25&page_size=200&page_num=1&sort_key=-start_date).
- [Validated collection, wider search envelope](https://cmr.earthdata.nasa.gov/search/granules.umm_json?collection_concept_id=C3622241360-ASF&bounding_box=88.15,21.45,89.2,22.5&page_size=200&page_num=1&sort_key=-start_date).

[Evidence manifest](sundarbans-evidence/manifest.json) records exact URLs, UTC retrieval times, HTTP status and SHA-256 hashes of stored response files. [Summary](sundarbans-evidence/summary.json) contains AOIs, collection counts, like-metadata groups, candidate pairs, unresolved checks and shared coverage. Raw UMM responses, individual candidate records, service/variable associations and live capabilities are stored alongside it. Derived normalized files are identified by `-normalized.json`; their polygons and fields are traceable to the raw responses. Source/derived coverage is reproducible with the existing science functions.

Run the read-only audit from the project root:

```powershell
.venv\Scripts\python.exe -m scripts.audit_sundarbans
```

The audit helper uses public metadata requests without Earthdata credentials, retrieves no radar imagery and submits no jobs. It refreshes this separate evidence directory; future catalog revisions can change counts and hashes. Page-number harvests are not transactional snapshots; use CMR Search After for future long-running harvests. See the [official CMR API documentation](https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html).

## Preferred repeat pair — VERIFIED observations, PARTIALLY VERIFIED compatibility

| Metadata field | Baseline | Comparison |
| --- | --- | --- |
| CMR concept ID / source | [G4405780437-ASF](https://cmr.earthdata.nasa.gov/search/concepts/G4405780437-ASF.umm_json) | [G4405182121-ASF](https://cmr.earthdata.nasa.gov/search/concepts/G4405182121-ASF.umm_json) |
| Acquisition beginning | 2026-10-23T23:29:18.000000Z | 2026-11-04T23:29:18.000000Z |
| Acquisition ending | 2026-10-23T23:29:52.999342Z | 2026-11-04T23:29:52.999342Z |
| Absolute orbit | 6497 | 6670 |
| Approximate pilot coverage individually | 91.49% | 94.85% |

Both records explicitly report: collection **C3622241360-ASF**, short name **NISAR_L2_GCOV_V1**, collection version **1**, product **GCOV**, product version **1.0.20**, instrument **L-SAR**, pass **ASCENDING**, relative track **170**, frame **13**, look direction **LEFT**, frequency A **HH/HV, 40 MHz**, frequency B **HH/HV, 5 MHz**, `FULL_FRAME=TRUE`, `ORBIT_TYPE=MOE`, processing center **JPL**, PGE **GCOV_L_PGE R05.03.2**. The published stack is `170_A_013`. These fields come from metadata, not guessed filename parsing. MOE is retained as the reported orbit-type value; precise-orbit performance is not established.

Exact producer granule identifiers (`GranuleUR`):

```text
NISAR_L2_PR_GCOV_033_170_A_013_4005_DHDH_A_20261023T232918_20261023T232952_P05036_N_F_J_001
NISAR_L2_PR_GCOV_034_170_A_013_4005_DHDH_A_20261104T232918_20261104T232952_P05036_N_F_J_001
```

Published CMR footprint rings, copied as **longitude,latitude**, WGS84, including closing point:

```text
G4405780437-ASF:
[(90.45895,22.02588), (89.88696,24.10253), (87.40878,23.49180),
 (88.01621,21.42722), (90.45895,22.02588)]

G4405182121-ASF:
[(90.46695,21.99603), (89.89525,24.07273), (87.41771,23.46222),
 (88.02476,21.39758), (90.46695,21.99603)]
```

These are actual metadata polygons, not bounding-envelope substitutes. Shared intersection inside the original pilot is approximately **91.49% of pilot area**. All known screening fields match; incidence is null for both, giving `status: unknown` and `analysis_ready: false`. A full-frame flag does not establish valid samples everywhere within the footprint.

CMR also lists frequency-A HHHH and HVHV browse PNG artifacts for each scene, corroborating the expected layers. This is supporting metadata evidence, not inspection of the HDF5 arrays or proof that Harmony will return every requested variable. The baseline HDF5 alone is listed as **6,593,445,888 bytes**; a small server-side subset is preferable for the initial experiment.

## Independent repeat pair and rejected choices

**VERIFIED observations / PARTIALLY VERIFIED compatibility:**

| Field | Baseline | Comparison |
| --- | --- | --- |
| Concept ID / source | [G4404467079-ASF](https://cmr.earthdata.nasa.gov/search/concepts/G4404467079-ASF.umm_json) | [G4409021162-ASF](https://cmr.earthdata.nasa.gov/search/concepts/G4409021162-ASF.umm_json) |
| Beginning UTC | 2026-10-25T12:43:14.000000Z | 2026-11-06T12:43:14.000000Z |
| Ending UTC | 2026-10-25T12:43:47.999342Z | 2026-11-06T12:43:48.999342Z |
| Absolute orbit | 6519 | 6692 |
| Individual pilot coverage | 70.47% | 75.89% |

Both use the same validated collection/version, GCOV product version 1.0.20, L-SAR, A/B, HH/HV in both frequencies, A=40/B=5 MHz, LEFT look, MOE and PGE R05.03.2 as the preferred pair. This pair is **DESCENDING, track 19, frame 77**, stack `019_D_077`. Shared pilot coverage is **70.47%**; missing incidence again leaves `unknown`.

```text
NISAR_L2_PR_GCOV_034_019_D_077_4005_DHDH_A_20261025T124314_20261025T124347_P05036_N_F_J_001
NISAR_L2_PR_GCOV_035_019_D_077_4005_DHDH_A_20261106T124314_20261106T124348_P05036_N_F_J_001

G4404467079-ASF footprint:
[(87.72083,24.16284), (87.16275,22.14600), (89.52241,21.56677),
 (90.11312,23.57238), (87.72083,24.16284)]

G4409021162-ASF footprint:
[(87.72845,24.18640), (87.15364,22.11032), (89.51280,21.53124),
 (90.12085,23.59585), (87.72845,24.18640)]
```

Do not directly subtract ascending track 170 and descending track 19 data. Treat them as separate series with separate viewing geometry, then assess spatial agreement of independently supported anomalies.

**VERIFIED alternatives and exclusions:**

- Track 98/frame 12: G4404806602-ASF (2026-10-30T23:37:15Z) / G4411480194-ASF (2026-11-11T23:37:15Z) is another HH/HV repeat candidate, but shares only **4.29%** of the original pilot. It fully covers the proposed Lothian box. Incidence remains unknown.
- Track 98/frame 13: G4405152572-ASF / G4411494688-ASF matches repeat-mode metadata but shares **0%** of the original pilot. It is incompatible for that AOI; its presence in the wider search does not rescue pilot coverage.
- Provisional track 170/frame 13: G4332482072-ASF (2026-09-29T23:29:17Z) / G4363245985-ASF (2026-10-11T23:29:17Z) shares **95.38%** of the pilot with like-mode metadata; incidence is unknown. This is a verified catalog alternative for exploratory history, with extra maturity/calibration risk. Do not splice it into a validated baseline without checking processing consistency.
- Wider-search beta observations intersect Lothian but none intersect the proposed central or Sajnekhali boxes. Beta data is not the preferred baseline. Multiple regional modes include VV/VH and quad-polarization; membership in GCOV alone does not establish compatibility.

Alternative granules above are present in the saved regional UMM responses and normalized records; they were not all fetched individually. Only the four primary/independent candidate concept records were individually rechecked.

## Mangrove-focused AOIs examined

The Indian Sundarbans' mangrove character is established by [UNESCO's Sundarbans National Park description](https://whc.unesco.org/en/list/452/). The [Lothian field/remote-sensing study](https://isprs-archives.copernicus.org/articles/XLIX-B3-2026/923/2026/) independently identifies that island as a mangrove study area. These support regional/site relevance; they do not turn rectangles into authoritative mangrove boundaries.

| AOI, WGS84 west/south/east/north | Status | Preferred track-170 pair shared area | Independent track-19 pair shared area |
| --- | --- | ---: | ---: |
| Existing pilot `[88.4,21.55,89.1,22.25]` | **Selected; unchanged** | 91.49% | 70.47% |
| Central forest proposal `[88.65,21.7,88.9,21.95]` | Inside existing pilot; recommended first subset candidate | 100% | 79.89% |
| Sajnekhali-sector proposal `[88.75,22.05,88.9,22.2]` | Inside existing pilot; separate smaller candidate | 100% | 100% |
| Lothian-sector proposal `[88.28,21.62,88.4,21.75]` | **West of selected pilot**; explicit location alternative | 100% | 0% |

**VERIFIED:** Calculated metadata-footprint coverage of these explicit boxes. **PARTIALLY VERIFIED:** Geographic suitability in mangrove-rich sectors. **NOT VERIFIED:** Their mangrove fractions, exact sanctuary/island boundaries, legal boundaries, or usable forest area. All three new rectangles are analyst proposals, not observed NASA polygons or already-selected locations. The source masks must clip out channels, mudflats, settlements and farmland. Retain the pilot because its coverage is adequate for investigation; adopting a different selected AOI should be an explicit product decision.

## Harmony feasibility

### Collection and variable support — VERIFIED

All three live [collection capability responses](https://harmony.earthdata.nasa.gov/capabilities?collectionId=C3622241360-ASF) advertise a service chain containing **nasa/harmony-gdal-adapter**. The associated [UMM-S service S4389714698-ASF](https://cmr.earthdata.nasa.gov/search/concepts/S4389714698-ASF.umm_json), named Harmony GDAL Adapter, version 4.0.0, explicitly declares HDF5 input and **COG output**. Capabilities expose `GEOTIFF`, MIME **image/tiff**, bounding-box and variable subsetting, and reprojection including **EPSG:32645**. Shape/dimension subsetting, temporal subsetting, averaging and concatenation are not advertised for this chain. Temporal scene selection is distinct from trimming a time dimension.

Select variables explicitly, using the collection's associated variable IDs:

| HDF5 variable | CMR variable concept | Purpose |
| --- | --- | --- |
| `/science/LSAR/GCOV/grids/frequencyA/HHHH` | V4137651715-ASF | HH diagonal backscatter power |
| `/science/LSAR/GCOV/grids/frequencyA/HVHV` | V4137651725-ASF | HV diagonal backscatter power |
| `/science/LSAR/GCOV/grids/frequencyA/mask` | V4137651736-ASF | Valid-sample / subswath mask |
| `/science/LSAR/GCOV/grids/frequencyA/numberOfLooks` | V4137651748-ASF | Multilooking context |

Frequency B counterparts are also advertised but should be evaluated separately. Current capabilities additionally list **asf/nisar-py** for PNG browse output; do not mistake that service for analytical COG extraction.

The [official ASF NISAR Harmony guide](https://nisar-docs.asf.alaska.edu/harmony/) confirms spatial/variable extraction to COG. It also explains that a collection's variable list spans possible acquisition modes: absent requested layers may be skipped. Consequently collection support is established, while successful extraction of these specific scenes is **NOT VERIFIED**. Their HH/HV attributes and listed browse artifacts support the choice of HHHH/HVHV; actual output validation is still required.

### Authorization and asynchronous operation

The [official Harmony API documentation](https://harmony.earthdata.nasa.gov/docs) requires Earthdata Login for transformations and supports an `Authorization: Bearer` header. Public CMR/capability success does not establish authenticated source-data or job access. Keep credentials on the server; no token is required to reproduce the public audit.

**VERIFIED access limitation:** Unauthenticated GETs to each preferred granule's exact published `.h5.iso.xml` and `_QA_SUMMARY.csv` links returned **HTTP 302**, not metadata/QA contents. Redirects were deliberately not followed, and no authenticated retrieval was attempted. The four response/status records are included in the manifest. Thus this audit has not inspected the scene-specific ancillary geometry or QA; a redirect is not evidence of either good or bad scene quality.

For a later bounded experiment, use the OGC coverages route with explicit variable concepts, **one exact `granuleId` per request**, `subset=lon(88.65:88.9)`, `subset=lat(21.7:21.95)`, `format=image/tiff`, `forceAsync=true`, `maxResults=1`, and `ignoreErrors=false`. Use native projection first; request EPSG:32645 only if source grids require it and validate actual output alignment. These are **proposed request parameters, not a submitted or acceptance-tested request**. Check syntax against live API/Harmony-Py before coding.

Future job handling must retain the returned job reference, poll `/jobs/{jobID}`, surface failure/cancellation/paused states, and validate completed result/STAC links. Preserve expiration/provenance and retrieve outputs before cleanup. Do not equate HTTP submission, progress 100, or partial outputs with a successful complete variable set. No job ID or result URL exists from this audit.

### Important geometry gap

**NOT VERIFIED:** Numeric incidence geometry for any candidate. The [ASF metadata guide](https://nisar-docs.asf.alaska.edu/metadata/) describes `/science/LSAR/GCOV/metadata/radarGrid/incidenceAngle` as a height-dependent metadata cube. This path is absent from the 20 advertised GCOV variables, which concern gridded 2D science layers. Do not assume the current extraction service can turn that cube into a COG. A separate authenticated metadata-reading/interpolation path must be demonstrated before incidence screening can pass. Treat ellipsoid incidence and local terrain incidence as distinct quantities.

## Preliminary scientific comparison strategy — proposed, not implemented

1. **Fix the baseline population.** Use the pre-acquisition **2025 epoch of GMW v4.1.12** as the preferred contemporary extent prior. [JAXA's current dataset documentation](https://www.eorc.jaxa.jp/ALOS/en/dataset/gmw_e.htm) verifies its availability: 41 annual bands, 1985–2025, 30 m, geographic GeoTIFF; band 41 is 2025. Retain version, epoch, license and checksum. Global accuracy is not local ground truth. If unavailable locally, the published [GMW v3.0 2020 extent](https://www.mdpi.com/2072-4292/14/15/3657) is a documented older fallback requiring stronger contemporary review. No mask was downloaded or intersected in this audit. Use a fixed baseline mask for loss investigation; a baseline-only mask cannot measure gains outside it.
2. **Use one repeat geometry at a time.** Start with the track-170 pair, frequency A HHHH/HVHV, same-version processing. The [GCOV product guide](https://nisar-docs.asf.alaska.edu/gcov/) describes diagonal values as terrain-corrected gamma-zero power. At 40 MHz it documents 10 m posting, versus 80 m for 5 MHz frequency B; these are expected specifications, **not measured grid properties of the candidates**. Confirm CRS, transform, dimensions, spacing and normalization from the actual outputs. Do not resample B onto A and imply equal information content, or apply RTC a second time blindly.
3. **Gate on quality and alignment.** Require finite, valid power in both dates, inspect QA summaries/reports, number of looks, noise/RFI/calibration evidence, focusing and edge validity. The [CMR mask definition](https://cmr.earthdata.nasa.gov/search/concepts/V4137651736-ASF.umm_json) marks partially focused/invalid averaging ensembles as 0 and samples outside acquisition extent as 255; neither represents usable forest. Decode documented valid subswath classes, rather than using `mask != 0`. Handle layover/shadow where applicable and validate co-registration against stable features. Distinguish posting from effective spatial resolution. Forest coverage is the intersection of valid samples, the approved AOI and the baseline mask, not the table's footprint percentage.
4. **Resolve tides before ecological interpretation.** Obtain spatially relevant gauge or validated tide-model water levels at both exact UTC acquisitions, with model/version, datum, uncertainty and local propagation lag. A repeat local overpass time does not imply matching tide height or stage. Evaluate rising/falling tide, recent rainfall, wetness and seasonal effects; exclude or separately analyze creek edges and inundated zones. No tide heights or allowable mismatch threshold are invented here. [The Sundarbans L-band SAR study](https://www.mdpi.com/2072-4292/5/1/224) documents tide/soil-moisture and registration confounding and differing HH/HV sensitivities. Establish local tolerances empirically before approving this pair.
5. **Resolve incidence, orbit and calibration.** Read candidate incidence cubes and coordinates, interpolate at documented terrain/ellipsoid heights onto the common analysis grid, and compare corresponding forest pixels. Check QA, orbit accuracy and processing versions, and use stable forest controls to characterize geometry-related variation. Track/frame equality alone does not establish identical incidence or radiometry. Do not fabricate a universal angular tolerance.
6. **Start with anomalies, then validate disturbance.** Aggregate/denoise valid linear power at a documented common support; retain spatial detail needed for narrow islands. Compute `10*log10(P_comparison/P_baseline)` for positive HH and HV power, with support/uncertainty and optional polarization-ratio change. A negative radar anomaly is not automatically canopy loss; flooding can alter scattering and changes need not have a unique sign. Select thresholds from stable controls and independently validated examples, not arbitrary dB cuts or the older study's settings. Seek persistence across additional same-track dates, optical observations and field/high-resolution evidence. The two-date experiment cannot by itself establish cause, biomass loss, accuracy or an event date. No particular disturbance between these acquisitions is verified.

## Blocking risks and exact Phase 2 handoff

| Gate | Audit status | Required next evidence |
| --- | --- | --- |
| Real observations / repeat-mode match | **VERIFIED** | Retain/recheck exact concept revisions and raw metadata |
| Suitable mangrove pixels | **PARTIALLY VERIFIED** | Approve AOI; intersect a versioned baseline mask and two-date valid pixels |
| Collection extraction capability | **VERIFIED** | Retain live service/variable associations |
| Candidate-specific COG output / EDL access | **NOT VERIFIED** | Successful authenticated bounded jobs; verify every expected asset |
| Incidence / grid / radiometric equivalence | **NOT VERIFIED** | Read real metadata cubes, grids and QA; quantify differences |
| Tide / wetness comparability | **NOT VERIFIED** | Acquisition-time gauge/model evidence and defensible local tolerance |
| Disturbance signal or validation accuracy | **NOT VERIFIED** | Persistent anomaly plus independent validation and uncertainty |

Recommended implementation sequence for a **future** Phase 2 task:

1. Preserve Phase 1 API behavior. Record an explicit user-visible AOI choice; start with the central proposal as a subset within the retained pilot, subject to mask review. Freeze the two preferred granule IDs, collection, UTC times, revisions, expected variables and evidence hashes in an experiment record.
2. Add a server-side, collection-aware capability/variable resolver and bounded authenticated extraction worker. Demonstrate the incidence-metadata access path first or alongside extraction; inability to retrieve usable geometry remains a stop gate for scientific comparison.
3. Submit one small async request per preferred granule for A/HHHH, A/HVHV, A/mask and A/numberOfLooks. Use the documented subset parameters; enforce resource limits and clear auth errors. Do not select `all` or rely on broad date searches to select scenes.
4. Implement persisted submit/status/cancel/result handling, bounded polling/backoff and output-expiration handling. Only then validate output COG structure, data types, CRS, transform, nodata, extent and all expected layer names. A skipped mask/backscatter layer must fail the experiment even if Harmony calls the job successful.
5. Retrieve actual QA/geometry; establish the common valid mangrove footprint, co-registration and tide screening. Produce a written go/no-go decision. Keep `analysis_ready: false` until these checks and the scientific pipeline are implemented and validated.
6. After passing the gates, implement the preliminary anomaly workflow and independent validation as a separate milestone. Keep the descending pair as an independent follow-up, rather than mixing its pixels into the ascending baseline. If the primary pair fails tides/quality, screen the documented alternate pairs and other actual same-track dates; no alternate is pre-approved scientifically.

This audit adds documentation, public metadata evidence and a reproducible read-only helper. It does **not** begin the integration above or real change detection.

## Validation performed

- Backend: `.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider` — **20 passed**, with the existing Starlette/httpx deprecation warning. The sandboxed run stalled on local TestClient requests; the completed run outside the sandbox passed.
- Frontend: `npm.cmd test` — **5 passed**.
- Public evidence: all **24** stored response hashes and expected HTTP statuses checked; four candidate single-record metadata documents cross-checked against regional-search fields; both selected repeat pairs retain **unknown incidence**, with `analysis_ready: false`.
- No application runtime code was changed. A production build was not repeated for this documentation/audit-helper change.
