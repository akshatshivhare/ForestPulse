"""Public preflight, then at most ONE gated first-scene real processing test.

No secrets or signed output URLs are exported. Never processes scene two.
"""
import asyncio
import json
from pathlib import Path

from fastapi import HTTPException
from backend.app import cmr
from backend.app.harmony import CANDIDATES, Extraction, Manager, ROOT, stamp
from backend.app.science import compare


async def main():
    manager = Manager()
    try:
        await verify(manager)
    finally:
        await asyncio.to_thread(manager.transport.close)


async def verify(manager):
    report = {'checked_at': stamp(), 'processing_submitted': False, 'submission_attempted': False, 'verification_mode': 'public metadata / dry-run',
              'authentication_configured': manager.settings.authentication_configured, 'authentication_method': manager.settings.auth_mode,
              'real_processing_enabled': manager.settings.enabled,
              'documentation': ['https://nisar-docs.asf.alaska.edu/harmony/', 'https://harmony.earthdata.nasa.gov/docs'],
              'candidates': [], 'live_result': None, 'analysis_ready': False}
    for gid in CANDIDATES:
        result = await manager.submit(Extraction(granule_id=gid))
        report['candidates'].append(result['plan'])
    first, second = [x['scene'] for x in report['candidates']]
    report['pilot_screening'] = compare(first, second, [88.4,21.55,89.1,22.25])
    cid = report['candidates'][0]['collection']['id']
    collection = await cmr.request('collections.umm_json', {'concept_id': cid})
    report['collection_metadata'] = collection
    report['collection_capabilities'] = await manager.transport.json(ROOT + '/capabilities?collectionId=' + cid)
    if not manager.settings.authentication_configured or not manager.settings.enabled:
        report['live_status'] = 'BLOCKED: configure the selected server authentication mode and explicitly enable HARMONY_PROCESSING_ENABLED=true; no real submission attempted.'
    else:
        # Exactly one first-scene request. The second scene is never submitted here.
        try:
            job = await manager.submit(Extraction(dry_run=False))
            if job['status'] == 'queued' or job.get('remote_job_id') and job['status'] in {'running','paused','downloading','validating','cancel_pending'}:
                await manager.run(job)
            job = manager.get(job['id'])
            report['submission_attempted'] = job.get('submission_attempted', False)
            report['processing_submitted'] = True if job.get('remote_job_id') else (None if job['status'] == 'submission_unknown' else False)
            report['live_result'] = job
            report['live_status'] = 'LIVE VERIFIED: first candidate COG only' if job['status'] == 'verified' else 'BLOCKED: ' + job['status']
        except HTTPException as exc:
            report['live_status'] = 'BLOCKED: ' + exc.detail['code']
    destination = Path('docs/harmony-verification.json')
    destination.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'evidence': str(destination), 'live_status': report['live_status'],
                      'processing_submitted': report['processing_submitted'],
                      'candidate_ids': CANDIDATES, 'analysis_ready': False}, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
