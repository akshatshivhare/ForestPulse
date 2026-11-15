"""Offline tests. Raster pixels and Harmony job responses are SYNTHETIC."""
import asyncio
import copy
import json
import os
import time
from pathlib import Path
from uuid import uuid4

import httpx
import numpy as np
import pytest
import rasterio
from fastapi import HTTPException
from fastapi.testclient import TestClient
from rasterio.transform import from_bounds

from backend.app import cmr, harmony
from backend.app.main import app
from backend.app.rasters import inspect_cog, check_alignment

EVIDENCE = Path(__file__).resolve().parents[2] / 'docs' / 'sundarbans-evidence'
REMOTE_ID = '11111111-1111-4111-8111-111111111111'


def read(name):
    return json.loads((EVIDENCE / (name + '.json')).read_text(encoding='utf-8'))


def cog(path, bbox, *, invalid=False, wrong_variable=False, driver='COG', offset=0):
    data = np.full((100, 100), np.nan if invalid else 2, dtype='float32')
    w, s, e, n = bbox
    with rasterio.open(path, 'w', driver=driver, width=100, height=100, count=1, dtype='float32',
                       crs='EPSG:4326', transform=from_bounds(w+offset, s, e+offset, n, 100, 100), nodata=np.nan) as ds:
        ds.write(data, 1)
        ds.set_band_description(1, 'frequencyA/VVVV' if wrong_variable else harmony.VARIABLE)


