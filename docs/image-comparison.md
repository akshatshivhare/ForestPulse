# Preloaded image comparison

Implemented and locally validated on 15 November 2026. This workflow is independent of NASA processing. No Harmony submission, authentication request, HDF5 download, second NISAR acquisition or study-area change was made for this work. `HARMONY_PROCESSING_ENABLED=false` remains unchanged.

## What is working

The default page (`/#images`, also `/` without a hash) loads a manifest-backed gallery and automatically compares its first compatible chronological pair. The original Overview, Explore Map, Date Comparison, Change Analytics, Reports, CMR APIs and gated Harmony architecture remain available. The image page makes no CMR or Harmony requests; its images, API, analysis and PDF run locally. External web fonts are optional styling dependencies, with local font fallbacks.

Working controls: available-image date dropdowns, gallery selection, noise filter, threshold, minimum region size, progress polling, keyboard/pointer before/after divider, side-by-side, heatmap, clickable region outlines/list and PDF download. Settings take effect on the next Compare action. A failed comparison returns a safe error; it never substitutes a fabricated result. Invalid/missing files, empty libraries, incompatible selections, uncertain registration, insufficient valid coverage, timeouts and expired reports have explicit states.

## Dataset and provenance

`datasets/catalog.json` is the curated registry. `datasets/sundarbans-simulated-v1/` contains four small generated assets: two RGBA PNGs and two georeferenced float32 power GeoTIFFs. These are **SIMULATED**, not satellite imagery or an observed Sundarbans landscape. Their dates, 1 January and 1 February 2026, are fictional scenario labels; `acquisition_date` is null. Sensor/source/calibration fields explicitly identify simulation. The fixed seed is 20261115. The RGB follow-up has three synthetic patches and a known translation (+5, -3 pixels); only patches exceeding the selected thresholds are flagged. The radar follow-up contains synthetic -5 dB and +4 dB patches plus generated noise. There are no invented accuracy scores.

One **REAL** gallery entry references the existing file `artifacts/harmony-spatial-audit/first-real-cog.tif`, without copying it or treating another cached copy as a second observation:

- Granule **G4405780437-ASF**, collection **C3622241360-ASF**, acquisition start **2026-10-23T23:29:18.000000Z**.
- Existing variable evidence: `/science/LSAR/GCOV/grids/frequencyA/HHHH`; EPSG:32645, 313 columns × 334 rows, 10 m; prior spatial-validation evidence is retained in `harmony-spatial-validation.md`.
- Preserved SHA-256: `f9f232f2743c2839835d59726456a7d2eaa3bf7c04188d5a2d5d87cfd650df5d`.
- The COG has no explicit Rasterio band description or units. Prior evidence establishes linear HHHH power and variable identity; it does **not** independently establish a gamma0 normalization/calibration. Accordingly its manifest says `linear_HHHH_power` and `normalization_not_independently_verified`. It can be previewed, but cannot enter a calibrated gamma0 comparison under the current gate.
- No second real matched COG is locally available. Real two-date environmental comparison is **PENDING**, not simulated as NISAR. If the real file is absent on another checkout, this entry is unavailable; the four simulated images still work.

The manifest is separate from the NASA discovery catalog. Scenario dates never enter CMR results or the original acquisition calendars.

## Comparison method and limitations

Compatibility requires distinct chronological images, matching curated `area_id`, `pair_group`, sensor, data type and real/simulated provenance. Radar additionally requires matching identified calibration, frequency and polarization and supported power units (`gamma0_linear_power` or `gamma0_db`). Curated metadata is an explicit trust boundary: adding unrelated photos with false locality metadata is unsupported. There is no arbitrary file/URL upload or remote ingestion endpoint.

For georeferenced inputs, the reference must be north-up. Rasterio transforms the second extent into the reference CRS, requires at least 95% mutual envelope coverage and derives an intersecting grid on reference pixel edges. Both sources are reprojected onto that grid; nodata/NaN/nonpositive power and nonoverlap are excluded. The final valid comparison footprint is the **intersection of valid pixel masks**, not the outer rectangle. A different CRS is supported when its transformed coverage is compatible; displaced or insufficiently overlapping imagery is rejected. Coordinate alignment does not verify sensor geolocation accuracy. The current 95% coverage gate is conservative and intentionally rejects broad/narrow mismatched crops.

