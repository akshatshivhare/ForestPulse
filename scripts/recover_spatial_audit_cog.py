"""Recover only the existing completed job's COG; no worker/submission path.

Keep it in an isolated ignored audit directory, without changing historical job
state or unlocking scene two. Never write the signed output link to disk.
"""
import asyncio
import hashlib
import json
from pathlib import Path
from urllib.parse import unquote,urlsplit
from backend.app.harmony import ROOT,Settings,Transport,stamp

JOB='c9136c2d-e1ec-4669-b738-4a455f3b8f66'
DIRECTORY=Path('artifacts/harmony-spatial-audit')


async def main():
    settings=Settings()
    if settings.enabled or settings.auth_mode!='earthdata_password':
        raise RuntimeError('Require disabled processing and password mode.')
    history=json.loads(Path('docs/harmony-first-live-test.json').read_text())
    if history['remote_job_id']!=JOB or history['submission_attempts']!=1:
        raise RuntimeError('Unexpected existing-job provenance.')

    class ReadOnly(Transport):
        async def json(self,url,**kwargs):
            if url!=ROOT+'/jobs/'+JOB+'?linktype=https':
                raise RuntimeError('Only the existing completed job can be read.')
            return await super().json(url,**kwargs)

    target=DIRECTORY/'first-real-cog.tif'
    if target.exists():
        print(json.dumps({'result':'already_cached','bytes':target.stat().st_size}))
        return
    DIRECTORY.mkdir(parents=True,exist_ok=True)
    part=DIRECTORY/'first-real-cog.part'
    t=ReadOnly(settings)
    report={'job_id':JOB,'started_at_utc':stamp(),'processing_enabled':False,'new_jobs_submitted':0,
            'prior_local_cog_absent':True}
    try:
        data=await t.json(ROOT+'/jobs/'+JOB+'?linktype=https',auth=True,retry=False)
        links=[x for x in data.get('links',[]) if x.get('rel')=='data']
        if data.get('status')!='successful' or len(links)!=1:
            raise RuntimeError('Require one output from the existing successful job.')
        url=links[0].get('href','')
        if Path(unquote(urlsplit(url).path)).suffix.lower() not in {'.tif','.tiff'}:
            raise RuntimeError('Only COG output is permitted, never HDF5.')
        async with asyncio.timeout(60):
            await t.download(url,part,64*1024*1024)
        if part.stat().st_size!=history['raster_audit']['bytes']:
            raise RuntimeError('Output size differs from the previously measured COG.')
        part.replace(target)
        # Store only non-sensitive identity booleans, not tags or signed URLs.
        report.update(result='recovered_same_job_output',bytes=target.stat().st_size,
            sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
            output_name_contains_source=history['plan']['scene']['name'] in unquote(urlsplit(url).path),
            output_name_contains_variable='frequencyA' in unquote(urlsplit(url).path) and 'HHHH' in unquote(urlsplit(url).path))
    except Exception:
        report.update(result='UNRESOLVED',failure_category='existing_cog_recovery_failed')
    finally:
        await asyncio.to_thread(t.close)
        part.unlink(missing_ok=True)
        report['finished_at_utc']=stamp()
        (DIRECTORY/'recovery.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))


if __name__=='__main__':
    asyncio.run(main())
