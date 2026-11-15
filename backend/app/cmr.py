"""NASA CMR adapter. Public discovery; optional credentials stay on the server."""
import asyncio
import time
import httpx
from fastapi import HTTPException
from .config import CMR_BASE, TOKEN, TIMEOUT, CACHE_SECONDS

_cache = {}
_locks = {}


async def request(path, params=None):
    key = (path, tuple(sorted((params or {}).items())))
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
        return cached[1]
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        cached = _cache.get(key)
        if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
            return cached[1]
        headers = {'Client-Id': 'ForestPulse-Phase1', 'Accept': 'application/json'}
        if TOKEN:
            headers['Authorization'] = f'Bearer {TOKEN}'
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as client:
                response = await client.get(f'{CMR_BASE}/{path}', params=params, headers=headers)
            if response.status_code in (401, 403):
                raise HTTPException(401, detail={'code': 'authentication_required', 'message': 'NASA requires authentication for this request. Configure a valid EARTHDATA_TOKEN on the server; never enter it in the browser.'})
            if response.status_code == 404:
                raise HTTPException(404, detail={'code': 'not_found', 'message': 'NASA CMR did not find this metadata record.'})
            if response.status_code == 429:
                raise HTTPException(503, detail={'code': 'rate_limited', 'message': 'NASA CMR rate limit reached. Please retry shortly.'})
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(502, detail={'code': 'upstream_error', 'message': 'NASA CMR is unavailable or returned an invalid response. Retry discovery; no fallback scenes are fabricated.'}) from exc
        if len(_cache) > 256:
            _cache.clear()
            # Locks remain bounded by the API request space in normal local use.
        _cache[key] = (time.monotonic(), data)
        return data


async def collections(product=None):
    result = await request('collections.umm_json', {'keyword': 'NISAR', 'page_size': 200})
    records = []
    for item in result.get('items', []):
        u, m = item['umm'], item['meta']
        name = u.get('ShortName', '')
        if not name.startswith('NISAR_') or (product and f'_{product}_' not in name):
            continue
        records.append({'id': m['concept-id'], 'short_name': name, 'title': u.get('EntryTitle', name),
                        'version': u.get('Version'), 'provider': m.get('provider-id'),
                        'maturity': 'provisional' if 'PROVISIONAL' in name else ('beta' if 'BETA' in name else ('validated' if 'Validated' in u.get('EntryTitle', '') else 'unspecified')),
                        'metadata_url': f"{CMR_BASE}/concepts/{m['concept-id']}.umm_json"})
    records.sort(key=lambda c: ({'validated': 0, 'provisional': 1, 'beta': 2}.get(c['maturity'], 3), c['short_name']))
    return records


async def validate_collection(concept_id):
    records = await collections()
    found = next((c for c in records if c['id'] == concept_id), None)
    if not found:
        raise HTTPException(422, detail={'code': 'invalid_collection', 'message': 'Choose a NISAR collection returned by live collection discovery.'})
    return found


async def granule(concept_id):
    raw = await request(f'concepts/{concept_id}.umm_json')
    # The single-concept endpoint returns a UMM document, without search meta wrapping.
    umm = raw.get('umm', raw)
    if not umm.get('CollectionReference', {}).get('ShortName', '').startswith('NISAR_'):
        raise HTTPException(422, detail={'code': 'invalid_scene', 'message': 'Only NISAR granules can be screened.'})
    coll = next((c for c in await collections() if c['short_name'] == umm['CollectionReference']['ShortName'] and c['version'] == umm['CollectionReference'].get('Version')), None)
    return {'meta': {'concept-id': concept_id, 'collection-concept-id': coll['id'] if coll else None}, 'umm': umm}
