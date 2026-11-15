# ForestPulse

**Deployment preparation:** use the [Vercel + Render deployment guide](docs/deployment.md). Both hosting roots are the repository root. Production builds require `VITE_API_BASE_URL` set to the actual Render HTTPS origin; local `npm run dev` still supports the development proxy. No public deployment is claimed. Production mode keeps NASA Harmony disabled and private job endpoints blocked.

A NASA–ISRO NISAR mangrove monitoring prototype with Phase 1 discovery and gated Phase 2B extraction for **Sundarbans, West Bengal, India**. This is an independent prototype, not an official NASA or ISRO application.

**Primary demo: Image Comparison.** Open `/#images` (the default page) for a preloaded gallery, automatic two-image alignment/comparison, before/after slider, side-by-side, heatmap, highlighted regions and downloadable detailed PDF. No NASA connection or credentials are needed. Two explicitly **SIMULATED** matched pairs exercise RGB visual difference and georeferenced radar-power comparison. Scenario dates are not acquisitions. The one genuine cached NISAR observation is separately labeled; no second real observation has been invented. See [setup, methods and validation](docs/image-comparison.md). Live Harmony processing remains disabled.

**Real functionality:** live NASA CMR collection / granule discovery, actual UTC acquisition dates, provisional spatial coverage, metadata inspection, conservative two-date screening, and discovery metadata exports.

**Phase 2B implemented:** server-side, explicitly enabled Harmony GCOV subset jobs, polling/cancellation, bounded COG caching and Rasterio inspection. The first real COG passed spatial revalidation and is registered as the reference. The second candidate's dry-run is ready, awaiting explicit authorization; scientific comparability is unconfirmed. Processing remains disabled. Password and token modes remain available. See [second-scene readiness](docs/harmony-second-test-readiness.md), [spatial validation](docs/harmony-spatial-validation.md) and [Harmony setup](docs/harmony-integration.md).

**Science still pending:** real two-date calibrated backscatter validation, mangrove masks, measured forest loss / gain and validated scientific change reports (Phase 3). The new local engine supports identified power-unit/common-grid calculations and RGB visual differences; its matched demonstration pairs are simulated. No simulated scenes or dates enter discovery results. Image indicators are never presented as confirmed deforestation or hectares of forest lost.

## Quick start in this workspace

Dependencies are already installed in `node_modules` and `.venv`. From the project root, use two terminals:

