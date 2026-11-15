from datetime import date, datetime, timezone
from contextlib import asynccontextmanager, suppress
from typing import Annotated
import asyncio
import re
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from . import cmr
from .config import ORIGINS, PILOT_BBOX
from .science import normalize, compare
from . import harmony
from . import image_comparison, runtime
from .deployment import validate_demo_assets
from .image_comparison import router as image_comparison_router


@asynccontextmanager
async def lifespan(_app):
    async def cache_maintenance():
        while True:
            await asyncio.to_thread(image_comparison.cleanup)
            await asyncio.sleep(300)

    if runtime.PRODUCTION:
        await asyncio.to_thread(validate_demo_assets)
        await asyncio.to_thread(image_comparison.cleanup)
    task = asyncio.create_task(cache_maintenance() if runtime.PRODUCTION else harmony.manager.worker())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        if hasattr(harmony.manager.transport, 'close'):
            await asyncio.to_thread(harmony.manager.transport.close)


app = FastAPI(title='ForestPulse API', version='0.2.0', lifespan=lifespan, description='NASA discovery and gated Phase 2B GCOV extraction. No forest-change measurements.')


@app.middleware('http')
async def public_processing_guard(request, call_next):
    path = request.url.path
    if (runtime.PRODUCTION and (path == '/api/processing' or path.startswith('/api/processing/'))
            and path != '/api/processing/capabilities'):
        return JSONResponse(status_code=403, content={'detail': {'code': 'processing_private',
            'message': 'NASA processing and private job records are unavailable on the public deployment. Use the preloaded Image Comparison workflow.'}})
    return await call_next(request)


app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=['GET', 'POST'], allow_headers=['Content-Type'])
app.include_router(image_comparison_router)


@app.exception_handler(RequestValidationError)
async def safe_processing_validation(request, exc):
    if request.url.path.startswith('/api/image-comparisons'):
        return JSONResponse(status_code=422,content={'detail':{'code':'invalid_comparison_request',
            'message':'Choose gallery images and bounded comparison settings. Credentials belong only in the server environment.'}})
    if request.url.path.startswith('/api/processing/'):
        # Pydantic's default error echoes input, including accidentally sent secrets.
        return JSONResponse(status_code=422, content={'detail': {'code': 'invalid_processing_request',
            'message': 'Use an audited candidate and bounded subset. Credentials belong only in the server environment.'}})
    return await request_validation_exception_handler(request, exc)


def parse_bbox(value: str):
    try:
        values = [float(v) for v in value.split(',')]
        if len(values) != 4 or not (-180 <= values[0] < values[2] <= 180 and -90 < values[1] < values[3] < 90):
            raise ValueError()
        return values
    except ValueError:
        raise HTTPException(422, detail={'code': 'invalid_bbox', 'message': 'Use west,south,east,north, with valid increasing longitude and latitude bounds. Dateline-crossing AOIs are not supported in Phase 1.'})


@app.get('/api/health')
def health():
    return {'status': 'ok', 'phase': '2B', 'processing_implemented': True, 'change_analysis_implemented': False,
            'deployment_mode': 'production' if runtime.PRODUCTION else 'development',
            'harmony_processing_enabled': False if runtime.PRODUCTION else harmony.manager.settings.enabled,
            'image_comparison_implemented': True, 'generated_files_ephemeral': runtime.PRODUCTION}


@app.get('/api/config')
def config():
    return {'pilot': {'name': 'Sundarbans, West Bengal, India', 'bbox': PILOT_BBOX, 'status': 'provisional', 'notice': 'Pilot AOI is illustrative and is not a validated NISAR scene footprint.'}, 'capabilities': {'cmr_discovery': True, 'metadata_screening': True, 'harmony': True, 'change_analysis': False}}


@app.get('/api/collections')
async def collections(product: Annotated[str | None, Query(pattern=r'^(GCOV|GSLC|RSLC|GUNW|GOFF|RUNW|RIFG|ROFF)$')] = None):
    items = await cmr.collections(product)
    return {'source': 'NASA CMR live metadata (short-lived server cache)', 'collections': items, 'count': len(items), 'retrieved_at': datetime.now(timezone.utc).isoformat()}


