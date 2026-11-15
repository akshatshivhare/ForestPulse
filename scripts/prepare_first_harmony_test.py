"""Preparation only: public metadata and an existing backend dry-run.

Never starts a worker, sends authentication, touches processing endpoints or
downloads imagery. Only the local non-secret authentication selector is edited.
"""
import argparse
import asyncio
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import urlencode, urlsplit

from dotenv import dotenv_values


def prepare_config(path):
    if path.is_symlink() or not path.is_file():
        raise RuntimeError('Use a regular local .env file with existing credentials.')
    original = path.read_bytes()
    before = dotenv_values(stream=io.StringIO(original.decode('utf-8-sig')))
    if str(before.get('HARMONY_PROCESSING_ENABLED', '')).lower() != 'false':
        raise RuntimeError('Processing must already be explicitly false; no configuration changed.')
    if not before.get('EDL_USERNAME', '').strip() or not before.get('EDL_PASSWORD', ''):
        raise RuntimeError('Existing server-side EDL username/password are required.')
    # Byte-preserving replacement leaves credential lines and line endings alone.
    pattern = rb'(?m)^[ \t]*(?:export[ \t]+)?HARMONY_AUTH_MODE[ \t]*=[^\r\n]*'
    updated, count = re.subn(pattern, b'HARMONY_AUTH_MODE=earthdata_password', original)
    if not count:
        newline = b'\r\n' if b'\r\n' in original else b'\n'
        updated = original + (b'' if original.endswith(b'\n') else newline) + b'HARMONY_AUTH_MODE=earthdata_password' + newline
    after = dotenv_values(stream=io.StringIO(updated.decode('utf-8-sig')))
    if {k:v for k,v in before.items() if k != 'HARMONY_AUTH_MODE'} != {k:v for k,v in after.items() if k != 'HARMONY_AUTH_MODE'}:
        raise RuntimeError('Non-selector settings changed; refusing to write.')
    if updated != original:
        path.write_bytes(updated)
    return {'auth_mode': 'earthdata_password', 'credentials_present': True,
            'credentials_preserved': True, 'processing_enabled': False,
            'selector_changed': updated != original}


def estimate(bbox):
    w,s,e,n = bbox
    width = 6371008.8 * math.radians(e-w) * math.cos(math.radians((s+n)/2))
    height = 6371008.8 * math.radians(n-s)
    cols, rows = math.ceil(width/10), math.ceil(height/10)
    return {'method': 'spherical ground-size approximation, nominal 10m grid, one float32 band',
            'approx_width_m': round(width,1), 'approx_height_m': round(height,1),
            'nominal_pixel_spacing_m':10, 'approx_columns':cols, 'approx_rows':rows,
            'approx_pixels':cols*rows, 'uncompressed_samples_bytes_estimate':cols*rows*4,
            'actual_grid_and_cog_size_verified':False,
            'warning':'Excludes tiling, projection rotation, overviews, masks, metadata and compression; not an actual output size.'}


def listed_browse_layers(umm):
    # ASF names these artifacts NATIVE_A_HHHH, not frequencyA_HHHH.
    return sorted({Path(urlsplit(x.get('URL','')).path).name for x in umm.get('RelatedUrls',[])
                   if x.get('Type')=='GET RELATED VISUALIZATION'
                   and Path(urlsplit(x.get('URL','')).path).name.endswith('_NATIVE_A_HHHH.png')})