```powershell
# Terminal 1: backend
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

```powershell
# Terminal 2: frontend
npm.cmd run dev
```

Open **http://127.0.0.1:5173**. API documentation: **http://127.0.0.1:8000/docs**. Stop each process with `Ctrl+C`.

The new local-image dependencies are included in `backend/requirements-lock.txt`. If updating an existing environment, install that lock first. The four small simulated files are included under `datasets/`; if absent, run `.venv\Scripts\python.exe -m scripts.generate_comparison_demo`. This explicit regeneration command rewrites the demo manifest, so preserve any expanded curated catalog first. The cached real COG is optional for the demonstration. Additional real matched pairs can be registered in the manifest without changing comparison code.

No API key, paid subscription, NASA account, raw HDF5 upload or manual satellite-data download is needed for public CMR metadata discovery. Internet is required for NASA CMR, basemap tiles and optional web fonts. The app remains explicit about discovery errors; it does not replace unavailable NASA data with invented results.

## Fresh setup

Requires Node.js 24.x and Python 3.12 (3.12.13 for the prepared Render service). Use `npm.cmd` on Windows if PowerShell execution policy blocks `npm.ps1`; changing Windows execution policy is unnecessary.

```powershell
npm.cmd ci
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend\requirements-lock.txt
Copy-Item .env.example .env
```

If Python is managed with `uv`, the workspace-local alternative is:

```powershell
$env:UV_CACHE_DIR = "$PWD\.uv-cache"
$env:UV_PYTHON_INSTALL_DIR = "$PWD\.python"
uv python install 3.12
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -r backend\requirements-lock.txt
```

On macOS/Linux, use `python3.12 -m venv .venv`, `.venv/bin/python -m pip install -r backend/requirements-lock.txt`, `.venv/bin/python -m uvicorn backend.app.main:app --reload`, and `npm run dev`. The exact lock was verified on Windows; `backend/requirements.txt` supplies portable direct dependency ranges when another platform cannot resolve the lock.

The optional `.env` stays at the project root. Leave `EARTHDATA_TOKEN` empty for public discovery. If NASA returns 401/403, configure a valid token **server-side** and restart the backend. Never put a token in a `VITE_` variable, browser field, query string, source control, or export. There is no browser login flow in Phase 1. Integrated server-side username/password authentication was separately live-verified; see [authentication evidence](docs/harmony-backend-authentication.md). The new image comparison does not use Earthdata authentication.

## Using the dashboard

1. **Overview** discovers GCOV collections dynamically, prefers a collection labeled validated by NASA, and searches the previous 365 days over the provisional pilot. Metrics are counts and timestamps from returned metadata, never forest-change measurements.
2. **Explore Map** lets you change the collection, search dates and bounding box (`west, south, east, north`). Submit **Discover** after editing the bounds or dates. Toggle Esri satellite / OpenStreetMap, show CMR footprints, zoom, rotate and recenter. Satellite basemap imagery is contextual; it is not a NISAR observation or change layer.
3. **Date Comparison** allows selection only on dates represented by loaded granules. Both calendars initially show the newest acquisition month. Gray dates mean no scenes **in loaded results**, not proof that NASA has no observations. Choose the exact acquisition from the dropdown when a day has multiple scenes. The calendar previews mismatches and unknown fields; **Screen compatibility** performs the server-side footprint and metadata check.
4. **Change Analytics** explicitly displays `Not calculated` and an optional **DEMO / SIMULATED** chart. Samples A–H are illustrative and have no observation dates or forest-area units.
5. **Reports** exports a local JSON discovery report with query bounds, collection provenance, actual timestamps, loaded metadata, pagination state, screening results and limitations. It does not export measured change.

The initial AOI `[88.4, 21.55, 89.1, 22.25]` is a provisional rectangular pilot. It is not an authoritative mangrove boundary, legal boundary or validated NISAR scene footprint. **Manual scientific action:** validate or replace the AOI and review footprint overlap before any Phase 2 processing.

## API contract

Frontend requests use `/api`; Vite proxies to FastAPI on port 8000. Optional public `VITE_API_BASE_URL` can point to a separately deployed backend. FastAPI restricts CORS to `ALLOWED_ORIGINS`. CMR requests are made on the server, use a 30-second timeout and a 5-minute in-process cache, and do not log or return credentials.

| Route | Behavior |
| --- | --- |
| `GET /api/health` | Local service health, phase and processing flag; does not imply NASA availability |
| `GET /api/config` | Default provisional AOI and implemented capabilities |
| `GET /api/collections?product=GCOV` | Query CMR keyword NISAR; filter NISAR short names and optional product; return discovered IDs / maturity |
| `GET /api/scenes?collection_id=…&bbox=…&start=YYYY-MM-DD&end=YYYY-MM-DD&page=1&page_size=200` | Validate dynamically discovered collection, query overlapping granules, normalize metadata, dates and approximate AOI coverage |
| `GET /api/scenes/{granule_concept_id}?bbox=…` | Fetch original UMM granule metadata and normalized fields |
| `POST /api/compare` | Accept `baseline_id`, `comparison_id`, optional `bbox`; return per-field statuses and shared AOI coverage; always `analysis_ready: false` |
| `GET /api/processing/capabilities` | Phase 2B setup state, safe limits, and first/second-scene gates; no fake NASA results |

The API's collection endpoint supports GCOV, GSLC, RSLC, GUNW, GOFF, RUNW, RIFG and ROFF product filters. The Phase 1 dashboard focuses on GCOV. Dates use **acquisition beginning times in UTC**, not provider insertion or publication dates. Missing acquisition times remain null and are excluded from available dates.

Scene searches return at most 200 records per page. Use **Load more observations** until complete. `available_dates` is page-specific in the API; the frontend merges loaded dates. Exports include `has_more` and `dates_complete` so incomplete search results cannot be mistaken for a complete calendar. Collection discovery is currently bounded to 200 keyword matches; the verified catalog returned fewer than this. Page-number pagination may shift if NASA changes its catalog while paging; a future harvesting service should use CMR Search After.

Errors include explicit `authentication_required` (401), `upstream_error` (502), `rate_limited` (503), invalid input (422), and missing records (404). Empty searches return a successful empty list, not invented observations. Loading, error, empty, authentication-required, unknown metadata and unimplemented-processing states are represented separately.

## Compatibility and coverage limitations

Screening checks distinct dates; product and product version; collection / maturity and version; radar instrument; frequency sub-bands; polarization and bandwidth per frequency; orbit direction; relative track; frame; look direction; incidence angle; and shared scene coverage inside the requested AOI. Absolute orbit numbers are exposed as context and are not required to match between repeat acquisitions.

Missing required metadata is **unknown**, even if other fields match. A known mismatch takes precedence and marks the pair incompatible. Missing incidence angles stay unknown; different reported angles require scientific review. `compatible` means a metadata candidate only. Every result has `analysis_ready: false` because the scientific pipeline is absent. These rules are deliberately conservative and may reject scientifically usable pairs requiring a more sophisticated Phase 2 method.

Coverage uses the actual CMR polygon when available; rectangular footprint fallbacks are identified. It is an approximate cylindrical equal-area intersection, with transformed straight polygon edges, rounded to two decimals. Shared coverage is intersection of both scene footprints **inside the AOI**, divided by AOI area. It does not establish pixel validity or forest area. Only positive shared coverage passes the metadata overlap test; there is no validated minimum-coverage threshold. Geographic boundaries, dateline-crossing AOIs, irregular custom polygons and high-precision geodesic coverage require further work.

CMR may not include incidence angles or all calibration / geometry metadata needed for processing. No filename-derived assumptions fill these gaps. Tides, seasonal differences, speckle, radiometric calibration, terrain correction, pixel alignment and masks have not been evaluated.

## Verified NASA endpoints

Live checks ran on **14 November 2026** through the actual FastAPI routes. Full query URLs, real returned dates, discovered IDs, sample metadata and screening checks are recorded in [`docs/nasa-verification.json`](docs/nasa-verification.json). Identifiers in that evidence are records of verification, **not hard-coded application configuration**.

- `https://cmr.earthdata.nasa.gov/search/collections.umm_json` — HTTP 200; keyword `NISAR` discovered three GCOV collections.
- `https://cmr.earthdata.nasa.gov/search/granules.umm_json` — HTTP 200 for each discovered GCOV collection with `bounding_box=88.4,21.55,89.1,22.25`. At verification: validated 10 granules, provisional 66, beta 5 (unbounded acquisition date search). Counts may change.
- `https://cmr.earthdata.nasa.gov/search/concepts/{granule_id}.umm_json` — HTTP 200; sample acquisition timestamp matched the scene-search record. The sample's missing incidence angle was preserved as null / unknown.

