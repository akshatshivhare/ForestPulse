"""Run a single explicit password test in the isolated official SDK environment."""
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
        raise RuntimeError('Processing must remain disabled. No configuration was changed.')
    if not os.getenv('EDL_USERNAME','').strip() or not os.getenv('EDL_PASSWORD',''):
        raise RuntimeError('Configure EDL_USERNAME and EDL_PASSWORD privately before this test.')
    report={'started_at_utc':datetime.now(timezone.utc).isoformat(),
            'selected_authentication_method':'username_password','token_used':False,
            'processing_enabled_before':False,'processing_submitted':False,
            'credential_file_modified':False,'outer_deadline_seconds':15}
    python=Path('artifacts/harmony-auth-env/Scripts/python.exe').resolve()
    try:
        child=subprocess.run([str(python),'-m','scripts.harmony_password_auth_probe'],
                             capture_output=True,text=True,timeout=15,check=False)
        report['result']=json.loads(child.stdout) if child.returncode==0 else {'outcome':'blocked_sdk_process_error'}
    except subprocess.TimeoutExpired:
        report['result']={'outcome':'timed_out_outer_deadline','authentication_confirmed':False}
    except Exception:
        report['result']={'outcome':'blocked_sdk_process_error'}
    report['finished_at_utc']=datetime.now(timezone.utc).isoformat()
    report['processing_enabled_after']=os.getenv('HARMONY_PROCESSING_ENABLED','').lower()=='true'
    assert not report['processing_enabled_after']
    payload=json.dumps(report,indent=2,allow_nan=False)+'\n'
    # Compare privately; never put credentials or request headers in evidence.
    for key in ['EDL_USERNAME','EDL_PASSWORD']:
        if os.getenv(key) in payload:
            raise RuntimeError('Credential redaction failed; report not written.')
    Path('docs/harmony-password-auth-test.json').write_text(payload,encoding='utf-8')
    print(payload,flush=True)


if __name__=='__main__':
    main()
