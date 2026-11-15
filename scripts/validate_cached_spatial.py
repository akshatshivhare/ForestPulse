"""Validate the cached first COG; optional read-only output filename refresh.

No worker, submit, cancel, second-scene or imagery-download path exists here.
Historical live-test evidence and production job state are not modified.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from urllib.parse import unquote,urlsplit
from backend.app.harmony import ROOT,Settings,Transport,stamp
from scripts.live_cog_audit import audit_cog

JOB='c9136c2d-e1ec-4669-b738-4a455f3b8f66'
DIR=Path('artifacts/harmony-spatial-audit')


async def identity_from_completed_job(settings):
    class ReadOnly(Transport):
        async def json(self,url,**kwargs):
            if url!=ROOT+'/jobs/'+JOB+'?linktype=https':
                raise RuntimeError('Only the existing job status is allowed.')
            return await super().json(url,**kwargs)
        async def download(self,*_args,**_kwargs):
            raise RuntimeError('No data download is allowed by this validator.')
    t=ReadOnly(settings)
    try:
        data=await t.json(ROOT+'/jobs/'+JOB+'?linktype=https',auth=True,retry=False)
        links=[x for x in data.get('links',[]) if x.get('rel')=='data']
        if data.get('status')!='successful' or len(links)!=1:
            raise RuntimeError('Expected one output from this completed job.')
        u=urlsplit(links[0]['href'])
        if u.scheme!='https' or u.netloc!='harmony.earthdata.nasa.gov':
            raise RuntimeError('Unexpected output-permalink origin.')
        filename=unquote(Path(u.path).name)
        identity={'observed_output_basename':filename,'job_id':JOB,'observed_at_utc':stamp(),
                  'source':'authenticated NASA job status; only filename retained, no URI/query'}
        (DIR/'output-identity.json').write_text(json.dumps(identity,indent=2)+'\n')
        return identity
    finally:
        await asyncio.to_thread(t.close)


def main(refresh):
    settings=Settings()
    if settings.enabled:
        raise RuntimeError('Processing must remain disabled.')
    history=json.loads(Path('docs/harmony-first-live-test.json').read_text())
    if history['remote_job_id']!=JOB or history['submission_attempts']!=1:
        raise RuntimeError('Unexpected existing-job provenance.')
    report={'checked_at_utc':stamp(),'job_id':JOB,'processing_enabled':False,'new_processing_jobs':0,
            'second_scene_processed':False,'historical_evidence_modified':False,'verdict':'UNRESOLVED'}
    try:
        identity=asyncio.run(identity_from_completed_job(settings)) if refresh else json.loads((DIR/'output-identity.json').read_text())
        if identity['job_id']!=JOB:
            raise RuntimeError('Unexpected output identity.')
        path=DIR/'first-real-cog.tif'
        recovery=json.loads((DIR/'recovery.json').read_text())
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if digest!=recovery['sha256']:
            raise RuntimeError('Recovered cache hash differs.')
        audit=audit_cog(path,history['plan'],identity['observed_output_basename'])
        report.update(verdict='VALID' if audit['validation_passed'] else 'INVALID',raster_validation=audit,
            recovery=recovery,output_identity=identity,sha256=digest,
            prior_extent_failure=history['raster_audit']['failure_category'])
    except Exception:
        report['failure_category']='cached_output_or_identity_unavailable'
    report['finished_at_utc']=stamp()
    Path('docs/harmony-spatial-validation.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    audit=report.get('raster_validation',{})
    print(json.dumps({'verdict':report['verdict'],'failure_category':report.get('failure_category',audit.get('failure_category')),
        'spatial_validation':audit.get('verified_metadata',{}).get('spatial_validation',audit.get('spatial_validation'))},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--refresh-output-identity',action='store_true',help='One read-only status lookup; never processes/downloads data.')
    main(p.parse_args().refresh_output_identity)