@app.get('/api/scenes')
async def scenes(collection_id: Annotated[str, Query(pattern=r'^C\d+-[A-Za-z0-9_]+$')], bbox: str = ','.join(map(str, PILOT_BBOX)), start: date | None = None, end: date | None = None, page: int = Query(1, ge=1, le=100), page_size: int = Query(100, ge=1, le=200)):
    bounds = parse_bbox(bbox)
    await cmr.validate_collection(collection_id)
    if start and end and start > end:
        raise HTTPException(422, detail={'code': 'invalid_dates', 'message': 'Start must be before or equal to end.'})
    params = {'collection_concept_id': collection_id, 'bounding_box': bbox, 'page_size': page_size, 'page_num': page, 'sort_key': '-start_date'}
    if start or end:
        params['temporal'] = f"{start.isoformat() + 'T00:00:00Z' if start else ''},{end.isoformat() + 'T23:59:59.999999Z' if end else ''}"
    raw = await cmr.request('granules.umm_json', params)
    items = [normalize(i, bounds) for i in raw.get('items', [])]
    dates = sorted({s['date'] for s in items if s['date']})
    hits = raw.get('hits', 0)
    return {'source': 'NASA CMR', 'scenes': items, 'available_dates': dates, 'total_hits': hits, 'page': page, 'page_size': page_size,
            'has_more': page * page_size < hits, 'dates_complete': page == 1 and hits <= page_size,
            'bbox': bounds, 'aoi_status': 'provisional', 'coverage_method': 'Approximate cylindrical equal-area polygon intersection; bounding rectangle fallback is identified. Not a validated acquisition footprint.', 'retrieved_at': datetime.now(timezone.utc).isoformat()}


@app.get('/api/scenes/{scene_id}')
async def metadata(scene_id: str, bbox: str = ','.join(map(str, PILOT_BBOX))):
    if not re.fullmatch(r'G\d+-[A-Za-z0-9_]+', scene_id):
        raise HTTPException(422, detail='Invalid granule concept ID.')
    bounds = parse_bbox(bbox)
    item = await cmr.granule(scene_id)
    return {'scene': normalize(item, bounds), 'umm': item['umm'], 'source': 'NASA CMR'}


class CompareRequest(BaseModel):
    baseline_id: str = Field(pattern=r'^G\d+-[A-Za-z0-9_]+$')
    comparison_id: str = Field(pattern=r'^G\d+-[A-Za-z0-9_]+$')
    bbox: list[float] = Field(default_factory=lambda: PILOT_BBOX.copy(), min_length=4, max_length=4)

    @field_validator('bbox')
    @classmethod
    def bbox_valid(cls, values):
        parse_bbox(','.join(map(str, values)))
        return values


@app.post('/api/compare')
async def comparison(body: CompareRequest):
    first, second = await asyncio.gather(cmr.granule(body.baseline_id), cmr.granule(body.comparison_id))
    a, b = normalize(first, body.bbox), normalize(second, body.bbox)
    return {**compare(a, b, body.bbox), 'baseline': a, 'comparison': b, 'source': 'NASA CMR', 'screened_at': datetime.now(timezone.utc).isoformat()}


@app.get('/api/processing/capabilities')
def processing_capabilities():
    result = harmony.manager.capabilities()
    if runtime.PRODUCTION:
        result.update(real_processing_enabled=False, authentication_configured=False, authentication_verified=False,
                      state='processing_disabled', public_deployment=True)
    return result


@app.post('/api/processing/jobs')
async def submit_processing(body: harmony.Extraction):
    return await harmony.manager.submit(body)


@app.get('/api/processing/jobs')
def processing_jobs():
    harmony.manager.cleanup()
    return {'jobs': harmony.manager.jobs()}


@app.get('/api/processing/jobs/{job_id}')
def processing_job(job_id: str):
    harmony.manager.cleanup()
    return harmony.manager.get(job_id)


@app.post('/api/processing/jobs/{job_id}/cancel')
async def cancel_processing(job_id: str):
    return await harmony.manager.cancel(job_id)


@app.get('/api/processing/jobs/{job_id}/raster')
def processing_raster(job_id: str):
    harmony.manager.cleanup()
    job = harmony.manager.get(job_id)
    if job['status'] != 'verified' or not harmony.manager.path(job_id, '.tif').exists():
        raise HTTPException(409, detail={'code': 'raster_not_verified', 'message': 'No verified cached raster exists for this job.'})
    return {'raster': job['raster'], 'alignment': job['alignment'], 'provenance': job['plan'], 'analysis_ready': False}