async def dry_run():
    from fastapi import HTTPException
    from shapely.geometry import box, shape
    from backend.app import cmr, harmony
    from backend.app.config import CMR_BASE, PILOT_BBOX
    if cmr.TOKEN or CMR_BASE != 'https://cmr.earthdata.nasa.gov/search':
        raise RuntimeError('Preparation requires public CMR on the official origin without a bearer header.')
    settings = harmony.Settings()
    if settings.enabled or settings.auth_mode != 'earthdata_password' or not settings.authentication_configured:
        raise RuntimeError('Password mode and disabled processing are required.')
    sources, documents = [], {}
    original_request = cmr.request

    async def metadata(path, params=None):
        if path not in {'granules.umm_json','collections.umm_json','services.umm_json'}:
            raise RuntimeError('Only public CMR discovery is allowed.')
        data = await original_request(path,params)
        documents[path] = data
        sources.append({'url':CMR_BASE+'/'+path+'?'+urlencode(params or {}), 'retrieved_at_utc':harmony.stamp(),
            'http_result':'successful_json', 'sha256_canonical_json':hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()})
        return data

    class PreparationTransport(harmony.Transport):
        async def json(self,url,*,auth=False,retry=True):
            u = urlsplit(url)
            if auth or u.scheme!='https' or u.netloc!='harmony.earthdata.nasa.gov' or u.path!='/capabilities':
                raise RuntimeError('Processing and authentication requests are forbidden during preparation.')
            data = await super().json(url,auth=False,retry=False)
            documents['capabilities'] = data
            sources.append({'url':url, 'retrieved_at_utc':harmony.stamp(), 'http_result':'successful_json',
                'sha256_canonical_json':hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()})
            return data

        async def download(self,*_args,**_kwargs):
            raise RuntimeError('All downloads are forbidden during preparation.')

    cmr.request = metadata
    transport = PreparationTransport(settings)
    manager = harmony.Manager(settings,transport)
    before = len(manager.jobs())
    report = {'started_at_utc':harmony.stamp(), 'auth_mode':settings.auth_mode,
              'credentials_configured':settings.authentication_configured, 'token_used':False,
              'pilot_bbox':PILOT_BBOX, 'candidate_ids':harmony.CANDIDATES,
              'processing_enabled_before':settings.enabled, 'jobs_before':before,
              'processing_requests_sent':0, 'downloads_attempted':0, 'new_login_attempted':False}
    try:
        if before:
            raise RuntimeError('Existing local jobs need reconciliation before preparation.')
        try:
            manager.authorize()  # Pure local gate check; never calls submit/worker.
        except HTTPException as exc:
            if exc.status_code != 409 or exc.detail['code'] != 'processing_disabled':
                raise
            report['submission_gate'] = 'processing_disabled'
        async with asyncio.timeout(45):
            result = await manager.submit(harmony.Extraction(granule_id=harmony.CANDIDATES[0],dry_run=True))
        plan, setup = result['plan'], result['setup']
        scene = plan['scene']
        if scene['footprint_source']!='polygon' or not shape(scene['geometry']).is_valid or not shape(scene['geometry']).covers(box(*plan['bbox'])):
            raise RuntimeError('Requested subset is not contained in an actual valid metadata polygon.')
        if scene['bandwidth_mhz'].get('A') not in ('40','40.0'):
            raise RuntimeError('Nominal 10m estimate requires the confirmed 40MHz acquisition.')
        umm = documents['granules.umm_json']['items'][0]['umm']
        services = documents['services.umm_json']['items']
        service = next(x['umm'] for x in services if x['meta']['concept-id']==plan['service_id'])
        caps = documents['capabilities']
        service_caps = next(x for x in caps['services'] if x['href'].endswith(plan['service_id']))
        variable = next(x for x in caps['variables'] if x.get('name')==plan['variable'])
        report.update(status='READY', readiness_scope='bounded first extraction experiment pending explicit authorization; not scientific or valid-pixel readiness',
            dry_run=result, sources=sources,
            coverage={'metadata_polygon_valid':True, 'subset_contained_in_actual_cmr_polygon':True,
                      'subset_footprint_coverage_percent':scene['aoi_coverage_percent_approx'],
                      'actual_radar_valid_pixels_verified':False, 'mangrove_mask_intersection_verified':False},
            scene_layer_evidence={'frequencyA_HHHH_browse_listed':bool(listed_browse_layers(umm)),
                                  'listed_browse_names':listed_browse_layers(umm), 'browse_downloaded':False,
                                  'source_array_inspected':False},
            service={'name':service.get('Name'), 'version':service.get('Version'),
                     'capabilities':service_caps.get('capabilities'),
                     'reformatting':service.get('ServiceOptions',{}).get('SupportedReformattings',[])},
            variable_metadata={k:v for k,v in variable.items() if k not in {'href'}},
            estimated_output=estimate(plan['bbox']), limits=setup['limits'], cache_usage_bytes=manager.usage(),
            local_free_bytes=shutil.disk_usage(settings.cache.parent).free,
            authentication_evidence='docs/harmony-backend-password-auth.json',
            actual_processing_or_output_verified=False)
    except HTTPException as exc:
        report.update(status='BLOCKED', failure_category=exc.detail['code'])
    except TimeoutError:
        report.update(status='BLOCKED',failure_category='metadata_preflight_timeout')
    except Exception:
        report.update(status='BLOCKED',failure_category='local_preparation_check_failed')
    finally:
        cmr.request = original_request
        transport.close()
        report.update(jobs_after=len(manager.jobs()),processing_enabled_after=settings.enabled,finished_at_utc=harmony.stamp())
    if report['jobs_after'] != before or report['processing_enabled_after']:
        report.update(status='BLOCKED',failure_category='local_safety_gate_failed')
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--child',action='store_true',help=argparse.SUPPRESS)
    args = p.parse_args()
    if args.child:
        print(json.dumps(asyncio.run(dry_run()),allow_nan=False),flush=True)
        return
    from dotenv import load_dotenv
    load_dotenv()
    if os.getenv('HARMONY_PROCESSING_ENABLED','').lower()!='false':
        raise RuntimeError('Effective processing configuration must remain explicitly false.')
    configuration = prepare_config(Path('.env'))
    env = os.environ.copy()
    env.update(HARMONY_AUTH_MODE='earthdata_password',HARMONY_PROCESSING_ENABLED='false',EARTHDATA_TOKEN='')
    try:
        child = subprocess.run([sys.executable,'-m','scripts.prepare_first_harmony_test','--child'],
            env=env,capture_output=True,text=True,timeout=55,check=False)
        report = json.loads(child.stdout) if child.returncode==0 else {'status':'BLOCKED','failure_category':'preparation_process_error'}
    except subprocess.TimeoutExpired:
        report = {'status':'BLOCKED','failure_category':'outer_preparation_deadline'}
    report['configuration'] = configuration
    report['outer_deadline_seconds'] = 55
    payload = json.dumps(report,indent=2,allow_nan=False)+'\n'
    for key in ('EDL_USERNAME','EDL_PASSWORD','EARTHDATA_TOKEN'):
        if os.getenv(key) and os.getenv(key) in payload:
            raise RuntimeError('Redaction check failed; no report written.')
    Path('docs/harmony-first-test-readiness.json').write_text(payload,encoding='utf-8')
    print(json.dumps({k:report.get(k) for k in ('status','failure_category','jobs_before','jobs_after','processing_enabled_after')},indent=2))


if __name__=='__main__':
    main()