Non-georeferenced RGB uses ORB descriptors, Hamming matches (ratio <0.75) and a RANSAC partial-affine transform from follow-up to baseline. Gates: >=12 inliers, >=0.35 inlier ratio, residual RMSE <=2.5 pixels, features distributed across >=4 of 9 reference cells, scale 0.8–1.25 and >=60% baseline valid overlap. Confidence is a **heuristic category**, not measured detection accuracy: high requires >=60 inliers, >=0.7 ratio and <=1.5 px RMSE; otherwise an accepted solution is moderate. Partial-affine registration does not handle arbitrary perspective/terrain parallax. Feature matches establish visual overlap, not geographic coordinates or ecological truth. Radar without georeferencing is rejected rather than feature-registering speckle.

RGB change is CIE76 distance in CIELAB computed from uint8 display RGB. It is a visual indicator affected by illumination, display stretch, compression, resampling and registration residuals, **not reflectance, radar backscatter or confirmed forest change**. Calibrated radar-power mode converts dB source values to linear power before bilinear reprojection, then calculates `10 log10(after / before)` on shared positive valid pixels. It never subtracts preview images. The checked radar example is synthetic; the mathematical path is unit-tested with a known factor-of-two power ratio (3.0103 dB), but no real two-scene science validation has occurred.

Optional filtering uses a valid-weighted 3×3 or 5×5 Gaussian on the signed dB signal (or RGB magnitude). Thresholding uses absolute filtered magnitude, followed by 8-connected components and a configurable minimum pixel count. Defaults: RGB 15 CIE76 units; radar 3 dB; 3×3 filter; >=64 pixels per region. Summary mean/95th percentile use unfiltered differences; region magnitudes use filtered differences. Opposing signed radar changes can cancel inside the noise filter. These choices are illustrative, not statistically calibrated detection thresholds or a SAR speckle-analysis method.

Binary change/valid masks preserve actual pixel counts and holes. Up to 50 largest approximate outer region outlines are returned, and eight are listed in the panel/PDF. These outlines are image-space indicators, not mangrove boundaries; they may omit holes and minor contour details. Heatmap color saturates at the larger of threshold and the 99th percentile; it is not a probability. No hectares of forest lost, classifier, accuracy estimate, ecological attribution or confirmed deforestation is calculated. Valid comparison area is reported in shared pixels and mask, with CRS/grid extent for georeferenced inputs; RGB has no defensible ground-area estimate.

Before real scientific use: independently verify radiometric normalization/units and variable identity, repeat orbit/track/frame/pass and incidence geometry, focusing/subswath/quality masks, pixel-grid registration and resampling uncertainty, acquisition tide and season, a validated baseline mangrove mask, suitable speckle/radiometric harmonization, cloud/shadow screening for optical inputs, and independent reference observations. A common grid alone does not establish scientific suitability.

## Local setup and demo

Dependencies are in `backend/requirements.txt` and the exact Windows lock. Existing credentials can stay in `.env`; this workflow never reads or sends them. Keep processing false. From the repository root:

```powershell
uv pip install --python .venv\Scripts\python.exe -r backend\requirements-lock.txt
# Only if the four included simulated assets need regeneration:
.venv\Scripts\python.exe -m scripts.generate_comparison_demo
# Terminal 1
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
# Terminal 2
npm.cmd run dev
```

Open `http://127.0.0.1:5173/#images`. The default RGB comparison runs automatically. Drag the divider, open Heatmap or Regions, and download the report. To exercise the common-grid radar path, choose the two **Simulated radar power** entries and click Compare. Selecting the sole real NISAR image with a simulated follow-up produces a compatibility warning and disables submission.

The generator is an explicit maintenance command that rewrites the four fixtures and demo catalog. Do not rerun it over a curated expanded manifest without first preserving that manifest. Adding new images does not require changes to engine code: place files under a workspace dataset folder and add entries to `catalog.json` with unique `[a-z0-9-]` IDs (1–64 characters), name, relative file path, source, sensor, area/area_id, pair_group, data_type, units, boolean is_simulated and ISO `YYYY-MM-DD` acquisition_date (real) or scenario_date (simulated, acquisition_date null). Follow the current entries for calibration/frequency/polarization and provenance. Use a new pair_group for different geometry/processing/variable. Record actual source, license, timestamps, units/calibration verification and invalid-value semantics; never fill missing scientific metadata with guesses. Reopening the page reads the updated manifest. The current calibrated-radar comparison gate deliberately excludes unknown normalizations.

Accepted local formats: uint8 RGB/RGBA PNG/JPEG or 3/4-band uint8 GeoTIFF; one-band numeric power GeoTIFF. PNG alpha / GeoTIFF masks / nodata / nonfinite values are respected; optional `nodata_rgb` can specify a known RGB invalid value. Black is not automatically nodata. No raw HDF5 support is added.

## API and resource bounds

