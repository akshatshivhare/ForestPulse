"""One read-only check through the integrated backend, never the worker.

The child process has an outer deadline; no retries, processing or downloads.
Only a fixed summary is written, never the returned jobs payload.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys


async def check():
    from fastapi import HTTPException
    from backend.app.harmony import ROOT, Settings, Transport
    from backend.app.earthdata_session import FLOW_SECONDS, MAX_REDIRECTS
    settings = Settings(auth_mode='earthdata_password')
    if settings.enabled or not settings.authentication_configured:
        return {'status': 'BLOCKED', 'category': 'processing_enabled_or_missing_password_credentials'}
    transport = Transport(settings)
    result = {'authentication_method': settings.auth_mode, 'token_used': False,
              'logical_authentication_attempts': 1, 'processing_enabled': settings.enabled,
              'processing_submitted': False, 'download_attempted': False,
              'redirect_limit': MAX_REDIRECTS, 'per_flow_budget_seconds': FLOW_SECONDS}
    try:
        data = await transport.json(ROOT + '/jobs?limit=1', auth=True, retry=False)
        result['status'] = 'VERIFIED' if isinstance(data.get('jobs'), list) else 'STILL UNCONFIRMED'
        result['authenticated_jobs_list_received'] = result['status'] == 'VERIFIED'
    except HTTPException as exc:
        result.update(status='REJECTED' if exc.status_code == 401 else 'STILL UNCONFIRMED',
                      category=exc.detail['code'], backend_http_status=exc.status_code)
    except Exception:
        result.update(status='STILL UNCONFIRMED', category='local_verification_error')
    finally:
        if transport._password_session is not None:
            result['session_evidence'] = transport._password_session.last_evidence
        await asyncio.to_thread(transport.close)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--auth-mode', required=True, choices=['earthdata_password'])
    parser.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child:
        print(json.dumps(asyncio.run(check())), flush=True)
        return
    from dotenv import load_dotenv
    load_dotenv()
    if os.getenv('HARMONY_PROCESSING_ENABLED', '').lower() == 'true':
        raise RuntimeError('Processing must remain disabled. No settings changed.')
    if not os.getenv('EDL_USERNAME', '').strip() or not os.getenv('EDL_PASSWORD', ''):
        raise RuntimeError('Configure EDL_USERNAME and EDL_PASSWORD only in the ignored server .env.')
    report = {'started_at_utc': datetime.now(timezone.utc).isoformat(), 'outer_deadline_seconds': 30}
    try:
        child = subprocess.run([sys.executable, '-m', 'scripts.verify_backend_password_auth',
            '--auth-mode', args.auth_mode, '--child'], capture_output=True, text=True, timeout=30, check=False)
        report['result'] = json.loads(child.stdout) if child.returncode == 0 else {'status':'STILL UNCONFIRMED', 'category':'child_process_error'}
    except subprocess.TimeoutExpired:
        report['result'] = {'status':'STILL UNCONFIRMED', 'category':'outer_deadline_exceeded'}
    report['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    payload = json.dumps(report, indent=2) + '\n'
    for key in ('EDL_USERNAME', 'EDL_PASSWORD'):
        if os.getenv(key) in payload:
            raise RuntimeError('Redaction check failed; no evidence written.')
    Path('docs/harmony-backend-password-auth.json').write_text(payload, encoding='utf-8')
    print(payload, flush=True)


if __name__ == '__main__':
    main()
