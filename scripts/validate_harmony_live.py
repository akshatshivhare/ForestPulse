"""One first-scene smoke test using the existing backend; no second-scene jobs.

Live enablement is process-local and occurs only after authentication/preflight.
The persisted evidence excludes bearer credentials, user identity and asset URLs.
"""
import argparse
import asyncio
import json
import math
import os
import concurrent.futures
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import UUID

import httpx
from fastapi import HTTPException

from backend.app.config import CMR_BASE, TOKEN
from backend.app.harmony import CANDIDATES, Extraction, Manager, ROOT, Settings, Transport, file_lock, stamp
from scripts.live_cog_audit import audit_cog

DESTINATION = Path('docs/harmony-live-validation.json')


def diagnose_access():
    """Read-only reachability comparison. Never returns credentials or profiles."""
    settings = Settings()
    def probe(auth):
        try:
            headers = {'Authorization': 'Bearer ' + settings.token} if auth else {}
            response = httpx.get(ROOT + '/jobs?limit=1', headers=headers, timeout=15, follow_redirects=False)
            return {'authenticated_request': auth, 'http_status': response.status_code,
                    'jobs_list_received': response.status_code == 200 and
                    'json' in response.headers.get('content-type', '') and isinstance(response.json().get('jobs'), list)}
        except Exception as exc:
            return {'authenticated_request':auth, 'error_type':type(exc).__name__}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(probe, [False, True]))
    report = json.loads(DESTINATION.read_text(encoding='utf-8')) if DESTINATION.exists() else {}
    report['access_probes'] = results
    report['access_probes_at_utc'] = stamp()
    DESTINATION.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps(results, indent=2), flush=True)


def check_authorized_scope(plan):
    u=urlsplit(plan['request_url'])
    expected={'granuleId':['G4405780437-ASF'],'subset':['lon(88.75:88.78)','lat(21.85:21.88)'],
              'format':['image/tiff'],'forceAsync':['true'],'maxResults':['1'],'ignoreErrors':['false']}
    if (plan['scene']['id']!='G4405780437-ASF' or plan['bbox']!=[88.75,21.85,88.78,21.88]
        or plan['variable']!='/science/LSAR/GCOV/grids/frequencyA/HHHH'
        or u.scheme!='https' or u.netloc!='harmony.earthdata.nasa.gov'
        or u.path!='/C3622241360-ASF/ogc-api-coverages/1.0.0/collections/V4137651715-ASF/coverage/rangeset'
        or parse_qs(u.query)!=expected):
        raise RuntimeError('Request differs from the explicitly authorized scope.')


