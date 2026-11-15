"""Retrieve ONLY the output of the already submitted, successful first job.

Processing stays disabled. This tool has no submission, retry-job, cancel or
worker path. Signed links exist only in memory and never enter evidence.
"""
import asyncio
import json
from pathlib import Path
from urllib.parse import unquote,urlsplit
from uuid import UUID
from fastapi import HTTPException
from backend.app.harmony import ROOT,Settings,Transport,Manager,file_lock,stamp
from scripts.live_cog_audit import audit_cog

DEST=Path('docs/harmony-first-live-test.json')


async def main():
    evidence=json.loads(DEST.read_text())
    if evidence.get('submission_attempts')!=1:
        raise RuntimeError('Require exactly the existing single submission.')
    remote_id=str(UUID(evidence['remote_job_id']))
    local_id=str(UUID(evidence['local_job_id']))
    settings=Settings()
    if settings.enabled or settings.auth_mode!='earthdata_password':
        raise RuntimeError('Processing must remain disabled in password mode.')

    class ExistingJobOnly(Transport):
        async def json(self,url,**kwargs):
            if url!=ROOT+'/jobs/'+remote_id+'?linktype=https':
                raise RuntimeError('Only this existing job status can be requested.')
            return await super().json(url,**kwargs)

    t=ExistingJobOnly(settings)
    m=Manager(settings,t)
    record={'started_at_utc':stamp(),'processing_enabled':False,'processing_submissions':0}
    evidence.setdefault('output_retrieval_attempts',[]).append(record)

    def save():
        DEST.write_text(json.dumps(evidence,indent=2,allow_nan=False)+'\n',encoding='utf-8')

    part=m.path(local_id,'.part')
    try:
        with file_lock(settings.cache,'worker') as owned:
            if not owned:
                raise RuntimeError('Existing worker is active.')
            job=m.get(local_id)
            if job.get('remote_job_id')!=remote_id or job['plan']['scene']['id']!='G4405780437-ASF':
                raise RuntimeError('Existing job identity differs.')
            from scripts.validate_harmony_live import check_authorized_scope
            check_authorized_scope(job['plan'])
            if job['status']=='verified':
                raise RuntimeError('Output is already verified; no additional download needed.')
            data=await t.json(ROOT+'/jobs/'+remote_id+'?linktype=https',auth=True,retry=False)
            if data.get('status')!='successful':
                raise RuntimeError('Only successful existing jobs can be downloaded.')
            links=[x for x in data.get('links',[]) if x.get('rel')=='data']
            if len(links)!=1 or Path(unquote(urlsplit(links[0].get('href','')).path)).suffix.lower() not in {'.tif','.tiff'}:
                raise RuntimeError('Expected one COG output; source HDF5 is forbidden.')
            budget=min(64*1024*1024,settings.max_cache_bytes-m.usage()-1024*1024)
            if budget<=0:
                raise RuntimeError('Cache budget exhausted.')
            save()
            async with asyncio.timeout(60):
                await t.download(links[0]['href'],part,budget)
            record['download_completed_at_utc']=stamp()
            audit=audit_cog(part,job['plan'],links[0]['href'])
            evidence.update(raster_audit=audit,pixel_statistics=audit.get('statistics'))
            if audit['validation_passed']:
                part.replace(m.path(local_id,'.tif'))
                job.update(status='verified',raster=audit['verified_metadata'],error=None,remote_terminal=True)
                evidence.update(outcome='VALID',status='verified')
            else:
                job.update(status='failed',raster=None,error={'code':audit.get('failure_category'),
                           'message':'Downloaded COG failed technical validation; no replacement job was submitted.'})
                evidence.update(outcome='INVALID',status='failed')
            m.save(job)
            evidence['job']=m.get(local_id)
            record['outcome']=evidence['outcome']
    except HTTPException as exc:
        record.update(outcome='BLOCKED',category=exc.detail['code'],backend_http_status=exc.status_code)
    except Exception:
        record.update(outcome='BLOCKED',category='existing_output_retrieval_check_failed')
    finally:
        if t._password_session is not None:
            record['last_harmony_http_evidence']=t._password_session.last_operation_evidence
        await asyncio.to_thread(t.close)
        part.unlink(missing_ok=True)
        settings.enabled=False
        record['finished_at_utc']=stamp()
        evidence.update(process_local_enablement_restored_false=True,finished_at_utc=stamp())
        save()
        print(json.dumps(record,indent=2))


if __name__=='__main__':
    asyncio.run(main())
