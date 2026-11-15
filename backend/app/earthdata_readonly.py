"""Independent documented EDL profile GET. No credentials or profiles exported."""
import base64
import json
import logging
import re
import time

import httpx

for name in ['httpx','httpcore']:
    logging.getLogger(name).setLevel(logging.CRITICAL+1)


def profile_target_uid(token, fallback_username=None):
    """A claim selects a URL only. Decoding a JWT is NOT token validation."""
    uid = None
    try:
        if len(token)<=32768 and len(token.split('.'))==3:
            segment = token.split('.')[1]
            claims = json.loads(base64.urlsafe_b64decode(segment+'='*((-len(segment))%4)))
            uid = claims.get('uid') if isinstance(claims,dict) else None
    except Exception:
        pass
    uid = uid or fallback_username
    if isinstance(uid,str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',uid) and uid not in {'.','..'}:
        return uid
    return None


def verify_profile_access(token, *, fallback_username=None, transport=None):
    started = time.monotonic()
    result = {'endpoint_template':'GET https://urs.earthdata.nasa.gov/api/users/{uid}',
              'mechanism':'documented scoped user-profile access; not general token introspection',
              'credential_file_modified':False,'redirects_followed':False,'automatic_retries':0,
              'http_status':None,'category':None,'token_accepted_for_profile_api':None,
              'profile_identity_match':None,'stage':'before_request','attempts':0}
    uid = profile_target_uid(token,fallback_username)
    if not token or not uid:
        result['category'] = 'blocked_missing_token_or_profile_target'
        return result
    def trace(event,_info):
        if event.endswith('connect_tcp.started'):
            result['stage']='dns_or_tcp_connect'
        elif event.endswith('start_tls.started'):
            result['stage']='tls_handshake'
        elif event.endswith('receive_response_headers.started'):
            result['stage']='waiting_response_headers'
    try:
        with httpx.Client(timeout=httpx.Timeout(connect=4,read=6,write=4,pool=2),
                          trust_env=False,follow_redirects=False,transport=transport) as client:
            # uid is strictly path-safe and never printed/persisted. The trusted
            # EDL origin receives the token directly, without any redirect.
            result['attempts']=1
            with client.stream('GET','https://urs.earthdata.nasa.gov/api/users/'+uid,
                               headers={'Accept':'application/json','Authorization':'Bearer '+token},
                               extensions={'trace':trace}) as response:
                result['http_status']=response.status_code
                result['stage']='response_headers_received'
                if response.is_redirect:
                    result['category']='redirect_not_followed'
                elif response.status_code in (401,403):
                    result['category']='unauthorized' if response.status_code==401 else 'forbidden'
                    result['token_accepted_for_profile_api']=False
                elif response.status_code>=500:
                    result['category']='server_error'
                elif response.status_code==200:
                    result['stage']='reading_response_body'
                    body=bytearray()
                    for chunk in response.iter_bytes(16*1024):
                        body.extend(chunk)
                        if len(body)>64*1024:
                            result['category']='response_body_limit'
                            return result
                    try:
                        profile=json.loads(body)
                        matched=isinstance(profile,dict) and profile.get('uid')==uid
                    except (ValueError,TypeError):
                        matched=False
                    result['profile_identity_match']=matched
                    result['token_accepted_for_profile_api']=True if matched else None
                    result['category']='profile_access_confirmed' if matched else 'unexpected_success_body'
                    result['stage']='complete'
                else:
                    result['category']='http_error'
    except httpx.ConnectTimeout:
        result['category']='connect_timeout'
    except httpx.ReadTimeout:
        result['category']='read_timeout'
    except httpx.ConnectError:
        result['category']='connection_error'
    except httpx.HTTPError:
        result['category']='transport_error'
    except Exception:
        result['category']='local_diagnostic_error'
    finally:
        result['elapsed_seconds']=round(time.monotonic()-started,3)
    return result
