# Vercel frontend and Render backend

The project is prepared for these hosts. No public deployment has been performed or verified. The repository contains the React/Vite frontend at its root and FastAPI at `backend.app.main:app`. Use the repository root for both services; do not select `src/` or `backend/` as a hosting root directory.

## What is included

- `vercel.json`: Vite framework, `npm ci`, `npm run build`, `dist` output, SPA fallback.
- `render.yaml`: Python 3.12.13, one Uvicorn worker, platform `PORT`, `/api/health`, production mode, Harmony disabled, automatic deploys off.
- `backend/requirements-production.txt`: 37 pinned runtime dependencies resolved for Python 3.12 / Linux x86_64. Linux dependency resolution passed; execution of the native libraries on Render still requires deployment verification.
- `scripts/check_deployment.py`: offline validation that all four required simulated gallery assets and their labels are present. It never generates replacement imagery, authenticates or submits NASA jobs.
- Production caches use the OS temporary directory (`/tmp/forestpulse` on a typical Render instance). Source datasets are read from repository-relative absolute paths, independently of the working directory.

The four small PNG/GeoTIFF fixtures in `datasets/sundarbans-simulated-v1/` total 2,063,207 bytes. Include them and `datasets/catalog.json` in Git. All matched demonstration pairs remain **SIMULATED**. Their scenario dates are not satellite acquisitions or scientific observations.

The local validated NISAR COG, old jobs and generated reports remain under ignored `artifacts/`; they are not uploaded automatically. Its gallery metadata remains, but the real observation is unavailable on a clean deployment unless an explicitly curated source is supplied later. Nothing duplicates or invents a second real NISAR observation. This preparation does not claim a completed real Sentinel-2 vegetation-analysis pipeline.

## 1. GitHub

Use the intended GitHub repository and branch. Before committing, check ignored files and scan the intended files and existing Git history for credentials. Never upload `.env`, `.netrc`, Earthdata credentials, tokens, logs, caches, virtual environments, `node_modules`, `dist`, or generated PDFs. `.env.example` contains placeholders only and may be committed. Keep the small, explicitly simulated datasets in Git.

Review `git status` and the staged file list before committing. Do not force-push or rewrite an existing repository's history. The workspace's secret-audit script, when present, reports categories/paths and counts without printing matching values. A clean automated scan is not a guarantee against every possible unknown secret format.

## Frontend-only deployment first

You can complete the Vercel steps below before creating a Render service. Leave `VITE_API_BASE_URL` unset or empty. The build succeeds, navigation and styling remain available, and API-dependent pages show **Backend temporarily unavailable**. The frontend does not request `/api` on Vercel, use localhost, load invented gallery dates, or generate comparison/PDF results. The server-side simulated datasets remain unchanged and explicitly labeled. When the backend exists, set its actual HTTPS origin and rebuild the frontend.

Regression validation: `npm run build` passed with `VERCEL=1` and `VITE_API_BASE_URL` unset; **30 frontend tests passed**. Tests load the actual production Vite configuration, verify zero API requests without a backend, verify the unavailable page/navigation and absence of result claims, reject production localhost URLs, and retain configured HTTPS requests. Backend and Harmony processing code were unchanged.

## 2. Render backend — manual setup

1. In Render choose **New → Web Service**, connect the GitHub repository and choose the pushed branch.
2. Set **Root Directory** to the repository root (leave blank), **Language** to Python 3, and **Auto-Deploy** to Off.
3. Use these commands:

| Setting | Value |
| --- | --- |
| Build | `pip install -r backend/requirements-production.txt && python -m scripts.check_deployment` |
| Start | `python -m uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT --workers 1 --no-access-log` |
| Health check | `/api/health` |

4. Add the environment variables below. `ALLOWED_ORIGINS` must be your intended Vercel production origin; correct it after Vercel assigns the actual URL if the name differs.

| Variable | Value |
| --- | --- |
| `PYTHON_VERSION` | `3.12.13` |
| `FORESTPULSE_ENV` | `production` |
| `HARMONY_PROCESSING_ENABLED` | `false` |
| `ALLOWED_ORIGINS` | Your exact frontend origin, such as `https://YOUR-PROJECT.vercel.app` |
| `CMR_TIMEOUT_SECONDS` | `30` |
| `CMR_CACHE_SECONDS` | `300` |

Do not add `EDL_USERNAME`, `EDL_PASSWORD`, `EARTHDATA_TOKEN`, cookies or authentication headers to this public service. Public CMR discovery and the preloaded demo need none. Production mode ignores local `.env` files and Earthdata credentials, forces Harmony off, never starts its processing worker and returns HTTP 403 for private `/api/processing/...` job routes. Read-only capabilities remain available. This policy also applies when Render is detected through its platform environment.

5. Click **Create Web Service** yourself. Save the exact HTTPS backend URL shown by Render. `https://YOUR-SERVICE.onrender.com` is a placeholder, not a verified live URL.
6. Open its `/api/health`. Expect `status: ok`, `deployment_mode: production`, `harmony_processing_enabled: false`, and `generated_files_ephemeral: true`. The health check is local and does not claim NASA availability.

