"""Constrained Phase 2B extraction. Single-process local pilot, no science claims.

Only the two audited scenes, one variable, and a <=0.05-degree forest-sector
subset are supported. Live jobs require both server-side switches. Signed output
URLs and credentials never enter persisted/public job documents or error text.
"""
import asyncio
import json
import logging
import math
import os
import re
import time
from dataclasses import dataclass, field
from contextlib import contextmanager, asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from shapely.geometry import box, shape

from . import cmr
from .science import normalize
from .rasters import inspect_cog, check_alignment
from . import runtime

ROOT = 'https://harmony.earthdata.nasa.gov'
# HTTP debug records can contain bearer headers or signed asset query strings.
logging.getLogger('httpx').setLevel(logging.CRITICAL + 1)
logging.getLogger('httpcore').setLevel(logging.CRITICAL + 1)
CANDIDATES = ['G4405780437-ASF', 'G4405182121-ASF']
VARIABLE = '/science/LSAR/GCOV/grids/frequencyA/HHHH'
SMALL_BBOX = [88.75, 21.85, 88.78, 21.88]
TERMINAL = {'verified', 'failed', 'authentication_required', 'blocked', 'canceled', 'timed_out', 'submission_unknown', 'expired'}
ACTIVE = {'queued', 'submitting', 'running', 'paused', 'downloading', 'validating', 'cancel_pending'}


def fail(status, code, message):
    raise HTTPException(status, detail={'code': code, 'message': message})


def stamp():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def file_lock(cache, name):
    """OS lock also prevents the CLI smoke test racing an active API worker."""
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / (name + '.lock')
    if path.is_symlink():
        fail(500, 'unsafe_cache', 'Unsafe cache lock entry.')
    handle = path.open('a+b')
    owned = False
    try:
        if os.name == 'nt':
            import msvcrt
            if path.stat().st_size == 0:
                handle.write(b'0')
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                owned = True
            except OSError:
                pass
        else:
            import fcntl
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                owned = True
            except OSError:
                pass
        yield owned
    finally:
        if owned:
            if os.name == 'nt':
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


@asynccontextmanager
async def admission(cache):
    with file_lock(cache, 'admission') as owned:
        if not owned:
            fail(409, 'job_admission_busy', 'Another server is admitting a job. Retry without creating a duplicate.')
        yield


@dataclass
class Settings:
    token: str = field(default_factory=lambda: os.getenv('EARTHDATA_TOKEN', '').strip(), repr=False)
    auth_mode: str = field(default_factory=lambda: os.getenv('HARMONY_AUTH_MODE', 'earthdata_token'))
    username: str = field(default_factory=lambda: os.getenv('EDL_USERNAME', '').strip(), repr=False)
    password: str = field(default_factory=lambda: os.getenv('EDL_PASSWORD', ''), repr=False)
    enabled: bool = field(default_factory=lambda: os.getenv('HARMONY_PROCESSING_ENABLED', '').lower() == 'true')
    cache: Path = field(default_factory=lambda: runtime.cache_root() / 'harmony')
    max_file_bytes: int = 64 * 1024 * 1024
    max_cache_bytes: int = 256 * 1024 * 1024
    max_jobs: int = 50
    ttl: int = 24 * 3600
    timeout: float = 20 * 60
    poll: float = 5

    def __post_init__(self):
        if runtime.PRODUCTION:
            # Public deployment never uses operator credentials or resumes NASA jobs.
            self.enabled = False
            self.token = self.username = self.password = ''
        if self.auth_mode not in {'earthdata_password', 'earthdata_token'}:
            raise ValueError('HARMONY_AUTH_MODE must be earthdata_password or earthdata_token.')

    @property
    def authentication_configured(self):
        return bool(self.username and self.password) if self.auth_mode == 'earthdata_password' else bool(self.token)