async def main(submit_one=False,authorized_first_test=False):
    if authorized_first_test and DESTINATION.exists():
        previous=json.loads(DESTINATION.read_text(encoding='utf-8'))
        if previous.get('submission_attempts',0):
            raise RuntimeError('This one-test authorization has already been consumed; no new request sent.')
    settings = Settings()
    settings.enabled = False  # This runner never trusts a pre-existing opt-in blindly.
    report = {'started_at_utc': stamp(), 'authentication_verified': False, 'status': 'checking_authentication',
              'submission_attempts': 0, 'remote_job_id': None, 'events': [], 'plan': None, 'job': None,
              'pixel_statistics': None, 'raster_audit':None, 'second_scene_submitted': False, 'analysis_ready': False,
              'auth_mode':settings.auth_mode, 'token_used':settings.auth_mode!='earthdata_password',
              'output_download_attempts':0, 'outcome':'BLOCKED'}

    def save():
        report['updated_at_utc'] = stamp()
        DESTINATION.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')

    class ObservedTransport(Transport):
        async def json(self, url, **kwargs):
            path = urlsplit(url).path
            if '/coverage/rangeset' in path:
                if report['submission_attempts']:
                    raise RuntimeError('A second submission attempt is forbidden in this runner.')
                check_authorized_scope(report['plan'])
                if url!=report['plan']['request_url'] or kwargs.get('retry') is not False:
                    raise RuntimeError('Unapproved or retryable transformation request blocked.')
                report['submission_attempts'] += 1
                report['submission_attempted_at_utc'] = stamp()
                save()
            try:
                data = await super().json(url, **kwargs)
            except HTTPException as exc:
                if '/coverage/rangeset' in path:
                    report['submission_error']={'backend_http_status':exc.status_code,'code':exc.detail['code']}
                raise
            finally:
                if '/coverage/rangeset' in path and self._password_session is not None:
                    report['submission_http_evidence']=self._password_session.last_operation_evidence
                    save()
            if data.get('jobID'):
                remote_id=str(UUID(data['jobID']))
                if report['remote_job_id'] is not None and report['remote_job_id']!=remote_id:
                    raise RuntimeError('NASA response does not match the tracked job.')
                if report['remote_job_id'] is None:
                    report['remote_job_id']=remote_id
                    report['job_id_received_at_utc'] = stamp()
                    print(json.dumps({'remote_job_id':remote_id,'received_at_utc':report['job_id_received_at_utc']}),flush=True)
            if '/jobs/' in path:
                allowed={'accepted','queued','running','paused','previewing','successful','failed','complete_with_errors','canceled'}
                status=data.get('status') if data.get('status') in allowed else 'unrecognized'
                progress=float(data.get('progress',0))
                event = {'observed_at_utc': stamp(), 'status':status, 'progress':progress if math.isfinite(progress) else None}
                for key in ['createdAt', 'updatedAt', 'dataExpiration']:
                    if isinstance(data.get(key),str):
                        try:
                            event[key]=datetime.fromisoformat(data[key].replace('Z','+00:00')).isoformat()
                        except ValueError:
                            pass
                report['events'].append(event)
                print(json.dumps(event), flush=True)
            save()
            return data

        async def download(self,url,path,budget):
            if Path(unquote(urlsplit(url).path)).suffix.lower() not in {'.tif','.tiff'}:
                raise HTTPException(502,detail={'code':'unsupported_output_type','message':'Expected a COG filename; no source HDF5 or other file was downloaded.'})
            if budget>64*1024*1024:
                raise RuntimeError('Authorized file budget exceeded.')
            report['output_download_attempts']+=1
            save()
            await super().download(url,path,budget)
            report['output_downloaded_at_utc']=stamp()
            report['raster_audit']=audit_cog(path,report['plan'],url)
            report['pixel_statistics']=report['raster_audit'].get('statistics')
            save()  # Preserve invalid/zero-pixel evidence before backend cleanup.

    transport = ObservedTransport(settings)
    manager = Manager(settings, transport)
    save()
    try:
        if CMR_BASE != 'https://cmr.earthdata.nasa.gov/search':
            raise RuntimeError('Unexpected CMR origin; credentials will not be sent.')
        if authorized_first_test and settings.auth_mode!='earthdata_password':
            raise RuntimeError('This authorization requires explicit password mode.')
        if authorized_first_test and TOKEN:
            raise RuntimeError('Exclude the unused bearer value from this test process; keep the server .env unchanged.')
        if not settings.authentication_configured:
            report['status'] = 'blocked_authentication_missing'
            return
        print('Checking authenticated NASA jobs access; no submission.', flush=True)
        authentication = await transport.json(ROOT + '/jobs?limit=1', auth=True,retry=False)
        if not isinstance(authentication.get('jobs'), list):
            raise RuntimeError('Authenticated NASA response did not contain a jobs list.')
        report['authentication_verified'] = True
        report['authentication_verified_at_utc'] = stamp()
        print('Authentication verified. Checking first-candidate metadata and subset.', flush=True)
        dry = await manager.submit(Extraction(granule_id=CANDIDATES[0]))
        report['plan'] = dry['plan']
        report['limits'] = dry['setup']['limits']
        check_authorized_scope(dry['plan'])
        assert dry['plan']['scene']['id'] == CANDIDATES[0]
        assert settings.max_file_bytes <= 64*1024*1024 and settings.max_cache_bytes <= 256*1024*1024
        assert settings.timeout <= 1200
        report['status'] = 'preflight_verified'
        save()
        if not submit_one:
            return
        # Hold the worker lock across queueing and execution so an API worker
        # cannot take the CLI's queued job. The existing processing core is reused.
        with file_lock(settings.cache,'worker') as owned:
            if not owned or manager.jobs():
                report['status']='blocked_existing_work_or_worker'
                return
            os.environ['HARMONY_PROCESSING_ENABLED'] = 'true'
            settings.enabled = True
            report['process_local_enablement_at_utc'] = stamp()
            print('Safety checks passed. Sending one first-candidate extraction; no submission retry.', flush=True)
            job = await manager.submit(Extraction(granule_id=CANDIDATES[0],dry_run=False))
            report['local_job_id']=job['id']
            save()
            await manager._run(job)  # Worker lock is already held above.
            job=manager.get(job['id'])
            report.update(job=job,remote_job_id=job.get('remote_job_id') or report['remote_job_id'],status=job['status'])
            if job['status']=='verified' and report['raster_audit'] and report['raster_audit']['validation_passed']:
                report['outcome']='VALID'
            elif report['raster_audit'] and not report['raster_audit']['validation_passed']:
                report['outcome']='INVALID'
    except HTTPException as exc:
        report['status'] = 'blocked'
        report['error'] = {'backend_http_status':exc.status_code, 'detail':exc.detail}
    except Exception:
        # Exception representations may contain credentials or signed URLs.
        report['status'] = 'blocked_local_validation'
        report['error'] = {'message':'Local validation failed; no unredacted exception or remote payload was exported.'}
    finally:
        settings.enabled = False
        os.environ['HARMONY_PROCESSING_ENABLED'] = 'false'
        await asyncio.to_thread(transport.close)
        report['process_local_enablement_restored_false'] = True
        report['finished_at_utc'] = stamp()
        save()
        print(json.dumps({'evidence':str(DESTINATION),'status':report['status'],
                          'authentication_verified':report['authentication_verified'],
                          'submission_attempts':report['submission_attempts'],'remote_job_id':report['remote_job_id'],
                          'outcome':report['outcome']},indent=2),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--submit-one', action='store_true', help='After checks, permit exactly one first-scene transformation attempt.')
    parser.add_argument('--diagnose-access', action='store_true', help='Compare public/authenticated jobs access without processing.')
    parser.add_argument('--authorized-first-test',action='store_true',help='Execute the explicitly authorized one-shot password-mode test; never rerun a consumed authorization.')
    args = parser.parse_args()
    if args.authorized_first_test:
        if os.getenv('HARMONY_PROCESSING_ENABLED','').lower()!='false':
            raise RuntimeError('Server processing must remain false outside this scoped test.')
        DESTINATION=Path('docs/harmony-first-live-test.json')
    if args.diagnose_access:
        diagnose_access()
    else:
        asyncio.run(main(args.submit_one or args.authorized_first_test,args.authorized_first_test))
