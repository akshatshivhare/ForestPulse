"""Harmony-Py cookie session, using the live-verified EDL redirect flow.

No credential/cookie persistence. All exception text and telemetry are fixed,
public labels; raw requests, response bodies and OAuth parameters stay private.
"""
import json
import logging
import re
import threading
import time
from urllib.parse import parse_qs, urljoin, urlsplit
from uuid import UUID

import requests
from harmony import Client
from requests.adapters import HTTPAdapter

ROOT = 'https://harmony.earthdata.nasa.gov'
EDL = 'https://urs.earthdata.nasa.gov'
JOBS = ROOT + '/jobs?limit=1'
CALLBACK = ROOT + '/oauth2/redirect'
MAX_REDIRECTS = 4
FLOW_SECONDS = 20
SESSION_SECONDS = 900

for name in ('requests', 'urllib3', 'urllib3.connectionpool', 'harmony', 'harmony.client', 'curlify'):
    logging.getLogger(name).setLevel(logging.CRITICAL + 1)


class SessionError(Exception):
    def __init__(self, code, status=502):
        super().__init__(code)
        self.code, self.status = code, status


def route(url):
    """Exact HTTPS origins, never a hostname suffix or an echoed input URL."""
    try:
        u = urlsplit(url)
        if u.scheme != 'https' or u.username or u.password or u.fragment:
            return None
        if u.netloc == 'harmony.earthdata.nasa.gov':
            if u.path == '/jobs' and parse_qs(u.query) in ({}, {'limit': ['1']}):
                return ('harmony_jobs', ROOT, '/jobs')
            if u.path == '/oauth2/redirect':
                return ('harmony_oauth_callback', ROOT, '/oauth2/redirect')
        if u.netloc == 'urs.earthdata.nasa.gov' and u.path in ('/oauth/authorize', '/login'):
            return ('earthdata_authorize' if u.path == '/oauth/authorize' else 'earthdata_login_page', EDL, u.path)
    except (ValueError, TypeError):
        pass
    return None


def verify_authorize_url(url):
    p = parse_qs(urlsplit(url).query)
    return (p.get('redirect_uri') == [CALLBACK] and p.get('response_type') == ['code']
            and len(p.get('client_id', [])) == 1 and bool(p['client_id'][0]))


def harmony_origin(url):
    u = urlsplit(url)
    return u.scheme == 'https' and u.netloc == 'harmony.earthdata.nasa.gov' and not u.fragment


def safe_read(url):
    """GET alone is insufficient: Harmony transformations/cancellation use GET."""
    u = urlsplit(url)
    return harmony_origin(url) and (url == JOBS or bool(re.fullmatch(r'/jobs/[0-9a-fA-F-]{36}', u.path)))