The live two-scene comparison correctly reported mismatched orbit direction, track, frame, polarizations and bandwidth while also reporting positive approximate shared AOI coverage. That Phase 1 verification did not check Harmony endpoints, authenticated retrieval, COG conversion, raster calculation or measured change. Current Phase 2B evidence is documented separately.

Primary technical references: [NASA CMR Search API](https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html), [ASF NISAR GCOV user guide](https://nisar-docs.asf.alaska.edu/gcov/), and [ASF NISAR metadata guide](https://nisar-docs.asf.alaska.edu/metadata/).

## Checks

Current Phase 2B checks: **48 backend tests passed**, **9 frontend tests passed**, and the production build passed. One opt-in network pytest is skipped by default; the public NASA preflight ran successfully through `scripts/verify_harmony.py`. Actual processing remains blocked by missing server authentication and disabled live processing. See [full integration evidence and setup](docs/harmony-integration.md).

```powershell
npm.cmd run build
npm.cmd test
.venv\Scripts\python.exe -m pytest backend/tests -q
# Optional network check: refreshes public evidence in docs/nasa-verification.json
.venv\Scripts\python.exe -m scripts.verify_nasa
```

Automated checks cover real-date handling, missing metadata, same-date rejection, known mismatches, true polygon intersection versus envelope overlap, missing / disjoint geometry, AOI validation, pagination completeness, upstream authentication / rate-limit / server errors, collection filtering and explicitly unimplemented processing.

The TypeScript / Vite production build, **20 backend tests and 5 frontend tests** passed. The final npm installation audit reported **zero vulnerabilities** after upgrading MapLibre and Vitest. Local frontend HTTP and API health checks passed, and the live NASA integration check passed. The build retains a bundle-size warning because MapLibre and Recharts are currently in the main bundle (about 493 kB gzipped JavaScript); route / vendor splitting is a performance follow-up before a wider deployment. A Starlette test-client deprecation warning is present; all backend tests pass.

**Visual browser verification was blocked**: the browser connector was unavailable and Computer Use stopped because it could not confidently determine Chrome's current URL. Manually inspect desktop and mobile layouts, map tile loading, date selection and JSON download before publishing. There are no fabricated fallback tiles or scenes. Temporary preview servers used for verification were stopped; use the quick-start commands to launch the app.

## Architecture and Phase 2 handoff

The [Sundarbans real-data feasibility audit](docs/sundarbans-data-feasibility.md) documents **VERIFIED** repeat acquisitions and collection-level Harmony capabilities, **PARTIALLY VERIFIED** candidate compatibility, and **NOT VERIFIED** scientific readiness. It includes exact granule IDs, footprints, nearby AOI proposals, public evidence and a staged Phase 2 plan. The existing pilot and application behavior remain unchanged; no Harmony jobs or change detection were implemented by the audit.

```text
src/
  App.tsx                    Dashboard routes, query / selection state, report export
  api.ts                     Typed HTTP boundary and explicit errors
  types.ts                   Scene contracts and conservative calendar hints
  components/ForestMap.tsx    MapLibre basemaps, provisional AOI and CMR footprints
  components/DateCalendar.tsx Scene-backed date selection
backend/app/
  config.py                  Server-side settings and provisional default AOI
  cmr.py                     NASA adapter, dynamic identifiers, cache, auth / errors
  science.py                 Metadata normalization and approximate spatial screening
  main.py                    FastAPI routes; future processing capability boundary
  harmony.py                 Gated extraction jobs, provenance and bounded cache
  rasters.py                 COG validation and technical common-grid checks
backend/tests/               Offline, synthetic metadata tests (never UI data)
scripts/verify_nasa.py        Opt-in live integration verification
docs/nasa-verification.json  Dated public endpoint verification evidence
```

Phase 2B now provides a separate gated job service with bounded streaming, caching, persistence, retries, cancellation and Rasterio inspection. Follow docs/harmony-integration.md for its setup and outstanding live checks. Phase 3 still requires scientific processing and validation. Keep processed raster provenance and uncertainty separate from discovery metadata. Return measured metrics only after implementing and testing calibration, co-registration, mangrove masking and scientific validation. End users must not have to upload or manually download HDF5 files.

This is production-minded Phase 1 scaffolding, not a hardened multi-user deployment. Before Internet deployment: add API rate limiting, a deployment-specific secrets manager, durable job / cache infrastructure when processing is added, monitoring and an HTTPS reverse proxy. Configure CORS and serve `dist/` with a same-origin `/api` proxy, or set `VITE_API_BASE_URL` at build time for an HTTPS FastAPI origin. `vite preview` is a build preview, not a production backend.

## Manual actions required

1. Start the backend and frontend with the quick-start commands and open the local URL.
2. Manually review the desktop / mobile UI, tile loading, two-date screening and discovery JSON export (automated visual verification was unavailable).
3. Validate or replace the provisional pilot AOI before scientific use.
4. No NASA token is needed unless an upstream endpoint explicitly requests authentication. If needed, create / manage it yourself and place it only in the server `.env`.
5. Follow docs/harmony-integration.md for a dry-run and ONE gated first-scene processing test. No scientific change claims are allowed before Phase 3 validation.

Basemap attribution is displayed in the map: Esri imagery contributors and OpenStreetMap contributors. These public basemaps require no API key for this local pilot and remain subject to their providers' usage terms and service availability.
