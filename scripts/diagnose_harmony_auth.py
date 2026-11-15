"""Bounded read-only diagnostic. No enablement, mutation, or processing calls."""
import argparse
import concurrent.futures
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import time
from urllib.request import getproxies,proxy_bypass

# Absolute-path subprocess execution must still resolve the workspace package.
if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

HOSTS = ['harmony.earthdata.nasa.gov','urs.earthdata.nasa.gov']


def network_child(kind, host):
    if host not in HOSTS:
        raise ValueError('Unsupported host')
    started = time.monotonic()
    result = {'host':host,'probe':kind,'status':'not_verified'}
    try:
        if kind == 'dns':
            addresses = socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
            result.update(status='succeeded',ipv4_count=len({a[4][0] for a in addresses if a[0]==socket.AF_INET}),
                          ipv6_count=len({a[4][0] for a in addresses if a[0]==socket.AF_INET6}))
        elif kind == 'tls':
            import certifi
            context = ssl.create_default_context(cafile=certifi.where())
            result['stage'] = 'tcp_connect'
            with socket.create_connection((host,443),timeout=4) as connection:
                result['tcp_connected'] = True
                result['stage'] = 'tls_handshake'
                with context.wrap_socket(connection,server_hostname=host) as tls:
                    result.update(status='succeeded',protocol=tls.version(),certificate_hostname_verified=True,stage='complete')
    except socket.gaierror:
        result['status'] = 'dns_error'
    except ssl.SSLCertVerificationError:
        result['status'] = 'certificate_verification_failed'
    except (TimeoutError,socket.timeout):
        result['status'] = 'timeout'
    except Exception:
        result['status'] = 'connection_error'
    result['elapsed_seconds'] = round(time.monotonic()-started,3)
    print(json.dumps(result),flush=True)


def bounded_child(args, timeout=15, interpreter=None):
    try:
        output = subprocess.run([str(interpreter or sys.executable),*args],capture_output=True,
                                text=True,timeout=timeout,check=False)
        if output.returncode != 0:
            return {'category':'diagnostic_child_error','details_redacted':True}
        return json.loads(output.stdout)
    except subprocess.TimeoutExpired:
        return {'category':'diagnostic_deadline','stage':'unknown_before_deadline','deadline_seconds':timeout}
    except Exception:
        return {'category':'diagnostic_child_error','details_redacted':True}


def main():
    from backend.app.harmony import Settings,Manager
    settings = Settings()
    if settings.enabled:
        raise RuntimeError('Refusing diagnostics while processing is enabled. No setting was changed.')
    before_jobs = len(Manager(settings).jobs())
    proxy = getproxies()
    report = {'started_at_utc':datetime.now(timezone.utc).isoformat(), 'token_present':bool(settings.token),
              'processing_enabled_before':settings.enabled,'processing_submitted':False,
              'request_policy':{'methods':['GET'],'attempts_per_probe':1,'http_connect_seconds':4,'http_read_seconds':6,
                                'http_child_deadline_seconds':15,'max_same_origin_redirects':2,'credential_cross_origin_forwarding':False},
              'proxy':{'discovered_schemes':sorted(k for k in proxy if k!='no'),
                       'harmony_bypassed':proxy_bypass(HOSTS[0]),
                       'environment_variables_present':{k:bool(os.environ.get(k)) for k in
                         ['HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','http_proxy','https_proxy','all_proxy','no_proxy',
                          'SSL_CERT_FILE','SSL_CERT_DIR','REQUESTS_CA_BUNDLE','CURL_CA_BUNDLE']}},
              'network':[],'https':[]}
    script = str(Path(__file__).resolve())
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        tasks = [(kind,host,pool.submit(bounded_child,[script,'--network-child',kind,host],10))
                 for host in HOSTS for kind in ['dns','tls']]
        for kind,host,future in tasks:
            data = future.result()
            data.setdefault('host',host)
            data.setdefault('probe',kind)
            report['network'].append(data)
    cases = [('capabilities','environment'),('jobs_public','environment'),('jobs_auth','environment'),('jobs_auth','direct')]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = [(name,mode,pool.submit(bounded_child,[script,'--http-child',name,mode])) for name,mode in cases]
        for name,mode,future in futures:
            item = future.result()
            item.update(probe=name,configuration=mode)
            report['https'].append(item)
    sdk_python = Path('artifacts/harmony-auth-env/Scripts/python.exe')
    if sdk_python.exists():
        report['harmony_py'] = bounded_child([str(Path('scripts/harmony_sdk_auth_probe.py').resolve())],15,sdk_python.resolve())
    else:
        report['harmony_py'] = {'category':'isolated_sdk_not_installed'}
    report['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    report['processing_enabled_after'] = Settings().enabled
    report['tracked_job_count_before'] = before_jobs
    report['tracked_job_count_after'] = len(Manager(settings).jobs())
    assert not report['processing_enabled_after'] and before_jobs==report['tracked_job_count_after']
    destination = Path('docs/harmony-auth-diagnostics.json')
    payload = json.dumps(report,indent=2,allow_nan=False)+'\n'
    if settings.token and settings.token in payload:
        raise RuntimeError('Evidence redaction check failed; no evidence was written.')
    destination.write_text(payload,encoding='utf-8')
    print(payload,flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--network-child',nargs=2)
    parser.add_argument('--http-child',nargs=2)
    args = parser.parse_args()
    if args.network_child:
        network_child(*args.network_child)
    elif args.http_child:
        from dotenv import load_dotenv
        from backend.app.auth_diagnostics import http_probe,JOBS,CAPABILITIES
        load_dotenv()
        if os.getenv('HARMONY_PROCESSING_ENABLED','').lower()=='true':
            print(json.dumps({'category':'blocked_processing_enabled'}))
        else:
            name,mode = args.http_child
            if name not in {'jobs_auth','jobs_public','capabilities'} or mode not in {'environment','direct'}:
                raise ValueError('Unsupported diagnostic')
            token = os.getenv('EARTHDATA_TOKEN','').strip() if name=='jobs_auth' else ''
            print(json.dumps(http_probe(CAPABILITIES if name=='capabilities' else JOBS,token,trust_env=mode=='environment')),flush=True)
    else:
        main()