| Route | Purpose |
| --- | --- |
| `GET /api/images` | Public manifest metadata, availability and available file-backed dates |
| `GET /api/images/{id}/preview` | Bounded local preview |
| `POST /api/image-comparisons` | Queue local comparison (202) |
| `GET /api/image-comparisons/{uuid}` | Stage, progress, completed result or sanitized failure |
| `GET /api/image-comparisons/{uuid}/assets/{name}` | Completed before/after/heatmap/overlay/mask/valid PNG or report PDF |

Example POST: `{"before_id":"sim-rgb-before","after_id":"sim-rgb-after","threshold":15,"noise_radius":1,"min_region_pixels":64}`. No credentials or source URLs are accepted. Additional request fields are rejected without echoing payloads. Local IDs and asset names are constrained; paths cannot escape the workspace/cache. No server filesystem paths, credentials, authentication cookies or signed download URLs are returned.

Each source <=32 MiB and <=1,048,576 pixels; manifest <=100 entries. Local processing is serialized, with at most two admitted queued/running jobs. A cooperative 30-second processing deadline is checked between stages; native bounded operations are not force-killed mid-call. Job cache is `artifacts/image-comparisons/`: 24-hour access lifetime, 20 completed-job cap and 256 MiB quota with a 16 MiB reservation per admission. Expired/oldest completed entries are removed during new submissions; stale queued/running states are marked interrupted. Reports can be recreated by rerunning the local comparison. Previews are <=480 pixels on their longest side, at most one cached PNG per manifest entry. A single backend process is supported; in-process locks are not a distributed queue. Deployments needing multiple workers or untrusted uploads require a separate queue, stronger isolation and access control.

## Actual validation evidence

`docs/image-comparison-validation.json` contains actual computed results from the four **simulated** local assets, including masks/regions, dates, parameters and measured registration diagnostics. It is not NASA or environmental evidence.

| Local run | Shared valid pixels | Flagged pixels | Regions | Meaning |
| --- | ---: | ---: | ---: | --- |
| Simulated RGB, default settings | 185,294 | 5,628 (3.0373%) | 2 | Synthetic visual differences only |
| Simulated radar, default settings | 186,000 | 6,064 (3.2602%) | 2 | Synthetic dB differences only |

The RGB registration measured 2,120 matches, 2,003 inliers, 0.8185 px residual RMSE and translation approximately (-4.912, +2.977) px against the generator's known (-5, +3) px inverse shift. The confidence category is high under the stated heuristic, not a ground-truth geographic accuracy estimate. The radar common grid is EPSG:32645, 512×384, approximately 6.1133×8.6979 m **synthetic** pixels; it is not the genuine 10 m NISAR raster.

Backend tests cover gallery provenance/dates, compatibility, units, masks, filters, tiny/empty overlap, feature registration, unrelated images, shifted geospatial grids, wrong location/mixed georeferencing, dB conversion, both full local API/PDF pipelines, safe failures, rejected credential-shaped inputs, path confinement and cache expiry. Existing CMR/Harmony regressions remain intact. Browser checks exercised default completion, all four viewer modes, keyboard divider changes, both simulated pairs, loaded real/simulated thumbnails and responsive mobile controls. PDF pages were rasterized and visually inspected.

Commands: `.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider`, `npm.cmd test`, `npm.cmd run build`. Final full validation: **172 passed, 1 skipped** backend; **14 passed** frontend; production build passed. The existing optional public-metadata integration test is skipped without its opt-in flag. Warnings: upstream Starlette/httpx TestClient deprecation and Vite's existing large bundle advisory. No credential-dependent or Harmony live processing test was run.

Method references: [OpenCV feature matching](https://docs.opencv.org/4.x/dc/dc3/tutorial_py_matcher.html), [Rasterio reprojection](https://rasterio.readthedocs.io/en/stable/topics/reproject.html), [ReportLab Platypus](https://docs.reportlab.com/reportlab/userguide/ch5_platypus/).

Final browser-driven validation exposed a Windows `PermissionError` during atomic progress-state replacement. State reads/writes now share an in-process lock and replacement retries are bounded to six attempts / 620 ms total wait. This retries only a small local journal write, never NASA or image-processing submission. A regression test reproduces the transient lock, and jobs with no updates after 90 seconds return an interrupted failure rather than perpetual running. After the fix, three actual HTTP local comparison runs completed in 1.09 s (RGB), 1.03 s (simulated radar) and 1.00 s (RGB) under frequent status polling. All returned PDF HTTP 200; the browser also successfully downloaded its report. Final full suite: 172 backend passed / 1 skipped; 14 frontend passed; production build passed.