class FakeNASA:
    """Fake upstream, including synthetic pixels. Never installed in app runtime."""
    def __init__(self):
        self.calls = []
        self.remote_status = 'successful'
        self.missing_output = False
        self.invalid = False
        self.ambiguous = False
        self.no_cancel = False
        self.plan = None

    async def json(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if '/capabilities?' in url:
            return read('C3622241360-ASF-capabilities')
        if url.endswith('/cancel'):
            return {'status': 'running' if self.no_cancel else 'canceled'}
        if '/rangeset?' in url:
            if self.ambiguous:
                harmony.fail(502, 'harmony_unavailable', 'Uncertain submission')
            return {'jobID': REMOTE_ID}
        href = 'https://harmony-prod-staging.s3.us-west-2.amazonaws.com/' + self.plan['scene']['name'] + '_frequencyA_HHHH.tif?secret=DO_NOT_PERSIST'
        return {'status': self.remote_status, 'progress': 100,
                'links': [] if self.missing_output else [{'rel': 'data', 'href': href}], 'dataExpiration': '2026-11-15T00:00:00Z'}

    async def download(self, url, path, budget):
        assert 'DO_NOT_PERSIST' in url
        cog(path, self.plan['bbox'], invalid=self.invalid)


@pytest.fixture
def manager(tmp_path, monkeypatch):
    async def request(path, params=None):
        if path == 'granules.umm_json':
            gid = params['concept_id']
            return {'items': [{'meta': {'concept-id': gid, 'collection-concept-id': 'C3622241360-ASF', 'revision-id': 1}, 'umm': read(gid)}]}
        if path == 'services.umm_json':
            return read('C3622241360-ASF-services')
        raise AssertionError(path)

    async def collection(cid):
        return {'id': cid, 'short_name': 'NISAR_L2_GCOV_V1', 'version': '1', 'maturity': 'validated'}
    monkeypatch.setattr(cmr, 'request', request)
    monkeypatch.setattr(cmr, 'validate_collection', collection)
    settings = harmony.Settings(token='TEST_SECRET_NEVER_REAL', enabled=True, cache=tmp_path, poll=.001, timeout=2)
    result = harmony.Manager(settings, FakeNASA())
    monkeypatch.setattr(harmony, 'manager', result)
    return result


def execute(manager, body=None):
    async def run():
        job = await manager.submit(body or harmony.Extraction(dry_run=False))
        manager.transport.plan = job['plan']
        await manager.run(job)
        return manager.get(job['id'])
    return asyncio.run(run())


def test_dry_run_exact_supported_request_without_credentials(manager):
    manager.settings.token = ''
    manager.settings.enabled = False
    result = asyncio.run(manager.submit(harmony.Extraction()))
    assert result['status'] == 'dry_run' and result['submitted'] is False
    url = httpx.URL(result['plan']['request_url'])
    assert '/collections/V4137651715-ASF/coverage/rangeset' in url.path
    assert url.params.get_list('subset') == ['lon(88.75:88.78)', 'lat(21.85:21.88)']
    assert url.params['granuleId'] == harmony.CANDIDATES[0]
    assert url.params['format'] == 'image/tiff' and url.params['forceAsync'] == 'true'
    assert not manager.jobs() and all('/rangeset' not in url for url, _ in manager.transport.calls)


@pytest.mark.parametrize('bbox', [[88.4,21.55,89.1,22.25], [88.8,21.8,88.7,21.9], [float('nan'),21.8,88.78,21.88]])
def test_reject_large_or_invalid_subset(bbox):
    with pytest.raises(ValueError):
        harmony.Extraction(bbox=bbox)


def test_real_requests_require_both_gates_before_network(manager):
    for token, enabled, code in [('', True, 401), ('test', False, 409)]:
        manager.settings.token, manager.settings.enabled = token, enabled
        with pytest.raises(HTTPException) as exc:
            asyncio.run(manager.submit(harmony.Extraction(dry_run=False)))
        assert exc.value.status_code == code
    assert not manager.transport.calls


def test_live_capability_removal_blocks_builder(manager):
    original = manager.transport.json
    async def unsupported(url, **kwargs):
        if '/capabilities?' in url:
            return {'variables': [], 'services': []}
        return await original(url, **kwargs)
    manager.transport.json = unsupported
    with pytest.raises(HTTPException) as exc:
        asyncio.run(manager.submit(harmony.Extraction()))
    assert exc.value.detail['code'] == 'unsupported_service'


def test_second_scene_locked_before_first_success(manager):
    with pytest.raises(HTTPException) as exc:
        asyncio.run(manager.submit(harmony.Extraction(granule_id=harmony.CANDIDATES[1], dry_run=False)))
    assert exc.value.detail['code'] == 'first_scene_required'
    assert not manager.jobs()


def test_complete_mock_lifecycle_and_persisted_provenance(manager):
    job = execute(manager)
    assert job['status'] == 'verified' and job['raster']['verified']
    assert job['raster']['positive_power_pixels'] == 10000
    assert job['raster']['identity_verified_from_output'] and job['raster']['nodata_is_nan']
    assert not job['analysis_ready'] and not job['raster']['analysis_ready']
    assert job['plan']['granule_revision'] == 1
    persisted = manager.path(job['id']).read_text()
    assert 'TEST_SECRET' not in persisted and 'DO_NOT_PERSIST' not in persisted
    assert harmony.Manager(manager.settings).get(job['id'])['status'] == 'verified'
    assert manager.capabilities()['second_scene_unlocked']


def test_second_output_is_actually_reprojected_on_common_grid(manager):
    first = execute(manager)
    second = execute(manager, harmony.Extraction(granule_id=harmony.CANDIDATES[1], dry_run=False))
    assert second['status'] == 'verified' and second['reference_job_id'] == first['id']
    assert second['alignment']['can_align'] and second['alignment']['shared_valid_pixels'] > 0
    assert second['alignment']['analysis_ready'] is False


def test_shifted_grids_checked_not_assumed_identical(tmp_path):
    a, b = tmp_path/'a.tif', tmp_path/'b.tif'
    cog(a, harmony.SMALL_BBOX)
    cog(b, harmony.SMALL_BBOX, offset=.00015)
    result = check_alignment(a, b)
    assert result['can_align'] and not result['already_same_grid']


@pytest.mark.parametrize('missing,invalid,status', [(True,False,'failed'), (False,True,'failed'), (False,False,'verified')])
def test_missing_or_empty_output_never_passes(manager, missing, invalid, status):
    manager.transport.missing_output = missing
    manager.transport.invalid = invalid
    job = execute(manager)
    assert job['status'] == status
    if status != 'verified':
        assert job['raster'] is None and not manager.path(job['id'], '.part').exists()


@pytest.mark.parametrize('state', ['failed', 'complete_with_errors', 'canceled', 'unrecognized'])
def test_remote_error_states(manager, state):
    manager.transport.remote_status = state
    job = execute(manager)
    assert job['status'] != 'verified' and job['raster'] is None


def test_uncertain_submission_not_retried_or_expired(manager):
    manager.transport.ambiguous = True
    job = execute(manager)
    assert job['status'] == 'submission_unknown'
    assert job['submission_attempted'] is True and job['remote_job_id'] is None
    assert len([u for u, _ in manager.transport.calls if '/rangeset?' in u]) == 1
    repeated = asyncio.run(manager.submit(harmony.Extraction(dry_run=False)))
    assert repeated['id'] == job['id']
    manager.settings.ttl = -1
    manager.cleanup()
    assert manager.get(job['id'])['status'] == 'submission_unknown'


def test_cancel_and_deadline(manager):
    async def run():
        job = await manager.submit(harmony.Extraction(dry_run=False))
        canceled = await manager.cancel(job['id'])
        assert canceled['status'] == 'canceled'
        # Different subset avoids idempotent match with canceled request.
        job = await manager.submit(harmony.Extraction(dry_run=False, bbox=[88.75,21.85,88.77,21.87]))
        manager.transport.plan = job['plan']
        manager.transport.remote_status = 'running'
        manager.settings.timeout = .03
        await manager.run(job)
        return manager.get(job['id'])
    job = asyncio.run(run())
    assert job['status'] == 'timed_out' and job['remote_cancel_confirmed'] is True


def test_active_remote_cancel_and_recovery(manager):
    async def run():
        job = await manager.submit(harmony.Extraction(dry_run=False))
        job.update(status='running', remote_job_id=REMOTE_ID)
        manager.save(job)
        await manager.cancel(job['id'])
        await manager.run(job)
        return manager.get(job['id'])
    job = asyncio.run(run())
    assert job['status'] == 'canceled' and job['remote_cancel_confirmed']
    assert not any('/rangeset?' in u for u, _ in manager.transport.calls)


def test_cleanup_storage_limits_and_idempotency(manager):
    async def run():
        body = harmony.Extraction(dry_run=False)
        first = await manager.submit(body)
        assert (await manager.submit(body))['id'] == first['id']
        manager.settings.max_jobs = 1
        await manager.cancel(first['id'])
        with pytest.raises(HTTPException) as exc:
            await manager.submit(harmony.Extraction(dry_run=False, bbox=[88.75,21.85,88.77,21.87]))
        assert exc.value.status_code == 507
        manager.settings.ttl = -1
        manager.cleanup()
        assert not manager.jobs()
        manager.settings.max_cache_bytes = 1
        with pytest.raises(HTTPException) as exc:
            await manager.submit(body)
        assert exc.value.status_code == 507
    asyncio.run(run())


def test_unsafe_paths_and_output_hosts(manager):
    with pytest.raises(HTTPException):
        manager.get('../../.env')
    assert not harmony.Transport.asset_allowed('http://127.0.0.1/secret')
    assert not harmony.Transport.asset_allowed('https://harmony.earthdata.nasa.gov.evil.test/x')
    assert not harmony.Transport.asset_allowed('https://harmony-prod-test.s3.us-west-2.amazonaws.com@evil.test/x')


def test_process_lock_and_interrupted_submission_prevent_duplicates(manager):
    async def run():
        job = await manager.submit(harmony.Extraction(dry_run=False))
        with harmony.file_lock(manager.settings.cache, 'worker') as owned:
            assert owned
            await harmony.Manager(manager.settings, manager.transport).run(job)
        assert not any('/rangeset?' in u for u, _ in manager.transport.calls)
        job['status'] = 'submitting'
        manager.save(job)
        await manager.run(job)
        assert manager.get(job['id'])['status'] == 'submission_unknown'
        assert not any('/rangeset?' in u for u, _ in manager.transport.calls)
    asyncio.run(run())


def test_api_worker_automatically_processes_mock_job(manager):
    manager.transport.plan = asyncio.run(manager.submit(harmony.Extraction()))['plan']
    with TestClient(app) as client:
        job = client.post('/api/processing/jobs', json={'dry_run':False}).json()
        for _ in range(250):
            result = client.get('/api/processing/jobs/'+job['id']).json()
            if result['status'] == 'verified':
                break
            time.sleep(.01)
        assert result['status'] == 'verified'
        assert client.get('/api/processing/jobs/'+job['id']+'/raster').status_code == 200


def test_download_size_auth_isolation_and_status_backoff(tmp_path, monkeypatch):
    calls = []
    responses = iter([429, 503, 200])
    def handler(request):
        calls.append(request)
        if request.url.host == 'harmony.earthdata.nasa.gov':
            return httpx.Response(next(responses), json={'status':'running'})
        assert 'authorization' not in request.headers
        return httpx.Response(200, headers={'content-length':'100'}, content=b'x'*100)
    client = httpx.AsyncClient
    monkeypatch.setattr(harmony.httpx, 'AsyncClient', lambda **kw: client(**kw, transport=httpx.MockTransport(handler)))
    waits = []
    async def sleep(seconds):
        waits.append(seconds)
    monkeypatch.setattr(harmony.asyncio, 'sleep', sleep)
    t = harmony.Transport(harmony.Settings(token='SECRET_TEST'))
    async def run():
        await t.json(harmony.ROOT+'/jobs/'+REMOTE_ID, auth=True)
        with pytest.raises(HTTPException) as exc:
            await t.download('https://harmony-prod-staging.s3.us-west-2.amazonaws.com/test.tif', tmp_path/'out', 10)
        assert exc.value.status_code == 413
    asyncio.run(run())
    assert waits == [1,2]
    assert len(calls) == 4 and calls[0].headers['authorization'] == 'Bearer SECRET_TEST'


def test_transport_auth_redirect_and_submission_no_retry(monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={'location':'https://urs.earthdata.nasa.gov/oauth/authorize'})
    client = httpx.AsyncClient
    monkeypatch.setattr(harmony.httpx, 'AsyncClient', lambda **kw: client(**kw, transport=httpx.MockTransport(handler)))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(harmony.Transport(harmony.Settings(token='TEST')).json(harmony.ROOT+'/test', auth=True, retry=False))
    assert exc.value.status_code == 401 and len(calls) == 1


def test_api_errors_dry_run_and_verified_metadata(manager):
    client = TestClient(app)
    manager.settings.token = ''
    response = client.post('/api/processing/jobs', json={'dry_run':False})
    assert response.status_code == 401 and 'TEST_SECRET' not in response.text
    assert client.post('/api/processing/jobs', json={}).json()['submitted'] is False
    assert client.get('/api/processing/jobs/not-a-uuid').status_code == 404
    rejected = client.post('/api/processing/jobs', json={'token':'never-accept'})
    assert rejected.status_code == 422 and 'never-accept' not in rejected.text
    manager.settings.token = 'TEST'
    job = execute(manager)
    assert client.get('/api/processing/jobs/'+job['id']+'/raster').json()['raster']['verified']
    assert client.get('/api/processing/capabilities').json()['analysis_ready'] is False


def test_non_cog_or_wrong_identity_rejected(manager, tmp_path):
    plan = asyncio.run(manager.submit(harmony.Extraction()))['plan']
    path = tmp_path/'ordinary.tif'
    cog(path, plan['bbox'], driver='GTiff')
    with pytest.raises(ValueError):
        inspect_cog(path, plan, 'https://example.test/'+plan['scene']['name']+'_frequencyA_HHHH.tif')
    cog(path, plan['bbox'], wrong_variable=True)
    with pytest.raises(ValueError):
        inspect_cog(path, plan, 'https://example.test/unidentified.tif')
    with pytest.raises(ValueError):
        inspect_cog(path, plan, 'https://example.test/'+plan['scene']['name']+'_frequencyA_HHHH.tif')


def test_public_dry_run_live_opt_in_only():
    if os.environ.get('FORESTPULSE_LIVE_METADATA_TEST') != 'true':
        pytest.skip('Public NASA metadata integration is opt-in; never submits processing.')
    m = harmony.Manager(harmony.Settings(token='', enabled=False))
    result = asyncio.run(m.submit(harmony.Extraction()))
    assert result['status'] == 'dry_run' and result['submitted'] is False