class Extraction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    granule_id: str = Field(default=CANDIDATES[0])
    bbox: list[float] = Field(default_factory=lambda: SMALL_BBOX.copy(), min_length=4, max_length=4)
    dry_run: bool = True

    @field_validator('granule_id')
    @classmethod
    def candidate(cls, value):
        if value not in CANDIDATES:
            raise ValueError('Phase 2B supports only the two audited candidate granules.')
        return value

    @field_validator('bbox')
    @classmethod
    def bounds(cls, b):
        w, s, e, n = b
        if not all(math.isfinite(x) for x in b) or not (88.65 <= w < e <= 88.9 and 21.7 <= s < n <= 21.95):
            raise ValueError('Subset must lie within the audited central forest-sector proposal.')
        if e - w > .050000001 or n - s > .050000001 or min(e - w, n - s) < .001:
            raise ValueError('Subset sides must be between 0.001 and 0.05 degrees.')
        return b


class Transport:
    def __init__(self, settings):
        self.settings = settings
        self._password_session = None

    def password_session(self):
        if self._password_session is None:
            from .earthdata_session import PasswordSession
            self._password_session = PasswordSession(self.settings.username, self.settings.password)
        return self._password_session

    def close(self):
        if self._password_session is not None:
            self._password_session.close()

    async def _password_call(self, method, *args, **kwargs):
        from .earthdata_session import SessionError
        pending = asyncio.create_task(asyncio.to_thread(method, *args, **kwargs))
        try:
            # A cancelled asyncio waiter cannot kill synchronous Requests I/O.
            # Finish bounded I/O before job cleanup or session closure can race it.
            return await asyncio.shield(pending)
        except asyncio.CancelledError:
            try:
                await pending
            except Exception:
                pass
            raise
        except SessionError as exc:
            # Only fixed labels are exported; never serialize a Requests exception.
            fail(exc.status, exc.code, 'NASA password-session request failed. Check server authentication and retry only safe read operations.')

    async def json(self, url, *, auth=False, retry=True):
        # Only this trusted origin can receive the Earthdata bearer token.
        if auth and (urlsplit(url).scheme != 'https' or urlsplit(url).netloc != 'harmony.earthdata.nasa.gov'):
            fail(502, 'unsafe_remote_url', 'NASA returned an unsupported authentication destination.')
        if auth and self.settings.auth_mode == 'earthdata_password':
            from .earthdata_session import safe_read
            retry = retry and safe_read(url)
            # Keep bounded status backoff; no automatic transformation replay.
            for attempt in range(3 if retry else 1):
                try:
                    return await self._password_call(self.password_session().json, url, replay_safe=retry)
                except HTTPException as exc:
                    if exc.detail['code'] not in {'rate_limited', 'harmony_unavailable'} or not retry or attempt == 2:
                        raise
                    await asyncio.sleep(2 ** attempt)
        headers = {'Accept': 'application/json', 'Client-Id': 'ForestPulse-Phase2B'}
        if auth:
            headers['Authorization'] = 'Bearer ' + self.settings.token
        for attempt in range(3 if retry else 1):
            try:
                async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
                    r = await client.get(url, headers=headers)
                if r.status_code in (401, 403) or (r.is_redirect and urlsplit(r.headers.get('location', '')).hostname == 'urs.earthdata.nasa.gov'):
                    fail(401, 'authentication_required', 'NASA requires valid server-side Earthdata credentials and application authorization.')
                if r.status_code in (302, 303, 307, 308):
                    target = urljoin(url, r.headers.get('location', ''))
                    destination = urlsplit(target)
                    match = re.fullmatch(r'/jobs/([0-9a-fA-F-]{36})', destination.path)
                    if destination.scheme != 'https' or destination.netloc != 'harmony.earthdata.nasa.gov' or not match:
                        fail(502, 'unexpected_redirect', 'NASA returned an unsupported redirect; no credentials were forwarded.')
                    return {'jobID': str(UUID(match[1]))}
                if r.status_code in (429, 500, 502, 503, 504) and retry and attempt < 2:
                    await asyncio.sleep(min(8, 2 ** attempt))
                    continue
                if r.status_code == 429:
                    fail(503, 'rate_limited', 'NASA rate limit reached. Retry status later.')
                if r.status_code == 409:
                    fail(409, 'remote_conflict', 'NASA cannot perform this job transition in its current state.')
                r.raise_for_status()
                data = r.json()
                if not isinstance(data, dict):
                    raise ValueError()
                return data
            except (httpx.HTTPError, ValueError):
                if retry and attempt < 2:
                    await asyncio.sleep(min(8, 2 ** attempt))
                    continue
                fail(502, 'harmony_unavailable', 'NASA request failed or returned invalid metadata. No remote details or credentials are exposed.')

    @staticmethod
    def asset_allowed(url):
        u = urlsplit(url)
        host = u.hostname or ''
        return u.scheme == 'https' and not u.username and not u.password and u.port in (None, 443) and (
            host == 'harmony.earthdata.nasa.gov' or
            # Exact distribution observed from NASA's HTTPS service-results 307
            # for the authorized first job on 2026-11-15. No CloudFront wildcard.
            host == 'dqzb5lcolc8fj.cloudfront.net' or
            (host.startswith('harmony-prod-') and host.endswith('.s3.us-west-2.amazonaws.com')))

    async def download(self, url, path, budget):
        # Explicit per-hop allowlist. Never send EDL credentials to signed S3 URLs.
        for hop in range(4):
            if not self.asset_allowed(url):
                fail(502, 'unsafe_asset_url', 'Unsupported output host. Backend download was blocked.')
            if self.settings.auth_mode == 'earthdata_password' and urlsplit(url).hostname == 'harmony.earthdata.nasa.gov':
                target = await self._password_call(self.password_session().download_harmony, url, path, budget)
                if target is None:
                    return
                url = target
                continue  # Signed S3 output uses the existing anonymous client.
            headers = {'Accept-Encoding': 'identity'}
            if urlsplit(url).hostname == 'harmony.earthdata.nasa.gov':
                headers['Authorization'] = 'Bearer ' + self.settings.token
            try:
                async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
                    async with client.stream('GET', url, headers=headers) as r:
                        if r.is_redirect:
                            url = urljoin(url, r.headers.get('location', ''))
                            continue
                        if r.status_code in (401, 403):
                            fail(401, 'authentication_required', 'Output access denied or signed output expired. Check server authentication and job expiration.')
                        r.raise_for_status()
                        if int(r.headers.get('content-length', '0')) > budget:
                            fail(413, 'file_too_large', 'Output exceeds the bounded cache/file budget.')
                        size = 0
                        with path.open('wb') as stream:
                            async for chunk in r.aiter_bytes(64 * 1024):
                                size += len(chunk)
                                if size > budget:
                                    fail(413, 'file_too_large', 'Output exceeds the bounded cache/file budget.')
                                stream.write(chunk)
                return
            except (httpx.HTTPError, ValueError):
                fail(502, 'download_failed', 'NASA output download failed. Partial data will be removed.')
        fail(502, 'unexpected_redirect', 'Too many output redirects.')


