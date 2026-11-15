"""One bounded official SDK password login flow. No token or processing path."""
import json
import logging
import os
import time
from urllib.parse import parse_qs,urljoin,urlsplit

HARMONY='https://harmony.earthdata.nasa.gov'
EDL='https://urs.earthdata.nasa.gov'
JOBS=HARMONY+'/jobs?limit=1'
CALLBACK=HARMONY+'/oauth2/redirect'
MAX_REDIRECTS=4
TOTAL_SECONDS=20


class FlowBlocked(Exception):
    def __init__(self,category):
        self.category=category


def route(url):
    """Return public fixed labels only; never echo an untrusted URL."""
    try:
        u=urlsplit(url)
        if u.scheme!='https' or u.fragment or u.username or u.password:
            return None
        if u.netloc=='harmony.earthdata.nasa.gov':
            if u.path=='/jobs' and parse_qs(u.query) in ({},{'limit':['1']}):
                return ('harmony_jobs',HARMONY,'/jobs')
            if u.path=='/oauth2/redirect':
                return ('harmony_oauth_callback',HARMONY,'/oauth2/redirect')
        if u.netloc=='urs.earthdata.nasa.gov':
            if u.path=='/oauth/authorize':
                return ('earthdata_authorize',EDL,'/oauth/authorize')
            if u.path=='/login':
                return ('earthdata_login_page',EDL,'/login')
    except (ValueError,TypeError):
        pass
    return None


def verify_authorize_url(url):
    params=parse_qs(urlsplit(url).query)
    return (params.get('redirect_uri')==[CALLBACK] and params.get('response_type')==['code']
            and len(params.get('client_id',[]))==1 and bool(params['client_id'][0]))


