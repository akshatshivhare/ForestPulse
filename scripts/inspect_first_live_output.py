"""Read-only output-origin inspection for the ONE already submitted job."""
import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID
from backend.app.harmony import ROOT, Settings, Transport


async def main():
    evidence=json.loads(Path('docs/harmony-first-live-test.json').read_text())
    job_id=str(UUID(evidence['remote_job_id']))
    settings=Settings()
    if settings.enabled or settings.auth_mode!='earthdata_password':
        raise RuntimeError('Require disabled processing and password mode.')
    t=Transport(settings)
    try:
        data=await t.json(ROOT+'/jobs/'+job_id+'?linktype=https',auth=True,retry=False)
        links=[x for x in data.get('links',[]) if x.get('rel')=='data']
        result={'job_id':job_id,'remote_status':data.get('status'),'data_asset_count':len(links),'assets':[]}
        for link in links:
            u=urlsplit(link.get('href',''))
            result['assets'].append({'scheme':u.scheme,'host':u.hostname,'port':u.port,
                'has_userinfo':bool(u.username or u.password),'has_query':bool(u.query),
                'filename_suffix':Path(u.path).suffix,'type':link.get('type'),
                'existing_allowlist_accepts':Transport.asset_allowed(link.get('href',''))})
        print(json.dumps(result,indent=2))
    except Exception:
        print(json.dumps({'status':'BLOCKED','category':'read_only_output_inspection_failed'}))
    finally:
        await asyncio.to_thread(t.close)


if __name__=='__main__':
    asyncio.run(main())