class PasswordSession:
    """One serialized, ephemeral SDK session per backend transport.

    Login/reauthentication only uses /jobs?limit=1. A transformation or job-control
    GET is never followed through EDL and never replayed on authentication loss.
    """
    def __init__(self, username, password):
        self._credentials = (username, password)
        self._client = self._session = None
        self._verified = 0.0
        self._gate = threading.Lock()
        self._context = None
        self.last_evidence = {}
        self.last_operation_evidence = {}

    @property
    def authenticated(self):
        return bool(self._session and self._verified and self._session.cookies
                    and time.monotonic() - self._verified < SESSION_SECONDS)

    def _reset(self):
        if self._session is not None:
            self._session.cookies.clear()
            self._session.close()
        if self._client is not None:
            self._client.executor.shutdown(wait=False, cancel_futures=True)
        self._client = self._session = None
        self._verified = 0.0

    def close(self):
        with self._gate:
            self._reset()

    def _create(self):
        if not all(self._credentials):
            raise SessionError('authentication_required', 401)
        self._client = Client(auth=self._credentials, token=None, should_validate_auth=False)
        if self._client.config.root_url != ROOT:
            raise SessionError('unexpected_sdk_origin')
        self._session = self._client._session()
        self._session.trust_env = False
        self._session.max_redirects = MAX_REDIRECTS
        owner = self

        class Guard(HTTPAdapter):
            def send(self, request, **kwargs):
                ctx = owner._context
                kind = route(request.url)
                if request.method != 'GET' or not ctx:
                    raise SessionError('unsafe_authentication_request')
                if ctx['login']:
                    if not kind:
                        raise SessionError('untrusted_or_unsupported_redirect')
                    if kind[0] == 'earthdata_authorize' and not verify_authorize_url(request.url):
                        raise SessionError('unexpected_oauth_authorization_parameters')
                    if kind[0] == 'harmony_oauth_callback' and ctx['state'] is None:
                        raise SessionError('unverified_callback')
                elif request.url != ctx['url'] or not harmony_origin(request.url):
                    raise SessionError('untrusted_or_unsupported_redirect')
                header = request.headers.get('Authorization', '')
                if header and (not ctx['login'] or not header.startswith('Basic ')):
                    raise SessionError('unexpected_authentication_method')
                signature = (request.url, request.headers.get('Cookie', ''), bool(header))
                if signature in ctx['seen']:
                    raise SessionError('redirect_loop')
                ctx['seen'].add(signature)
                remaining = FLOW_SECONDS - (time.monotonic() - ctx['started'])
                if remaining <= 0:
                    raise SessionError('authentication_timeout', 504)
                if ctx['requests'] >= MAX_REDIRECTS + 1:
                    raise SessionError('redirect_limit')
                if len(owner._session.cookies) > 64:
                    raise SessionError('cookie_jar_limit')
                ctx['requests'] += 1
                ctx['stage'] = 'waiting_response_headers'
                kwargs['timeout'] = (min(4, remaining), min(6, remaining))
                return super().send(request, **kwargs)

        self._session.mount('https://', Guard(max_retries=0))
        self._session.mount('http://', Guard(max_retries=0))
        self._session.hooks['response'] = [self._response]

    def _response(self, response, **_kwargs):
        ctx = self._context
        ctx['stage'] = 'response_received'
        ctx['http_status'] = response.status_code
        kind = route(response.url)
        if ctx['login']:
            if not kind:
                raise SessionError('untrusted_or_unsupported_redirect')
            event = {'origin': kind[1], 'path': kind[2], 'http_status': response.status_code,
                     'elapsed_seconds': round(time.monotonic() - ctx['started'], 3)}
            ctx['responses'].append(event)
            if response.is_redirect:
                target = urljoin(response.url, response.headers.get('Location', ''))
                dest = route(target)
                if not dest:
                    raise SessionError('untrusted_or_unsupported_redirect')
                event['redirect_destination'] = {'origin': dest[1], 'path': dest[2]}
                if dest[0] == 'earthdata_authorize':
                    p = parse_qs(urlsplit(target).query)
                    if not verify_authorize_url(target) or len(p.get('state', [])) != 1:
                        raise SessionError('unexpected_oauth_authorization_parameters')
                    ctx['state'] = p['state'][0]
                if dest[0] == 'harmony_oauth_callback':
                    p = parse_qs(urlsplit(target).query)
                    if 'error' in p:
                        raise SessionError('authentication_required', 401)
                    if ctx['state'] is None or p.get('state') != [ctx['state']] or len(p.get('code', [])) != 1:
                        raise SessionError('callback_state_mismatch')
            # Requests consumes redirect bodies itself. Cache only bounded bodies.
            response._content = self._body(response, 64 * 1024)
            response._content_consumed = True
        elif response.is_redirect:
            # Requests prepares a next request even with allow_redirects=False;
            # it must not consume an unbounded redirect body while doing so.
            response._content = self._body(response, 64 * 1024)
            response._content_consumed = True
        return response

    def _body(self, response, budget, destination=None):
        body = bytearray()
        size = 0
        self._context['stage'] = 'reading_response_body'
        for chunk in response.iter_content(16 * 1024):
            if time.monotonic() - self._context['started'] > FLOW_SECONDS:
                raise SessionError('authentication_timeout', 504)
            size += len(chunk)
            if size > budget:
                raise SessionError('file_too_large' if destination else 'response_body_limit', 413)
            if destination:
                destination.write(chunk)
            else:
                body.extend(chunk)
        return bytes(body)

    def _request(self, url, *, login=False, path=None, budget=None):
        self._context = {'url': url, 'login': login, 'started': time.monotonic(), 'state': None,
                         'requests': 0, 'seen': set(), 'responses': [], 'stage': 'preparing_request'}
        ctx = self._context
        try:
            # New ordinary requests use cookies, never repeat Basic credentials.
            kwargs = {} if login else {'auth': lambda request: request}
            with self._session.get(url, allow_redirects=login, stream=True, timeout=(4, 6), **kwargs) as r:
                if r.status_code in (401, 403):
                    raise SessionError('authentication_required' if r.status_code == 401 else 'authentication_forbidden', 401)
                if r.is_redirect:
                    target = urljoin(url, r.headers.get('Location', ''))
                    ctx['redirect_host'] = urlsplit(target).hostname
                    dest = route(target)
                    if dest and dest[0].startswith('earthdata_'):
                        raise SessionError('session_expired', 401)
                    if path is not None:
                        return target  # Existing transport validates output host on next hop.
                    u = urlsplit(target)
                    m = re.fullmatch(r'/jobs/([0-9a-fA-F-]{36})', u.path)
                    if harmony_origin(target) and m and not u.query:
                        return {'jobID': str(UUID(m[1]))}
                    raise SessionError('unexpected_redirect')
                if r.status_code == 429:
                    raise SessionError('rate_limited', 503)
                if r.status_code == 409:
                    raise SessionError('remote_conflict', 409)
                if r.status_code >= 400:
                    raise SessionError('harmony_unavailable')
                if login and route(r.url)[0] != 'harmony_jobs':
                    raise SessionError('interactive_login_or_consent_required', 401)
                if path is not None:
                    if int(r.headers.get('content-length', '0')) > budget:
                        raise SessionError('file_too_large', 413)
                    with path.open('wb') as output:
                        self._body(r, budget, output)
                    return None
                data = json.loads(self._body(r, 64 * 1024 if login else 1024 * 1024))
                if not isinstance(data, dict) or (login and not isinstance(data.get('jobs'), list)):
                    raise SessionError('invalid_metadata')
                return data
        except requests.exceptions.TooManyRedirects:
            raise SessionError('redirect_limit') from None
        except requests.exceptions.ConnectTimeout:
            raise SessionError('connect_timeout', 504) from None
        except requests.exceptions.ReadTimeout:
            raise SessionError('read_timeout', 504) from None
        except requests.exceptions.SSLError:
            raise SessionError('tls_verification_error') from None
        except (requests.exceptions.RequestException, ValueError, TypeError):
            raise SessionError('harmony_unavailable') from None
        finally:
            if login:
                self.last_evidence = {'responses': ctx['responses'], 'requests_sent': ctx['requests'],
                    'redirects_followed': max(0, ctx['requests'] - 1), 'automatic_retries': 0,
                    'elapsed_seconds': round(time.monotonic() - ctx['started'], 3), 'stage': ctx['stage'],
                    'cookies_in_memory_only': True, 'cookie_jar_populated': bool(self._session.cookies)}
            else:
                # Fixed fields only: no URL, headers, cookies, payload or identity.
                self.last_operation_evidence = {'http_status': ctx.get('http_status'),
                    'stage': ctx['stage'], 'elapsed_seconds': round(time.monotonic()-ctx['started'],3),
                    'requests_sent': ctx['requests'], 'automatic_retries': 0}
                if ctx.get('redirect_host'):
                    self.last_operation_evidence['redirect_host']=ctx['redirect_host']
            self._context = None

    def _login(self):
        self._reset()
        self._create()
        data = self._request(JOBS, login=True)
        self._verified = time.monotonic()
        return data

    def json(self, url, *, replay_safe=True):
        return self._execute(url, replay_safe=replay_safe and safe_read(url))

    def download_harmony(self, url, path, budget):
        return self._execute(url, replay_safe=True, path=path, budget=budget)

    def _execute(self, url, *, replay_safe, path=None, budget=None):
        if not harmony_origin(url):
            raise SessionError('unsafe_remote_url')
        if not self._gate.acquire(blocking=False):
            raise SessionError('authentication_busy', 503)
        try:
            if not self.authenticated:
                data = self._login()
                if url == JOBS and path is None:
                    return data
            try:
                return self._request(url, path=path, budget=budget)
            except SessionError as exc:
                if exc.code not in ('authentication_required', 'session_expired'):
                    raise
                self._reset()
                # retry=False protects submissions and job-control operations.
                if not replay_safe:
                    raise
                data = self._login()  # At most one fresh login for a safe read.
                return data if url == JOBS and path is None else self._request(url, path=path, budget=budget)
        except SessionError:
            self._reset()
            raise
        except Exception:
            self._reset()
            raise SessionError('authentication_unavailable') from None
        finally:
            self._gate.release()