async def build_plan(body, transport):
    # Fetch exact CMR search record to retain concept revision provenance.
    raw = await cmr.request('granules.umm_json', {'concept_id': body.granule_id, 'page_size': 1})
    if len(raw.get('items', [])) != 1:
        fail(404, 'granule_not_found', 'Candidate granule was not found in live CMR.')
    item = raw['items'][0]
    scene = normalize(item, body.bbox)
    collection = await cmr.validate_collection(scene['collection_id'])
    if scene['product'] != 'GCOV' or scene['collection_name'] != 'NISAR_L2_GCOV_V1':
        fail(422, 'unsupported_product', 'The candidate no longer belongs to the validated GCOV collection.')
    if 'HH' not in scene['polarizations'].get('A', []) or not scene['geometry'] or not shape(scene['geometry']).covers(box(*body.bbox)):
        fail(422, 'unsupported_subset', 'The candidate lacks frequency A HH or full metadata coverage of this subset.')
    caps = await transport.json(ROOT + '/capabilities?collectionId=' + collection['id'])
    var = next((v for v in caps.get('variables', []) if v.get('name') == VARIABLE), None)
    service = next((s for s in caps.get('services', []) if s.get('capabilities', {}).get('subsetting', {}).get('bbox')
                    and s['capabilities']['subsetting'].get('variable')
                    and any(f.get('mimeType') == 'image/tiff' for f in s['capabilities'].get('outputFormats', []))), None)
    if not var or not service:
        fail(422, 'unsupported_service', 'Live collection services do not advertise the requested extraction.')
    # Confirm collection-to-service association and explicit COG output.
    sid = service['href'].rsplit('/', 1)[-1]
    if not re.fullmatch(r'S\d+-ASF', sid):
        fail(422, 'unsupported_service', 'Unexpected service metadata reference.')
    services = await cmr.request('services.umm_json', {'concept_id': sid})
    service_record = next((s for s in services.get('items', []) if collection['id'] in s['meta'].get('associations', {}).get('collections', [])), None)
    formats = (service_record or {}).get('umm', {}).get('ServiceOptions', {}).get('SupportedReformattings', [])
    if not any('COG' in f.get('SupportedOutputFormats', []) and f.get('SupportedInputFormat') == 'HDF5' for f in formats):
        fail(422, 'unsupported_service', 'Associated service does not confirm HDF5-to-COG conversion.')
    vid = var['href'].rsplit('/', 1)[-1]
    if not re.fullmatch(r'V\d+-ASF', vid):
        fail(422, 'unsupported_variable', 'Unexpected variable metadata reference.')
    w, s, e, n = body.bbox
    params = [('granuleId', scene['id']), ('subset', f'lon({w}:{e})'), ('subset', f'lat({s}:{n})'),
              ('format', 'image/tiff'), ('forceAsync', 'true'), ('maxResults', '1'), ('ignoreErrors', 'false')]
    url = str(httpx.URL(f'{ROOT}/{collection["id"]}/ogc-api-coverages/1.0.0/collections/{vid}/coverage/rangeset', params=params))
    return {'request_url': url, 'method': 'GET', 'bbox': body.bbox, 'variable': VARIABLE,
            'variable_id': vid, 'scene': scene, 'collection': collection,
            'granule_revision': item['meta'].get('revision-id'), 'service_id': sid,
            'service_version': service_record['umm'].get('Version'), 'planned_at': stamp(),
            'analysis_ready': False, 'notice': 'Candidate extraction only. No mangrove change or scientific readiness is established.'}


