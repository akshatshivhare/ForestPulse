"""Explicit Harmony-Py username/password mode, entirely separate from tokens."""
import json
import logging
import os
import time
from urllib.parse import urlsplit

ROOT='https://harmony.earthdata.nasa.gov'
URL=ROOT+'/jobs?limit=1'


def run_probe():
    for name in ['requests','urllib3','harmony','httpx','httpcore']:
        logging.getLogger(name).setLevel(logging.CRITICAL+1)
    result={'authentication_method':'username_password','credential_source':'EDL_USERNAME / EDL_PASSWORD',
            'token_used':False,'client':'harmony-py','endpoint_category':'jobs_list','method':'GET',
            'authentication_confirmed':False,'http_status':None,'requests_sent':0,'retry_count':0,
            'redirects_followed':False,'trust_environment':False,'stage':'configuration',
            'processing_submitted':False}
    started=time.monotonic()
    client=session=None
    try:
        from dotenv import load_dotenv
        load_dotenv()
        if os.getenv('HARMONY_PROCESSING_ENABLED','').lower()=='true':
            result['outcome']='blocked_processing_enabled'
            return result
        username=os.getenv('EDL_USERNAME','').strip()
        password=os.getenv('EDL_PASSWORD','')
        if not username or not password:
            result['outcome']='blocked_missing_username_or_password'
            return result
        from harmony import Client
        from importlib.metadata import version
        import requests
        from requests.adapters import HTTPAdapter
        result['client_version']=version('harmony-py')
        # Explicit tuple selects the official SDK password branch. No code in
        # this mode reads EARTHDATA_TOKEN or constructs a token-authenticated client.
        client=Client(auth=(username,password),token=None,should_validate_auth=False)
        if client.config.root_url!=ROOT:
            result['outcome']='blocked_unexpected_sdk_origin'
            return result
        session=client._session()
        session.trust_env=False  # No netrc, alternate credentials or proxy fallback.
        class SingleReadOnlyAdapter(HTTPAdapter):
            def send(self,request,**kwargs):
                u=urlsplit(request.url)
                if request.method!='GET' or u.scheme!='https' or u.netloc!='harmony.earthdata.nasa.gov' or u.path!='/jobs' or u.query!='limit=1':
                    raise RuntimeError('Non-diagnostic destination blocked.')
                if result['requests_sent'] or not request.headers.get('Authorization','').startswith('Basic '):
                    raise RuntimeError('Additional request or unexpected authentication method blocked.')
                result['requests_sent']+=1
                kwargs['timeout']=(4,6)
                return super().send(request,**kwargs)
        session.mount('https://',SingleReadOnlyAdapter(max_retries=0))
        session.mount('http://',SingleReadOnlyAdapter(max_retries=0))
        result['stage']='waiting_response_headers'
        try:
            with session.get(URL,timeout=(4,6),allow_redirects=False,stream=True) as response:
                result['http_status']=response.status_code
                result['stage']='response_headers_received'
                if response.status_code in (401,403):
                    result['outcome']='failed_unauthorized' if response.status_code==401 else 'failed_forbidden'
                elif 300<=response.status_code<400:
                    result['outcome']='unconfirmed_redirect_requires_authentication_flow'
                elif response.status_code>=500:
                    result['outcome']='failed_server_error'
                elif response.status_code==200:
                    result['stage']='reading_response_body'
                    body=bytearray()
                    for chunk in response.iter_content(16*1024):
                        body.extend(chunk)
                        if len(body)>64*1024:
                            result['outcome']='failed_response_body_limit'
                            return result
                    try:
                        data=json.loads(body)
                        accepted=isinstance(data,dict) and isinstance(data.get('jobs'),list)
                    except (ValueError,TypeError):
                        accepted=False
                    result['authentication_confirmed']=accepted
                    result['outcome']='succeeded' if accepted else 'unconfirmed_unexpected_response'
                    result['stage']='complete'
                else:
                    result['outcome']='failed_http_error'
        except requests.exceptions.ConnectTimeout:
            result['outcome']='timed_out_connect'
        except requests.exceptions.ReadTimeout:
            result['outcome']='timed_out_read'
        except requests.exceptions.SSLError:
            result['outcome']='failed_tls'
        except requests.exceptions.RequestException:
            result['outcome']='failed_transport'
    except Exception:
        # Never export exception representations, which could embed credentials.
        result['outcome']='blocked_local_test_error'
    finally:
        if session is not None:
            session.close()
        if client is not None:
            client.executor.shutdown(wait=False,cancel_futures=True)
        result['elapsed_seconds']=round(time.monotonic()-started,3)
    return result


if __name__=='__main__':
    print(json.dumps(run_probe()),flush=True)