Alternatively, manually create a Render Blueprint from `render.yaml`; it encodes the same configuration and asks for `ALLOWED_ORIGINS`. No Blueprint or service was created automatically.

## 3. Vercel frontend — manual setup

1. In Vercel choose **Add New → Project**, import the same GitHub repository and select the intended production branch.
2. Select **Vite**, **Root Directory `./`**, **Node.js 24.x**, **Install `npm ci`**, **Build `npm run build`**, **Output `dist`**. The configuration file supplies the commands, output and SPA rewrite.
3. Optionally add **`VITE_API_BASE_URL`** for the Production environment when the backend is ready. Its value is the **actual Render HTTPS origin**, without `/api`, credentials or query parameters. For example, replace the entire placeholder `https://YOUR-SERVICE.onrender.com` with the URL Render actually assigned.
4. Click **Deploy** yourself. A missing backend origin enables the frontend-only unavailable state. An unsafe configured origin still fails clearly. Production builds reject localhost and non-HTTPS origins. No API URL is invented in source code.
5. Save Vercel's actual frontend origin. Update Render's `ALLOWED_ORIGINS` to that exact origin and manually redeploy/restart the backend if it differs from the initial setting.

`VITE_*` variables are public build-time values. Never put credentials in them. Changing the API origin requires rebuilding the frontend. `.vercelignore` excludes backend code, datasets, caches and environment files from the frontend upload; gallery images and PDFs are served directly by Render. Vite's localhost API proxy is for development only and is not used by the production build.

Allow only exact origins, separated by commas when necessary. Do not use `*`, wildcard Vercel subdomains or a path such as `/#images` in CORS. Preview deployments need their own explicitly permitted origins or a separate staging backend. CORS does not authorize NASA processing; the server-side production block does.

## 4. Public acceptance checks

Perform these against the **actual assigned URLs** before announcing a public deployment:

1. Backend `/api/health` and `/api/images` return HTTP 200; four simulated images are available even without any cached satellite data.
2. Frontend `/` and `/#images` load styles and gallery thumbnails. Dropdowns include only available image dates.
3. Default RGB comparison completes; before/after divider, side-by-side, heatmap and regions work. Labels continue to say SIMULATED.
4. Selecting the two simulated radar images also completes; no result is described as measured mangrove loss.
5. **Download detailed PDF** downloads a real PDF from the Render host with metadata, methods and uncertainty.
6. Overview / Explore Map perform CMR discovery; basemaps load from their existing HTTPS providers. Unavailable external services show errors rather than fabricated observations.
7. Date Comparison preserves metadata screening. Its Harmony controls are disabled on the public deployment, without requesting private job history.
8. `POST /api/processing/jobs` returns 403 even if a caller sends `dry_run: false`. No NASA job is created.
9. A request from an unapproved browser origin receives no CORS permission. Missing/expired comparison IDs show a rerun message.

Reports and comparison state expire and can disappear on restart, redeploy or service spin-down. Download a PDF to retain it; rerun a local comparison to regenerate it. Do not scale beyond one worker/instance: the current bounded queue and temporary job storage are single-process. Durable reports or multiple instances require a separate job store/queue and object storage, not a claim of persistence from temporary files.

Render documents that Free instances sleep after inactivity, can take about a minute to wake and lose filesystem changes on restart/spin-down. The frontend allows a bounded 90-second API wait, explains temporary/cold-start errors and never automatically retries a processing submission. Free hosting is suitable for a preview; choose hosting reliability appropriate to your use. [Render Free service behavior](https://render.com/docs/free).

## Local verification and current limits

From the repository root:

```powershell
.venv\Scripts\python.exe -m scripts.check_deployment
.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider
npm.cmd test
# Frontend-only build (no backend URL required):
Remove-Item Env:VITE_API_BASE_URL -ErrorAction SilentlyContinue
npm.cmd run build
# Later, set VITE_API_BASE_URL to your actual Render HTTPS origin and rebuild.
```

The earlier connected-backend production-mode check used a built frontend on port 4174, a separate API origin on port 8010 and a clean source copy without `.env`, cached NISAR data or historical job records. Asset validation, simulated comparisons, PDF HTTP responses, CORS restrictions and private-route blocking were exercised locally; public Vercel/Render access is **not verified**. See `deployment-validation.json` for sanitized evidence. Local testing on Windows does not replace Render's Linux build and public acceptance checks. Vite currently reports a large-bundle advisory; upstream Starlette reports a TestClient deprecation warning.

Official configuration references: [Vercel Vite and SPA routing](https://vercel.com/docs/frameworks/frontend/vite), [supported Node.js versions](https://vercel.com/docs/functions/runtimes/node-js/node-js-versions), [Render FastAPI startup](https://render.com/docs/deploy-fastapi), [Render health checks](https://render.com/docs/health-checks), [Render environment variables](https://render.com/docs/configure-environment-variables).