class Manager:
    def __init__(self, settings=None, transport=None):
        self.settings = settings or Settings()
        self.transport = transport or Transport(self.settings)
        self.lock = asyncio.Lock()

    def path(self, job_id, suffix='.json'):
        try:
            job_id = str(UUID(job_id))
        except ValueError:
            fail(404, 'job_not_found', 'Processing job not found.')
        root = self.settings.cache.resolve()
        path = root / (job_id + suffix)
        if path.is_symlink() or path.resolve().parent != root:
            fail(500, 'unsafe_cache', 'Unsafe cache entry.')
        return path

    def save(self, job):
        self.settings.cache.mkdir(parents=True, exist_ok=True)
        existing = self.path(job['id'])
        if existing.exists():
            job['cancel_requested'] = job['cancel_requested'] or json.loads(existing.read_text(encoding='utf-8')).get('cancel_requested', False)
        job['updated_at'] = stamp()
        tmp = self.path(job['id'], '.tmp')
        tmp.write_text(json.dumps(job, indent=2, allow_nan=False), encoding='utf-8')
        tmp.replace(self.path(job['id']))

    def jobs(self):
        result = []
        for p in self.settings.cache.glob('*.json'):
            if not p.is_symlink() and re.fullmatch(r'[0-9a-f-]{36}', p.stem):
                result.append(json.loads(p.read_text(encoding='utf-8')))
        return sorted(result, key=lambda j: j['created_at'])

    def get(self, job_id):
        path = self.path(job_id)
        if not path.exists():
            fail(404, 'job_not_found', 'Processing job not found or expired.')
        return json.loads(path.read_text(encoding='utf-8'))

    def cleanup(self):
        now = time.time()
        jobs = self.jobs()
        protected = {j.get('reference_job_id') for j in jobs if j['status'] in ACTIVE}
        for job in jobs:
            unresolved = job['status'] == 'submission_unknown' or (job.get('remote_job_id') and not job.get('remote_terminal') and not job.get('remote_cancel_confirmed'))
            if job['status'] in TERMINAL and not unresolved and job['id'] not in protected and now - job['created_epoch'] > self.settings.ttl:
                for suffix in ['.tif', '.part', '.json', '.tmp']:
                    self.path(job['id'], suffix).unlink(missing_ok=True)
        # Abandoned partial files from an interrupted download cannot grow forever.
        for p in self.settings.cache.glob('*.part'):
            if now - p.stat().st_mtime > self.settings.ttl:
                self.path(p.stem, '.part').unlink(missing_ok=True)
        for suffix in ['.tmp', '.tif']:
            for p in self.settings.cache.glob('*' + suffix):
                if now - p.stat().st_mtime > self.settings.ttl and not self.path(p.stem).exists():
                    self.path(p.stem, suffix).unlink(missing_ok=True)

    def usage(self):
        return sum(p.stat().st_size for p in self.settings.cache.iterdir() if p.is_file()) if self.settings.cache.exists() else 0

    def capabilities(self):
        self.cleanup()
        first = next((j for j in self.jobs() if j['status'] == 'verified' and j['plan']['scene']['id'] == CANDIDATES[0]
                      and self.path(j['id'], '.tif').exists()), None)
        return {'implemented': True, 'phase': '2B', 'real_processing_enabled': self.settings.enabled,
                'authentication_configured': self.settings.authentication_configured,
                'authentication_method': self.settings.auth_mode, 'raw_file_upload_required': False,
                'authentication_verified': bool(getattr(getattr(self.transport, '_password_session', None), 'authenticated', False)),
                'state': 'authentication_required' if not self.settings.authentication_configured else ('ready' if self.settings.enabled else 'processing_disabled'),
                'candidate_ids': CANDIDATES, 'subset_bbox': SMALL_BBOX, 'variable': VARIABLE,
                'second_scene_unlocked': bool(first), 'limits': {'file_bytes': self.settings.max_file_bytes,
                'cache_bytes': self.settings.max_cache_bytes, 'retention_seconds': self.settings.ttl,
                'job_timeout_seconds': self.settings.timeout, 'max_jobs': self.settings.max_jobs, 'concurrent_jobs': 1},
                'analysis_ready': False}

    def authorize(self):
        if not self.settings.authentication_configured:
            fail(401, 'authentication_required', 'Configure credentials for the selected HARMONY_AUTH_MODE only in the server environment or ignored .env, then restart the backend.')
        if not self.settings.enabled:
            fail(409, 'processing_disabled', 'Set HARMONY_PROCESSING_ENABLED=true on the server to explicitly enable real extraction. Dry-run remains available.')

    async def submit(self, body):
        if not body.dry_run:
            self.authorize()
        try:
            async with asyncio.timeout(40):
                plan = await build_plan(body, self.transport)
        except TimeoutError:
            fail(504, 'preflight_timeout', 'NASA metadata preflight timed out. No processing request was submitted.')
        if body.dry_run:
            return {'status': 'dry_run', 'submitted': False, 'plan': plan, 'setup': self.capabilities()}
        async with self.lock, admission(self.settings.cache):
            self.cleanup()
            jobs = self.jobs()
            prior = next((j for j in jobs if j['plan']['scene']['id'] == body.granule_id and j['plan']['bbox'] == body.bbox), None)
            if prior and prior['status'] == 'authentication_required' and not prior.get('remote_job_id'):
                prior = None  # Definitive authentication rejection is safe to retry after setup.
            if prior:
                return prior  # Idempotent: a browser retry never submits a duplicate.
            if any(j['status'] in ACTIVE or j['status'] == 'submission_unknown' or
                   (j.get('remote_job_id') and not j.get('remote_terminal') and not j.get('remote_cancel_confirmed')) for j in jobs):
                fail(409, 'job_in_progress', 'A job is active or its submission needs reconciliation. No additional job was submitted.')
            reference = next((j for j in jobs if j['status'] == 'verified' and j['plan']['scene']['id'] == CANDIDATES[0]
                              and j['plan']['bbox'] == body.bbox and self.path(j['id'], '.tif').exists()), None)
            if body.granule_id == CANDIDATES[1] and not reference:
                fail(409, 'first_scene_required', 'First candidate must have a verified COG for the same subset before processing the second.')
            if len(jobs) >= self.settings.max_jobs or self.usage() + self.settings.max_file_bytes + 1024 * 1024 > self.settings.max_cache_bytes:
                fail(507, 'cache_full', 'Bounded processing cache is full. Expired jobs are cleaned automatically.')
            job = {'id': str(uuid4()), 'status': 'queued', 'progress': 0, 'created_at': stamp(), 'created_epoch': time.time(),
                   'plan': plan, 'remote_job_id': None, 'cancel_requested': False, 'raster': None, 'alignment': None,
                   'submission_attempted': False,
                   'reference_job_id': reference['id'] if reference and body.granule_id == CANDIDATES[1] else None,
                   'error': None, 'analysis_ready': False}
            self.save(job)
            return job

    async def cancel(self, job_id):
        async with self.lock:
            job = self.get(job_id)
            if job['status'] in TERMINAL:
                return job
            job['cancel_requested'] = True
            if job['status'] == 'queued':
                job['status'] = 'canceled'
            self.save(job)
            return job

    async def remote_cancel(self, job):
        if not job['remote_job_id'] or not self.settings.authentication_configured:
            return False
        try:
            data = await self.transport.json(f'{ROOT}/jobs/{job["remote_job_id"]}/cancel', auth=True, retry=False)
            return data.get('status') == 'canceled'
        except HTTPException:
            return False

    async def run(self, job):
        with file_lock(self.settings.cache, 'worker') as owned:
            if not owned:
                return  # Another API/CLI worker owns processing; never resubmit.
            current = self.get(job['id'])
            if current['status'] in ACTIVE:
                await self._run(current)

    async def _run(self, job):
        try:
            if time.time() - job['created_epoch'] >= self.settings.timeout:
                raise TimeoutError()
            self.authorize()
            async with asyncio.timeout(max(.01, self.settings.timeout - (time.time() - job['created_epoch']))):
                if not job['remote_job_id']:
                    if job['status'] != 'queued':
                        job['status'] = 'submission_unknown'
                        job['error'] = {'code': 'submission_unknown', 'message': 'Submission may have reached NASA. Reconcile it before another request; it was not retried.'}
                        return
                    job['status'] = 'submitting'
                    job['submission_attempted'] = True
                    self.save(job)  # Journal before network: crash recovery must not repeat submission.
                    try:
                        data = await self.transport.json(job['plan']['request_url'], auth=True, retry=False)
                        job['remote_job_id'] = str(UUID(data['jobID']))
                    except (HTTPException, KeyError, ValueError) as exc:
                        job['status'] = 'authentication_required' if isinstance(exc, HTTPException) and exc.status_code == 401 else 'submission_unknown'
                        job['error'] = {'code': job['status'], 'message': 'NASA submission was not confirmed. It was not automatically repeated; review server authentication or reconcile NASA jobs.'}
                        return
                    job['status'] = 'running'
                    self.save(job)
                while True:
                    if self.get(job['id'])['cancel_requested']:
                        job['cancel_requested'] = True
                        if await self.remote_cancel(job):
                            job['remote_cancel_confirmed'] = True
                            job['status'] = 'canceled'
                            return
                        job['status'] = 'cancel_pending'
                    data = await self.transport.json(f'{ROOT}/jobs/{job["remote_job_id"]}?linktype=https', auth=True)
                    remote = data.get('status')
                    progress = float(data.get('progress', 0))
                    job['progress'] = max(0, min(100, progress)) if math.isfinite(progress) else 0
                    if remote in {'failed', 'complete_with_errors', 'canceled'}:
                        job['remote_terminal'] = True
                        job['status'] = 'canceled' if remote == 'canceled' else 'failed'
                        job['error'] = {'code': 'remote_' + remote, 'message': 'NASA job ended without a complete verified output.'}
                        return
                    if remote == 'successful':
                        job['remote_terminal'] = True
                        if job['cancel_requested']:
                            job['status'] = 'canceled'
                            return
                        links = [x for x in data.get('links', []) if x.get('rel') == 'data']
                        if len(links) != 1 or not links[0].get('href'):
                            fail(502, 'missing_output', 'Expected exactly one completed radar output; no file was accepted.')
                        job['status'] = 'downloading'
                        job['output_expires_at'] = data.get('dataExpiration')
                        self.save(job)
                        path = self.path(job['id'], '.part')
                        budget = min(self.settings.max_file_bytes, self.settings.max_cache_bytes - self.usage() - 1024 * 1024)
                        if budget <= 0:
                            fail(507, 'cache_full', 'Processing cache budget exhausted.')
                        # Retry download (not submission) at most three times; overwrite partials.
                        for attempt in range(3):
                            try:
                                await self.transport.download(links[0]['href'], path, budget)
                                break
                            except HTTPException as exc:
                                path.unlink(missing_ok=True)
                                if exc.status_code != 502 or attempt == 2:
                                    raise
                                await asyncio.sleep(2 ** attempt)
                        job['status'] = 'validating'
                        self.save(job)
                        job['raster'] = inspect_cog(path, job['plan'], links[0]['href'])
                        if job['reference_job_id']:
                            job['alignment'] = check_alignment(self.path(job['reference_job_id'], '.tif'), path)
                        if self.get(job['id'])['cancel_requested']:
                            job['status'] = 'canceled'
                            job['raster'] = None
                            job['alignment'] = None
                            return
                        path.replace(self.path(job['id'], '.tif'))
                        job['status'] = 'verified'
                        return
                    if remote not in {'accepted', 'queued', 'running', 'paused', 'previewing'}:
                        fail(502, 'unknown_remote_state', 'NASA returned an unsupported job state. No output was accepted.')
                    job['status'] = 'cancel_pending' if job['cancel_requested'] else ('paused' if remote == 'paused' else 'running')
                    self.save(job)
                    await asyncio.sleep(self.settings.poll)
        except TimeoutError:
            job['status'] = 'timed_out'
            job['remote_cancel_confirmed'] = await self.remote_cancel(job)
            job['error'] = {'code': 'job_timeout', 'message': 'Local deadline exceeded. Remote cancellation was attempted; check confirmation before assuming NASA stopped.'}
        except HTTPException as exc:
            job['status'] = 'authentication_required' if exc.status_code == 401 else 'failed'
            job['error'] = exc.detail
            job['raster'] = None
        except Exception:
            # Do not serialize exception strings: HTTP/raster errors can include signed URLs.
            job['status'] = 'failed'
            job['error'] = {'code': 'validation_failed', 'message': 'Output validation or job handling failed. No validated raster is available.'}
            job['raster'] = None
        finally:
            if job.get('remote_job_id') and job['status'] in {'failed', 'authentication_required'} and not job.get('remote_terminal'):
                job['remote_cancel_confirmed'] = await self.remote_cancel(job)
            self.path(job['id'], '.part').unlink(missing_ok=True)
            self.save(job)

    async def worker(self):
        while True:
            self.cleanup()
            job = next((j for j in self.jobs() if j['status'] in ACTIVE), None)
            if job:
                await self.run(job)
            await asyncio.sleep(1)


manager = Manager()
