"""Read-only authentication diagnostics; independent of the processing client.

No transformation, job control or arbitrary URL is allowed. Only categorized
outcomes are returned; response bodies, headers and locations stay in memory.
"""
import json
import logging
import time
from urllib.parse import urljoin, urlsplit, parse_qs

import httpx

ORIGIN = 'https://harmony.earthdata.nasa.gov'
JOBS = ORIGIN + '/jobs?limit=1'
CAPABILITIES = ORIGIN + '/capabilities?collectionId=C3622241360-ASF'
for name in ['httpx', 'httpcore', 'urllib3', 'requests']:
    logging.getLogger(name).setLevel(logging.CRITICAL + 1)


def safe_target(url):
    try:
        u = urlsplit(url)
        if u.scheme != 'https' or u.netloc != 'harmony.earthdata.nasa.gov' or u.fragment:
            return False
        params = parse_qs(u.query, keep_blank_values=True)
        if u.path == '/jobs':
            return set(params) <= {'limit', 'page'} and all(len(v) == 1 and v[0].isdigit() and 0 < int(v[0]) <= 1 for v in params.values())
        return u.path == '/capabilities' and params == {'collectionId': ['C3622241360-ASF']}
    except (ValueError, TypeError):
        return False


def redirect_category(url):
    try:
        u = urlsplit(url)
        if u.scheme == 'https' and u.netloc == 'urs.earthdata.nasa.gov':
            return 'earthdata_login'
        if safe_target(url):
            return 'same_origin_read_only'
        return 'untrusted_or_unsupported'
    except ValueError:
        return 'untrusted_or_unsupported'


def http_category(status):
    if status == 401:
        return 'unauthorized'
    if status == 403:
        return 'forbidden'
    if status == 429:
        return 'rate_limited'
    if 500 <= status <= 599:
        return 'server_error'
    if 300 <= status <= 399:
        return 'redirect'
    if 200 <= status <= 299:
        return 'http_success'
    return 'http_error'


def http_probe(url, token='', *, trust_env=True, transport=None, max_redirects=2):
    started = time.monotonic()
    result = {'method':'GET', 'endpoint_category':'jobs_list' if url == JOBS else 'collection_capabilities',
              'authenticated_request':bool(token), 'trust_environment':trust_env,
              'http_status':None, 'category':None, 'token_accepted':None,
              'redirects':[], 'stage':'before_request', 'attempts':0}
    def trace(event, _info):
        # _info may contain headers: never inspect, log or persist it.
        if event.endswith('connect_tcp.started'):
            result['stage'] = 'dns_or_tcp_connect'
        elif event.endswith('start_tls.started'):
            result['stage'] = 'tls_handshake'
        elif event.endswith('start_tls.complete'):
            result['stage'] = 'tls_complete'
        elif event.endswith('receive_response_headers.started'):
            result['stage'] = 'waiting_response_headers'
    seen = set()
    try:
        with httpx.Client(timeout=httpx.Timeout(connect=4, read=6, write=4, pool=2),
                          trust_env=trust_env, follow_redirects=False, transport=transport) as client:
            for _ in range(max_redirects + 1):
                if not safe_target(url):
                    result['category'] = 'blocked_destination'
                    return result
                if token and urlsplit(url).path != '/jobs':
                    result['category'] = 'blocked_credential_destination'
                    return result
                if url in seen:
                    result['category'] = 'redirect_loop'
                    return result
                seen.add(url)
                headers = {'Accept':'application/json', 'Client-Id':'ForestPulse-Auth-Diagnostic'}
                if token:
                    headers['Authorization'] = 'Bearer ' + token
                result['attempts'] += 1
                with client.stream('GET', url, headers=headers, extensions={'trace':trace}) as response:
                    result['http_status'] = response.status_code
                    result['category'] = http_category(response.status_code)
                    result['stage'] = 'response_headers_received'
                    if response.is_redirect:
                        target = urljoin(url, response.headers.get('location',''))
                        kind = redirect_category(target)
                        result['redirects'].append({'http_status':response.status_code, 'destination_category':kind})
                        if kind == 'earthdata_login':
                            result['category'] = 'login_redirect'
                            return result  # No credential forwarding to a different origin.
                        if kind != 'same_origin_read_only':
                            result['category'] = 'blocked_redirect'
                            return result
                        url = target
                        continue
                    if response.status_code in (401,403):
                        result['token_accepted'] = False if token else None
                    if response.status_code == 200 and result['endpoint_category'] == 'jobs_list':
                        result['stage'] = 'reading_response_body'
                        body = bytearray()
                        for chunk in response.iter_bytes(16*1024):
                            body.extend(chunk)
                            if len(body) > 64*1024:
                                result['category'] = 'response_body_limit'
                                return result
                        try:
                            data = json.loads(body)
                            valid = isinstance(data,dict) and isinstance(data.get('jobs'),list)
                        except (ValueError,TypeError):
                            valid = False
                        result['jobs_list_received'] = valid
                        if token and valid:
                            result['token_accepted'] = True
                        elif token:
                            result['category'] = 'unexpected_success_body'
                    result['stage'] = 'complete'
                    return result
            result['category'] = 'redirect_limit'
    except httpx.ConnectTimeout:
        result['category'] = 'connect_timeout'
    except httpx.ReadTimeout:
        result['category'] = 'read_timeout'
    except httpx.WriteTimeout:
        result['category'] = 'write_timeout'
    except httpx.PoolTimeout:
        result['category'] = 'pool_timeout'
    except httpx.ConnectError:
        result['category'] = 'connection_error'  # DNS/TLS probes distinguish these separately.
    except httpx.HTTPError:
        result['category'] = 'transport_error'
    except Exception:
        result['category'] = 'local_diagnostic_error'
    finally:
        result['elapsed_seconds'] = round(time.monotonic() - started,3)
    return result
