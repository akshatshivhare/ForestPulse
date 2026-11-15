"""Read-only EDL check or ONE user-attested alternative-network Harmony GET.

Never enables processing or edits credentials. No token/profile/headers logged.
"""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import sys


def child(mode):
    from dotenv import load_dotenv
    load_dotenv()
    if os.getenv('HARMONY_PROCESSING_ENABLED','').lower()=='true':
        return {'category':'blocked_processing_enabled'}
    token=os.getenv('EARTHDATA_TOKEN','').strip()
    if mode=='edl':
        from backend.app.earthdata_readonly import verify_profile_access
        return verify_profile_access(token,fallback_username=os.getenv('EARTHDATA_USERNAME'))
    from backend.app.auth_diagnostics import JOBS,http_probe
    if not token:
        return {'category':'authentication_missing'}
    return http_probe(JOBS,token,trust_env=False,max_redirects=0)


def main(args):
    from backend.app.harmony import Settings,Manager
    from scripts.diagnose_harmony_auth import bounded_child
    settings=Settings()
    if settings.enabled:
        raise RuntimeError('Processing must remain disabled. No setting was changed.')
    if args.mode=='alternative' and (not args.confirm_network_switch or not args.network_type):
        raise RuntimeError('An alternative trusted network must be explicitly confirmed before this single GET.')
    before=len(Manager(settings).jobs())
    report={'started_at_utc':datetime.now(timezone.utc).isoformat(),
            'network_type':args.network_type if args.mode=='alternative' else 'original_network_transport_unspecified',
            'network_confirmation':'user_attested_switch' if args.mode=='alternative' else 'user_confirmed_original_network',
            'alternative_network_tested':args.mode=='alternative',
            'processing_enabled_before':settings.enabled,'processing_submitted':False}
    report['result']=bounded_child(['-m','scripts.harmony_auth_followup','--child',args.mode],15)
    report['finished_at_utc']=datetime.now(timezone.utc).isoformat()
    report['processing_enabled_after']=Settings().enabled
    report['tracked_jobs_before']=before
    report['tracked_jobs_after']=len(Manager(settings).jobs())
    assert not report['processing_enabled_after'] and before==report['tracked_jobs_after']
    filename='docs/earthdata-auth-independent.json' if args.mode=='edl' else 'docs/harmony-alternative-network.json'
    payload=json.dumps(report,indent=2,allow_nan=False)+'\n'
    if settings.token and settings.token in payload:
        raise RuntimeError('Credential redaction failed; report not written.')
    Path(filename).write_text(payload,encoding='utf-8')
    print(payload,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',choices=['edl','alternative'],default='edl')
    parser.add_argument('--confirm-network-switch',action='store_true')
    parser.add_argument('--network-type',choices=['trusted_mobile_hotspot','other_trusted_network'])
    parser.add_argument('--child',choices=['edl','alternative'])
    args=parser.parse_args()
    if args.child:
        print(json.dumps(child(args.child)),flush=True)
    else:
        main(args)
