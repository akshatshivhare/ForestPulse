"""Public metadata/dry-run only. No transformation, worker or download path.

Losslessly reconcile the already revalidated first COG with its original local
job record, only after request checks pass. Processing is never enabled.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import parse_qs,urlencode,urlsplit

from scripts.prepare_first_harmony_test import estimate,listed_browse_layers

FIRST='G4405780437-ASF'
SECOND='G4405182121-ASF'
BBOX=[88.75,21.85,88.78,21.88]
VARIABLE='/science/LSAR/GCOV/grids/frequencyA/HHHH'
AUDIT=Path('artifacts/harmony-spatial-audit')


def digest(path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            value.update(chunk)
    return value.hexdigest()


def register_first_reference(manager,local_id,source,identity_filename,expected_sha):
    """No NASA activity; keep an exact original-record backup and audit raster."""
    from backend.app.harmony import file_lock,stamp
    from backend.app.rasters import inspect_cog
    if manager.settings.enabled:
        raise RuntimeError('Registration requires disabled processing.')
    if source.is_symlink() or digest(source)!=expected_sha:
        raise RuntimeError('First COG is missing, replaced or changed.')
    if source.stat().st_size>manager.settings.max_file_bytes:
        raise RuntimeError('First reference exceeds the per-file storage budget.')
    with file_lock(manager.settings.cache,'worker') as owned:
        if not owned:
            raise RuntimeError('An existing worker is active.')
        job=manager.get(local_id)
        if (job['plan']['scene']['id']!=FIRST or job['plan']['bbox']!=BBOX or job['plan']['variable']!=VARIABLE
                or not job.get('remote_terminal') or not job.get('remote_job_id')):
            raise RuntimeError('First-reference provenance does not match the completed test.')
        verified=inspect_cog(source,job['plan'],identity_filename)
        target=manager.path(local_id,'.tif')
        if target.exists() and digest(target)!=expected_sha:
            raise RuntimeError('Existing reference file differs; no data overwritten.')
        if job['status']=='verified' and target.exists() and (job.get('raster') or {}).get('verified') and job['raster'].get('sha256')==expected_sha:
            return {'registered':True,'changed':False,'source_sha256':expected_sha,'reference_sha256':digest(target)}
        if job['status']!='failed' or (job.get('error') or {}).get('code') not in {'extent_mismatch','validation_failed'}:
            raise RuntimeError('Only the historical spatial rejection can be reconciled.')
        record=manager.path(local_id)
        original=record.read_bytes()
        backup=source.parent/'first-job-before-reference-registration.json'
        if not backup.exists():
            with backup.open('xb') as out:
                out.write(original)
        elif backup.read_bytes()!=original:
            raise RuntimeError('Existing backup differs; no provenance overwritten.')
        if manager.usage()+source.stat().st_size+1024*1024>manager.settings.max_cache_bytes:
            raise RuntimeError('First reference would exceed storage budget.')
        created=False
        try:
            if not target.exists():
                with source.open('rb') as inp,target.open('xb') as out:
                    created=True
                    shutil.copyfileobj(inp,out,64*1024)
            if digest(target)!=expected_sha or digest(source)!=expected_sha:
                raise RuntimeError('Reference copy verification failed.')
            job['local_spatial_revalidation']={'checked_at_utc':stamp(),'previous_status':job['status'],
                'previous_error':job.get('error'),'previous_record_sha256':hashlib.sha256(original).hexdigest(),
                'raster_sha256':expected_sha,'method':'local inspect_cog with CRS-aware crop policy',
                'new_harmony_job_submitted':False}
            job.update(status='verified',raster=verified,error=None,analysis_ready=False)
            manager.save(job)
        except Exception:
            if created:
                target.unlink(missing_ok=True)
            raise
        return {'registered':True,'changed':True,'source_sha256':expected_sha,'reference_sha256':digest(target),
                'original_record_backup':str(backup.as_posix()),'original_record_sha256':hashlib.sha256(original).hexdigest(),
                'existing_local_job_id':local_id,'new_local_job_created':False,'new_harmony_job_submitted':False}


def request_checks(plan,comparison):
    u=urlsplit(plan['request_url'])
    expected={'granuleId':[SECOND],'subset':['lon(88.75:88.78)','lat(21.85:21.88)'],
              'format':['image/tiff'],'forceAsync':['true'],'maxResults':['1'],'ignoreErrors':['false']}
    if (plan['scene']['id']!=SECOND or plan['bbox']!=BBOX or plan['variable']!=VARIABLE
            or u.scheme!='https' or u.netloc!='harmony.earthdata.nasa.gov'
            or u.path!='/C3622241360-ASF/ogc-api-coverages/1.0.0/collections/V4137651715-ASF/coverage/rangeset'
            or parse_qs(u.query)!=expected):
        raise RuntimeError('Second request does not match the frozen candidate, AOI and layer.')
    if comparison['status']=='incompatible':
        raise RuntimeError('Scene metadata contains a known incompatibility.')


async def prepare():
    from fastapi import HTTPException
    from shapely.geometry import box,shape
    from backend.app import cmr,harmony
    from backend.app.science import normalize,compare
    settings=harmony.Settings()
    if settings.enabled or settings.auth_mode!='earthdata_password' or not settings.authentication_configured or cmr.TOKEN:
        raise RuntimeError('Require password configuration, disabled processing and public metadata without bearer use.')
    if cmr.CMR_BASE!='https://cmr.earthdata.nasa.gov/search':
        raise RuntimeError('Require the official CMR origin.')
    evidence=json.loads(Path('docs/harmony-spatial-validation.json').read_text())
    history=json.loads(Path('docs/harmony-first-live-test.json').read_text())
    identity=json.loads((AUDIT/'output-identity.json').read_text())
    source=AUDIT/'first-real-cog.tif'
    baseline_sha=digest(source)
    if evidence['verdict']!='VALID' or baseline_sha!=evidence['sha256']:
        raise RuntimeError('Verified first-scene cache does not match evidence.')
    sources=[]
    documents={}
    original=cmr.request

    async def metadata(path,params=None):
        if path not in {'granules.umm_json','collections.umm_json','services.umm_json'}:
            raise RuntimeError('Only CMR metadata is allowed.')
        data=await original(path,params)
        documents[(path,str((params or {}).get('concept_id','')))]=data
        sources.append({'url':cmr.CMR_BASE+'/'+path+'?'+urlencode(params or {}),
            'retrieved_at_utc':harmony.stamp(),'result':'successful_json',
            'sha256_canonical_json':hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()})
        return data

    class DryOnly(harmony.Transport):
        async def json(self,url,*,auth=False,retry=True):
            u=urlsplit(url)
            if auth or u.scheme!='https' or u.netloc!='harmony.earthdata.nasa.gov' or u.path!='/capabilities':
                raise RuntimeError('No authentication, processing or job-control request is allowed.')
            data=await super().json(url,auth=False,retry=False)
            documents[('capabilities','')]=data
            sources.append({'url':url,'retrieved_at_utc':harmony.stamp(),'result':'successful_json',
                'sha256_canonical_json':hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()})
            return data
        async def download(self,*_args,**_kwargs):
            raise RuntimeError('No satellite or other download is allowed.')

    cmr.request=metadata
    transport=DryOnly(settings)
    m=harmony.Manager(settings,transport)
    before=len(m.jobs())
    report={'started_at_utc':harmony.stamp(),'status':'BLOCKED','auth_mode':settings.auth_mode,
        'processing_enabled_before':False,'processing_submissions':0,'downloads':0,'jobs_before':before,
        'pilot_bbox':[88.4,21.55,89.1,22.25],'subset_bbox':BBOX,'scientific_comparison_ready':False,
        'first_cache_sha256_before':baseline_sha,'first_reference_gate_before':m.capabilities()['second_scene_unlocked']}
    try:
        if any(j['status'] in harmony.ACTIVE or j['status']=='submission_unknown' or
               (j.get('remote_job_id') and not j.get('remote_terminal') and not j.get('remote_cancel_confirmed')) for j in m.jobs()):
            raise RuntimeError('Existing unresolved work blocks preparation.')
        try:
            m.authorize()
        except HTTPException as exc:
            if exc.status_code!=409 or exc.detail['code']!='processing_disabled':
                raise
            report['submission_gate']='processing_disabled'
        async with asyncio.timeout(45):
            dry=await m.submit(harmony.Extraction(granule_id=SECOND,bbox=BBOX,dry_run=True))
            first_raw=await cmr.request('granules.umm_json',{'concept_id':FIRST,'page_size':1})
        first=normalize(first_raw['items'][0],BBOX)
        second=dry['plan']['scene']
        comparison=compare(first,second,BBOX)
        request_checks(dry['plan'],comparison)
        second_umm=documents[('granules.umm_json',SECOND)]['items'][0]['umm']
        first_umm=first_raw['items'][0]['umm']
        if (second['footprint_source']!='polygon' or not shape(second['geometry']).is_valid
                or not shape(second['geometry']).covers(box(*BBOX))):
            raise RuntimeError('The actual second metadata polygon does not contain the subset.')
        if first['name']!=history['plan']['scene']['name'] or first['product_version']!=history['plan']['scene']['product_version']:
            raise RuntimeError('First-scene identity/version has changed since the cached extraction.')
        if second['bandwidth_mhz'].get('A') not in ('40','40.0'):
            raise RuntimeError('Nominal 10m resource estimate no longer applies.')
        service_record=documents[('services.umm_json',dry['plan']['service_id'])]['items'][0]
        caps=documents[('capabilities','')]
        target=next(v for v in caps['variables'] if v.get('name')==VARIABLE)
        report.update(dry_run=dry,first_current_metadata=first,comparison=comparison,sources=sources,
            first_granule_revision=first_raw['items'][0]['meta'].get('revision-id'),
            geometry_metadata={'first_orbit_domains':first_umm.get('OrbitCalculatedSpatialDomains'),
                'second_orbit_domains':second_umm.get('OrbitCalculatedSpatialDomains'),
                'first_pge':first_umm.get('PGEVersionClass'),'second_pge':second_umm.get('PGEVersionClass')},
            service={'id':dry['plan']['service_id'],'name':service_record['umm'].get('Name'),
                'version':service_record['umm'].get('Version'),
                'reformatting':service_record['umm'].get('ServiceOptions',{}).get('SupportedReformattings')},
            selected_variable={k:v for k,v in target.items() if k!='href'},
            advertised_covariance_variables=[v['name'] for v in caps['variables'] if v.get('name','').endswith(('/HHHH','/HVHV'))],
            second_browse_evidence={'frequencyA_HHHH_listed':bool(listed_browse_layers(second_umm)),
                'filenames':listed_browse_layers(second_umm),'images_read':False,'source_arrays_read':False},
            coverage={'actual_polygon_valid':True,'subset_metadata_coverage_percent':second['aoi_coverage_percent_approx'],
                'actual_second_scene_valid_pixels_verified':False,'common_valid_pixel_footprint_verified':False},
            estimated_output=estimate(BBOX),limits=dry['setup']['limits'],
            unresolved_science=['incidence angles','second-scene valid pixels and QA','actual CRS/affine/grid alignment',
                                'tides and wetness','baseline mangrove mask','radiometric consistency and independent validation'])
        if settings.max_file_bytes>64*1024*1024 or settings.timeout>1200:
            raise RuntimeError('Configured limits exceed this preparation scope.')
        report['first_reference_registration']=register_first_reference(m,history['local_job_id'],source,
            identity['observed_output_basename'],baseline_sha)
        report.update(status='READY',readiness_scope='one second-scene extraction experiment pending explicit authorization; not scientific suitability')
    except HTTPException as exc:
        report.update(failure_category=exc.detail['code'])
    except TimeoutError:
        report.update(failure_category='metadata_preflight_timeout')
    except RuntimeError as exc:
        # Only hard-coded local check messages are eligible for evidence.
        known=('Second request does not match the frozen candidate, AOI and layer.',
               'Scene metadata contains a known incompatibility.',
               'The actual second metadata polygon does not contain the subset.',
               'First-scene identity/version has changed since the cached extraction.',
               'Nominal 10m resource estimate no longer applies.',
               'Existing unresolved work blocks preparation.',
               'Configured limits exceed this preparation scope.',
               'An existing worker is active.',
               'First-reference provenance does not match the completed test.',
               'Existing reference file differs; no data overwritten.',
               'Only the historical spatial rejection can be reconciled.',
               'Existing backup differs; no provenance overwritten.',
               'First reference would exceed storage budget.',
               'First reference exceeds the per-file storage budget.',
               'First COG is missing, replaced or changed.',
               'Reference copy verification failed.')
        report.update(failure_category='request_or_reference_preparation_failed',
                      failure_reason=str(exc) if str(exc) in known else 'A local preparation safety check failed.')
    except Exception:
        report.update(failure_category='request_or_reference_preparation_failed')
    finally:
        cmr.request=original
        transport.close()
        report.update(finished_at_utc=harmony.stamp(),processing_enabled_after=settings.enabled,jobs_after=len(m.jobs()),
            first_cache_sha256_after=digest(source),second_reference_gate_after=m.capabilities()['second_scene_unlocked'])
    if settings.enabled or report['jobs_after']!=before or report['first_cache_sha256_after']!=baseline_sha:
        report.update(status='BLOCKED',failure_category='local_safety_or_cache_integrity_failed')
    return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--child',action='store_true',help=argparse.SUPPRESS)
    args=p.parse_args()
    if args.child:
        print(json.dumps(asyncio.run(prepare()),allow_nan=False),flush=True)
        return
    from dotenv import load_dotenv
    load_dotenv()
    if os.getenv('HARMONY_PROCESSING_ENABLED','').lower()!='false' or os.getenv('HARMONY_AUTH_MODE')!='earthdata_password':
        raise RuntimeError('Keep the existing password mode and processing=false configuration.')
    env=os.environ.copy()
    env['EARTHDATA_TOKEN']=''  # Public CMR only; real file and token remain unchanged.
    try:
        child=subprocess.run([sys.executable,'-m','scripts.prepare_second_harmony_test','--child'],
            env=env,capture_output=True,text=True,timeout=60,check=False)
        report=json.loads(child.stdout) if child.returncode==0 else {'status':'BLOCKED','failure_category':'preparation_process_failed'}
    except subprocess.TimeoutExpired:
        report={'status':'BLOCKED','failure_category':'outer_preflight_deadline'}
    report['outer_deadline_seconds']=60
    payload=json.dumps(report,indent=2,allow_nan=False)+'\n'
    for key in ('EDL_USERNAME','EDL_PASSWORD','EARTHDATA_TOKEN'):
        if os.getenv(key) and os.getenv(key) in payload:
            raise RuntimeError('Redaction check failed; no evidence written.')
    Path('docs/harmony-second-test-readiness.json').write_text(payload,encoding='utf-8')
    print(json.dumps({k:report.get(k) for k in ('status','failure_category','jobs_before','jobs_after',
        'processing_enabled_after','first_reference_gate_before','second_reference_gate_after')},indent=2))


if __name__=='__main__':
    main()
