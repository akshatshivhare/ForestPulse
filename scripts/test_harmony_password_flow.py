"""Exactly one trusted-redirect authentication flow in an isolated process."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--auth-method',required=True,choices=['username-password'])
    parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv()
    if os.getenv('HARMONY_PROCESSING_ENABLED','').lower()=='true':
        raise RuntimeError('Processing must stay disabled; no settings changed.')
    if not os.getenv('EDL_USERNAME','').strip() or not os.getenv('EDL_PASSWORD',''):
        raise RuntimeError('Missing locally configured EDL username/password.')
    report={'started_at_utc':datetime.now(timezone.utc).isoformat(),
            'authentication_method':'username_password','token_used':False,
            'processing_enabled_before':False,'processing_submitted':False,
            'credential_or_cookie_file_written':False,'outer_deadline_seconds':25}
    python=Path('artifacts/harmony-auth-env/Scripts/python.exe').resolve()
    try:
        child=subprocess.run([str(python),'-m','scripts.harmony_password_redirect_flow'],
                             capture_output=True,text=True,timeout=25,check=False)
        report['result']=json.loads(child.stdout) if child.returncode==0 else {
            'status':'STILL UNCONFIRMED','failure_category':'sdk_process_error'}
    except subprocess.TimeoutExpired:
        report['result']={'status':'STILL UNCONFIRMED','failure_category':'outer_deadline_exceeded'}
    except Exception:
        report['result']={'status':'STILL UNCONFIRMED','failure_category':'sdk_process_error'}
    report['finished_at_utc']=datetime.now(timezone.utc).isoformat()
    report['processing_enabled_after']=os.getenv('HARMONY_PROCESSING_ENABLED','').lower()=='true'
    assert not report['processing_enabled_after']
    payload=json.dumps(report,indent=2,allow_nan=False)+'\n'
    for key in ['EDL_USERNAME','EDL_PASSWORD']:
        if os.getenv(key) in payload:
            raise RuntimeError('Credential redaction failed; evidence not written.')
    Path('docs/harmony-password-redirect-test.json').write_text(payload,encoding='utf-8')
    print(payload,flush=True)


if __name__=='__main__':
    main()