def run_flow():
    for name in ['requests','urllib3','harmony','httpx','httpcore']:
        logging.getLogger(name).setLevel(logging.CRITICAL+1)
    started=time.monotonic()
    result={'authentication_method':'username_password','token_used':False,'authentication_attempts':1,
            'status':'STILL UNCONFIRMED','failure_category':None,'requests_sent':0,'responses':[],
            'redirect_limit':MAX_REDIRECTS,'redirects_followed':0,'automatic_retries':0,
            'shared_deadline_seconds':TOTAL_SECONDS,'processing_submitted':False,
            'cookies_in_memory_only':True,'cookie_file_written':False,'cookie_jar_populated':False,
            'stage':'configuration','http_status':None}
    client=session=None
    callback_pinned=False
    expected_state=None
    seen=set()
    try:
        from dotenv import load_dotenv
        load_dotenv()
        if os.getenv('HARMONY_PROCESSING_ENABLED','').lower()=='true':
            raise FlowBlocked('processing_enabled')
        username=os.getenv('EDL_USERNAME','').strip()
        password=os.getenv('EDL_PASSWORD','')
        if not username or not password:
            raise FlowBlocked('missing_username_or_password')
        from harmony import Client
        from importlib.metadata import version
        import requests
        from requests.adapters import HTTPAdapter
        result['client_version']=version('harmony-py')
        client=Client(auth=(username,password),token=None,should_validate_auth=False)
        if client.config.root_url!=HARMONY:
            raise FlowBlocked('unexpected_sdk_origin')
        session=client._session()
        session.trust_env=False
        session.max_redirects=MAX_REDIRECTS

        class TrustedFlowAdapter(HTTPAdapter):
            def send(self,request,**kwargs):
                kind=route(request.url)
                if request.method!='GET' or not kind:
                    raise FlowBlocked('untrusted_or_non_read_only_destination')
                if kind[0]=='earthdata_authorize' and not verify_authorize_url(request.url):
                    raise FlowBlocked('unexpected_oauth_authorization_parameters')
                if kind[0]=='harmony_oauth_callback' and not callback_pinned:
                    raise FlowBlocked('unverified_callback')
                if result['requests_sent']>=MAX_REDIRECTS+1:
                    raise FlowBlocked('request_limit')
                auth=request.headers.get('Authorization','')
                if auth and not auth.startswith('Basic '):
                    raise FlowBlocked('unexpected_authentication_method')
                if not result['requests_sent'] and not auth.startswith('Basic '):
                    raise FlowBlocked('username_password_not_selected')
                # Private signatures stay in memory only. Cookie changes permit
                # the legitimate OAuth return to the original jobs URL.
                signature=(request.url,request.headers.get('Cookie',''),bool(auth))
                if signature in seen:
                    raise FlowBlocked('redirect_loop')
                seen.add(signature)
                remaining=TOTAL_SECONDS-(time.monotonic()-started)
                if remaining<=0:
                    raise FlowBlocked('shared_deadline_exceeded')
                if len(session.cookies)>64:
                    raise FlowBlocked('cookie_jar_limit')
                result['stage']='waiting_response_headers:'+kind[0]
                result['requests_sent']+=1
                result['redirects_followed']=result['requests_sent']-1
                kwargs['timeout']=(min(4,remaining),min(6,remaining))
                return super().send(request,**kwargs)

        def response_hook(response,**_kwargs):
            nonlocal callback_pinned,expected_state
            kind=route(response.url)
            if not kind:
                raise FlowBlocked('untrusted_response_origin')
            result['http_status']=response.status_code
            result['stage']='response_received:'+kind[0]
            event={'origin':kind[1],'path':kind[2],'http_status':response.status_code,
                   'elapsed_seconds':round(time.monotonic()-started,3)}
            result['responses'].append(event)
            if response.is_redirect:
                target=urljoin(response.url,response.headers.get('Location',''))
                destination=route(target)
                if not destination:
                    event['redirect_destination']='blocked_untrusted_or_unsupported'
                    raise FlowBlocked('untrusted_or_unsupported_redirect')
                event['redirect_destination']={'origin':destination[1],'path':destination[2]}
                if destination[0]=='earthdata_authorize':
                    if not verify_authorize_url(target):
                        raise FlowBlocked('unexpected_oauth_authorization_parameters')
                    callback_pinned=True
                    states=parse_qs(urlsplit(target).query).get('state',[])
                    if len(states)!=1:
                        raise FlowBlocked('authorization_missing_state')
                    expected_state=states[0]
                    event['documented_edl_authorization_flow_verified']=True
                if destination[0]=='harmony_oauth_callback':
                    params=parse_qs(urlsplit(target).query)
                    if not callback_pinned:
                        raise FlowBlocked('unverified_callback')
                    if 'error' in params:
                        result['status']='REJECTED'
                        raise FlowBlocked('oauth_authorization_denied')
                    if len(params.get('code',[]))!=1 or len(params.get('state',[]))!=1:
                        raise FlowBlocked('callback_missing_code_or_state')
                    if params['state']!=[expected_state]:
                        raise FlowBlocked('callback_state_mismatch')
            # Bound redirect and final bodies before Requests consumes them.
            result['stage']='reading_response_body:'+kind[0]
            body=bytearray()
            for chunk in response.iter_content(16*1024):
                if time.monotonic()-started>TOTAL_SECONDS:
                    raise FlowBlocked('shared_deadline_exceeded')
                body.extend(chunk)
                if len(body)>64*1024:
                    raise FlowBlocked('response_body_limit')
            response._content=bytes(body)
            response._content_consumed=True
            return response

        session.mount('https://',TrustedFlowAdapter(max_retries=0))
        session.mount('http://',TrustedFlowAdapter(max_retries=0))
        session.hooks['response']=[response_hook]
        try:
            with session.get(JOBS,allow_redirects=True,stream=True,timeout=(4,6)) as response:
                final=route(response.url)
                if response.status_code in (401,403):
                    result['status']='REJECTED'
                    result['failure_category']='unauthorized' if response.status_code==401 else 'forbidden'
                elif response.status_code>=500:
                    result['failure_category']='server_error'
                elif response.status_code==200 and final and final[0]=='harmony_jobs':
                    try:
                        data=response.json()
                        valid=isinstance(data,dict) and isinstance(data.get('jobs'),list)
                    except (ValueError,TypeError):
                        valid=False
                    if valid:
                        result['status']='VERIFIED'
                        result['stage']='authenticated_jobs_list_received'
                    else:
                        result['failure_category']='unexpected_non_jobs_response'
                elif response.status_code==200 and final and final[0].startswith('earthdata_'):
                    result['failure_category']='interactive_login_or_consent_required'
                else:
                    result['failure_category']='unexpected_http_response'
        except requests.exceptions.TooManyRedirects:
            result['failure_category']='redirect_limit'
        except requests.exceptions.ConnectTimeout:
            result['failure_category']='connect_timeout'
        except requests.exceptions.ReadTimeout:
            result['failure_category']='read_timeout'
        except requests.exceptions.SSLError:
            result['failure_category']='tls_verification_error'
        except requests.exceptions.RequestException:
            result['failure_category']='transport_error'
    except FlowBlocked as exc:
        result['failure_category']=exc.category
    except Exception:
        result['failure_category']='local_flow_error'
    finally:
        if session is not None:
            result['cookie_jar_populated']=bool(session.cookies)
            session.cookies.clear()
            session.close()
        if client is not None:
            client.executor.shutdown(wait=False,cancel_futures=True)
        result['elapsed_seconds']=round(time.monotonic()-started,3)
    return result


if __name__=='__main__':
    print(json.dumps(run_flow()),flush=True)
