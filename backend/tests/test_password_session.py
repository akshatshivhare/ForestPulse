"""Offline integration with the real SDK session; all HTTP and secrets fake."""
import asyncio
from email.message import Message
import json
import time
from types import SimpleNamespace
from urllib.parse import quote

import httpx
import pytest
import requests
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app import harmony
from backend.app.earthdata_session import CALLBACK, EDL, JOBS, ROOT, PasswordSession, SessionError
from backend.app.main import app

USERNAME = 'FAKE_EDL_USER'
PASSWORD = 'FAKE_EDL_PASSWORD'
TOKEN = 'FAKE_UNUSED_TOKEN'
PRIVATE = 'PRIVATE_CODE_STATE_COOKIE'
AUTHORIZE = EDL + '/oauth/authorize?response_type=code&client_id=PUBLIC_APP&redirect_uri=' + quote(CALLBACK, safe='') + '&state=' + PRIVATE
RETURN = CALLBACK + '?code=' + PRIVATE + '&state=' + PRIVATE
JOB = ROOT + '/jobs/11111111-1111-4111-8111-111111111111'
SUBMIT = ROOT + '/C3622241360-ASF/ogc-api-coverages/1.0.0/collections/V4137651715-ASF/coverage/rangeset?forceAsync=true'


def response(req, status=200, *, location=None, body=None, cookie=None):
    r = requests.Response()
    r.status_code, r.request, r.url = status, req, req.url
    r._content = json.dumps(body if body is not None else {'jobs': [], 'username': USERNAME}).encode()
    r._content_consumed = True
    if location:
        r.headers['Location'] = location
    message = Message()
    if cookie:
        message.add_header('Set-Cookie', cookie)
    r.raw = SimpleNamespace(_original_response=SimpleNamespace(msg=message), close=lambda: None, release_conn=lambda: None)
    return r


@pytest.fixture
def settings():
    return harmony.Settings(auth_mode='earthdata_password', username=USERNAME, password=PASSWORD, token=TOKEN, enabled=False)


@pytest.fixture
def fake_http(monkeypatch):
    calls = []
    def login(req, **kwargs):
        calls.append(req)
        assert req.method == 'GET' and kwargs['timeout'][0] <= 4 and kwargs['timeout'][1] <= 6
        assert TOKEN not in req.headers.get('Authorization', '')
        if req.url == JOBS and not req.headers.get('Cookie'):
            assert req.headers['Authorization'].startswith('Basic ')
            return response(req, 303, location=AUTHORIZE)
        if req.url == AUTHORIZE:
            assert req.headers['Authorization'].startswith('Basic ')
            return response(req, 302, location=RETURN)
        if req.url == RETURN:
            assert 'Authorization' not in req.headers
            return response(req, 307, location=JOBS, cookie='harmony_session='+PRIVATE+'; Path=/; Secure; HttpOnly')
        assert PRIVATE in req.headers.get('Cookie', '') and 'Authorization' not in req.headers
        return response(req)
    monkeypatch.setattr(requests.adapters.HTTPAdapter, 'send', lambda self, req, **kw: login(req, **kw))
    return calls, login


def test_auth_selection_and_secret_repr(settings, monkeypatch):
    monkeypatch.delenv('HARMONY_AUTH_MODE', raising=False)
    assert harmony.Settings().auth_mode == 'earthdata_token'
    for value in (USERNAME, PASSWORD, TOKEN):
        assert value not in repr(settings)
    settings.password = ''
    assert not settings.authentication_configured  # Does not fall back to present token.
    settings.auth_mode = 'earthdata_token'
    assert settings.authentication_configured
    with pytest.raises(ValueError, match='HARMONY_AUTH_MODE') as exc:
        harmony.Settings(auth_mode=PASSWORD)
    assert PASSWORD not in str(exc.value)


def test_integrated_transport_reuses_verified_session(settings, fake_http):
    t = harmony.Transport(settings)
    try:
        assert isinstance(asyncio.run(t.json(JOBS, auth=True, retry=False))['jobs'], list)
        first_session = t.password_session()._session
        assert isinstance(asyncio.run(t.json(JOBS, auth=True, retry=False))['jobs'], list)
        assert t.password_session()._session is first_session
        assert len(fake_http[0]) == 5  # Four login hops, one cookie-only read.
        assert t.password_session().authenticated
        evidence = json.dumps(t.password_session().last_evidence)
        assert all(s not in evidence for s in (USERNAME, PASSWORD, TOKEN, PRIVATE))
    finally:
        t.close()
    assert not first_session.cookies


def test_missing_password_has_no_network_or_fallback(settings, monkeypatch):
    settings.password = ''
    monkeypatch.setattr(requests.adapters.HTTPAdapter, 'send', lambda *_a, **_kw: pytest.fail('Network forbidden'))
    t = harmony.Transport(settings)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(t.json(JOBS, auth=True, retry=False))
    assert exc.value.status_code == 401


def test_age_expiry_replaces_and_clears_cookie_session(fake_http):
    s = PasswordSession(USERNAME, PASSWORD)
    try:
        s.json(JOBS)
        old = s._session
        s._verified = time.monotonic() - 901
        s.json(JOBS)
        assert len(fake_http[0]) == 8 and s._session is not old
        assert not old.cookies
    finally:
        s.close()


def test_server_expiry_reauthenticates_read_once(fake_http, monkeypatch):
    calls, login = fake_http
    s = PasswordSession(USERNAME, PASSWORD)
    try:
        s.json(JOBS)
        def expired(req, **kw):
            if req.url == JOBS and req.headers.get('Cookie') and len(calls) == 4:
                calls.append(req)
                return response(req, 401)
            return login(req, **kw)
        monkeypatch.setattr(requests.adapters.HTTPAdapter, 'send', lambda self, req, **kw: expired(req, **kw))
        assert s.json(JOBS)['jobs'] == []
        assert len(calls) == 9
    finally:
        s.close()


def test_submission_expiry_is_never_replayed(fake_http, monkeypatch):
    calls, login = fake_http
    def expired(req, **kw):
        if req.url == SUBMIT:
            calls.append(req)
            return response(req, 303, location=AUTHORIZE)
        return login(req, **kw)
    monkeypatch.setattr(requests.adapters.HTTPAdapter, 'send', lambda self, req, **kw: expired(req, **kw))
    s = PasswordSession(USERNAME, PASSWORD)
    with pytest.raises(SessionError, match='session_expired'):
        s.json(SUBMIT, replay_safe=False)
    assert len(calls) == 5 and sum(r.url == SUBMIT for r in calls) == 1
    assert not s.authenticated


@pytest.mark.parametrize('location,code', [
    ('https://untrusted.test/?secret='+PRIVATE, 'untrusted_or_unsupported_redirect'),
    (EDL+'/oauth/authorize?response_type=code&client_id=X&redirect_uri=https%3A%2F%2Fevil.test&state=X', 'unexpected_oauth_authorization_parameters'),
    (JOBS, 'redirect_loop'),
    ('http://urs.earthdata.nasa.gov/oauth/authorize', 'untrusted_or_unsupported_redirect'),
])
def test_unsafe_redirects_stop_before_credentials_forwarded(location, code, monkeypatch):
    calls = []
    def send(self, req, **kw):
        calls.append(req)
        return response(req, 303, location=location)
    monkeypatch.setattr(requests.adapters.HTTPAdapter, 'send', send)
    with pytest.raises(SessionError) as exc:
        PasswordSession(USERNAME, PASSWORD).json(JOBS)
    assert exc.value.code == code and len(calls) == 1
    assert PRIVATE not in str(exc.value)


@pytest.mark.parametrize('status,code', [(401,'authentication_required'), (403,'authentication_forbidden'), (503,'harmony_unavailable')])
def test_http_failures_are_safe_and_bounded(status, code, settings, monkeypatch):
    calls = []
    def send(self, req, **kw):
        calls.append(req)
        return response(req, status, body={'error':PASSWORD, 'url':'https://example.test/?signed='+PRIVATE})
    monkeypatch.setattr(requests.adapters.HTTPAdapter, 'send', send)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(harmony.Transport(settings).json(JOBS, auth=True, retry=False))
    assert exc.value.detail['code'] == code and len(calls) == 1
    assert all(s not in json.dumps(exc.value.detail) for s in (USERNAME, PASSWORD, TOKEN, PRIVATE))


@pytest.mark.parametrize('error,code', [(requests.exceptions.ReadTimeout,'read_timeout'), (requests.exceptions.ConnectTimeout,'connect_timeout'), (requests.exceptions.SSLError,'tls_verification_error')])
def test_transport_errors_never_export_exception_text(error, code, settings, monkeypatch):
    calls = []
    def send(self, req, **kw):
        calls.append(req)
        raise error(PASSWORD+' signed='+PRIVATE)
    monkeypatch.setattr(requests.adapters.HTTPAdapter, 'send', send)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(harmony.Transport(settings).json(JOBS, auth=True, retry=False))
    assert exc.value.detail['code'] == code and len(calls) == 1
    assert PASSWORD not in json.dumps(exc.value.detail)


def test_callback_state_and_redirect_cap(monkeypatch):
    calls = []
    def bad_state(self, req, **kw):
        calls.append(req)
        return response(req, 302, location=AUTHORIZE if len(calls)==1 else RETURN.replace('state='+PRIVATE,'state=WRONG'))
    monkeypatch.setattr(requests.adapters.HTTPAdapter, 'send', bad_state)
    with pytest.raises(SessionError, match='callback_state_mismatch'):
        PasswordSession(USERNAME, PASSWORD).json(JOBS)
    assert len(calls) == 2
    calls.clear()
    def loop(self, req, **kw):
        calls.append(req)
        return response(req, 302, location=AUTHORIZE+'&step='+str(len(calls)))
    monkeypatch.setattr(requests.adapters.HTTPAdapter, 'send', loop)
    with pytest.raises(SessionError, match='redirect_limit'):
        PasswordSession(USERNAME, PASSWORD).json(JOBS)
    assert len(calls) == 5


def test_interactive_page_and_body_limit_not_success(monkeypatch):
    def interactive(self, req, **kw):
        return response(req,303,location=AUTHORIZE) if req.url==JOBS else response(req)
    monkeypatch.setattr(requests.adapters.HTTPAdapter, 'send', interactive)
    with pytest.raises(SessionError, match='interactive_login_or_consent_required'):
        PasswordSession(USERNAME, PASSWORD).json(JOBS)
    def huge(self, req, **kw):
        r = response(req)
        r._content = b'x'*65537
        return r
    monkeypatch.setattr(requests.adapters.HTTPAdapter, 'send', huge)
    with pytest.raises(SessionError, match='response_body_limit'):
        PasswordSession(USERNAME, PASSWORD).json(JOBS)


def test_password_capabilities_and_processing_gate(settings, tmp_path, monkeypatch, fake_http):
    settings.cache = tmp_path
    m = harmony.Manager(settings)
    monkeypatch.setattr(harmony, 'manager', m)
    with TestClient(app) as client:
        setup = client.get('/api/processing/capabilities').json()
        assert setup['authentication_method'] == 'earthdata_password'
        assert setup['authentication_configured'] and not setup['authentication_verified']
        assert setup['state'] == 'processing_disabled'
        assert client.post('/api/processing/jobs', json={'dry_run':False}).status_code == 409
        assert client.post('/api/processing/jobs', json={'password':PASSWORD}).status_code == 422
        assert all(s not in json.dumps(setup) for s in (USERNAME, PASSWORD, TOKEN, PRIVATE))
    assert not fake_http[0] and not m.jobs()


@pytest.mark.parametrize('output_host',['harmony-prod-staging.s3.us-west-2.amazonaws.com','dqzb5lcolc8fj.cloudfront.net'])
def test_output_redirect_uses_anonymous_s3_client(settings, tmp_path, fake_http, monkeypatch, output_host):
    calls, login = fake_http
    asset = ROOT + '/output/test.tif'
    signed = 'https://'+output_host+'/output.tif?signature='+PRIVATE
    def send(req, **kw):
        if req.url == asset:
            calls.append(req)
            assert 'Authorization' not in req.headers
            return response(req,303,location=signed)
        return login(req, **kw)
    monkeypatch.setattr(requests.adapters.HTTPAdapter, 'send', lambda self, req, **kw:send(req, **kw))
    def anonymous(req):
        assert 'authorization' not in req.headers and 'cookie' not in req.headers
        return httpx.Response(200,content=b'MOCK_ONLY',headers={'content-length':'9'})
    original = httpx.AsyncClient
    monkeypatch.setattr(harmony.httpx, 'AsyncClient', lambda **kw:original(**kw,transport=httpx.MockTransport(anonymous)))
    t = harmony.Transport(settings)
    try:
        asyncio.run(t.download(asset,tmp_path/'mock.tif',10))
        assert (tmp_path/'mock.tif').read_bytes() == b'MOCK_ONLY'
        assert PRIVATE not in json.dumps(t.password_session().last_evidence)
    finally:
        t.close()


def test_busy_session_cannot_start_parallel_login():
    s = PasswordSession(USERNAME,PASSWORD)
    with s._gate:
        with pytest.raises(SessionError, match='authentication_busy'):
            s.json(JOBS)


def test_even_default_retry_cannot_replay_submission(settings, fake_http, monkeypatch):
    calls, login = fake_http
    def failed(req, **kw):
        if req.url == SUBMIT:
            calls.append(req)
            return response(req,503)
        return login(req, **kw)
    monkeypatch.setattr(requests.adapters.HTTPAdapter, 'send', lambda self, req, **kw:failed(req, **kw))
    t = harmony.Transport(settings)
    with pytest.raises(HTTPException):
        asyncio.run(t.json(SUBMIT,auth=True))  # retry defaults True, URL overrides it.
    assert sum(req.url==SUBMIT for req in calls) == 1
    t.close()


def test_public_metadata_never_creates_password_session(settings, monkeypatch):
    def handler(req):
        assert 'authorization' not in req.headers and 'cookie' not in req.headers
        return httpx.Response(200,json={'variables':[]})
    original = httpx.AsyncClient
    monkeypatch.setattr(harmony.httpx,'AsyncClient',lambda **kw:original(**kw,transport=httpx.MockTransport(handler)))
    t = harmony.Transport(settings)
    assert asyncio.run(t.json(ROOT+'/capabilities')) == {'variables':[]}
    assert t._password_session is None


def test_cancellation_waits_for_bounded_io_before_cleanup(settings):
    import threading
    entered, release = threading.Event(), threading.Event()
    finished = []
    def blocking_io():
        entered.set()
        assert release.wait(2)
        finished.append(True)
    async def scenario():
        task = asyncio.create_task(harmony.Transport(settings)._password_call(blocking_io))
        assert await asyncio.to_thread(entered.wait,2)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished
    asyncio.run(scenario())


def test_shared_deadline_blocks_send(monkeypatch):
    # Advance time only after the context begins, before adapter network I/O.
    ticks = iter([0,21,22])
    monkeypatch.setattr('backend.app.earthdata_session.time.monotonic',lambda:next(ticks))
    monkeypatch.setattr(requests.adapters.HTTPAdapter,'send',lambda *_a,**_kw:pytest.fail('No I/O after deadline'))
    with pytest.raises(SessionError,match='authentication_timeout'):
        PasswordSession(USERNAME,PASSWORD).json(JOBS)


def test_submission_job_redirect_is_returned_without_following(settings, fake_http, monkeypatch):
    calls, login = fake_http
    def submit(req, **kw):
        if req.url == SUBMIT:
            calls.append(req)
            return response(req,303,location=JOB)
        return login(req, **kw)
    monkeypatch.setattr(requests.adapters.HTTPAdapter,'send',lambda self,req,**kw:submit(req,**kw))
    t = harmony.Transport(settings)
    try:
        data = asyncio.run(t.json(SUBMIT,auth=True,retry=False))
        assert data == {'jobID':JOB.rsplit('/',1)[1]}
        assert len(calls) == 5 and not any(req.url==JOB for req in calls)
    finally:
        t.close()


def test_safe_status_read_has_only_one_reauthentication(fake_http, monkeypatch):
    calls, login = fake_http
    def expired(req,**kw):
        if req.url == JOB:
            calls.append(req)
            return response(req,401)
        return login(req,**kw)
    monkeypatch.setattr(requests.adapters.HTTPAdapter,'send',lambda self,req,**kw:expired(req,**kw))
    s = PasswordSession(USERNAME,PASSWORD)
    with pytest.raises(SessionError,match='authentication_required'):
        s.json(JOB)
    assert len(calls) == 10  # 2 four-hop logins, two status reads, then stop.
    assert sum(req.url==JOB for req in calls) == 2 and not s.authenticated


def test_harmony_download_obeys_actual_size_budget(fake_http, monkeypatch, tmp_path):
    calls, login = fake_http
    url = ROOT+'/output/mock.tif'
    def output(req,**kw):
        if req.url==url:
            calls.append(req)
            assert 'Authorization' not in req.headers
            r = response(req)
            r._content = b'MOCK_PIXELS'
            return r
        return login(req,**kw)
    monkeypatch.setattr(requests.adapters.HTTPAdapter,'send',lambda self,req,**kw:output(req,**kw))
    s = PasswordSession(USERNAME,PASSWORD)
    try:
        path = tmp_path/'only-mock-data.part'
        with pytest.raises(SessionError,match='file_too_large'):
            s.download_harmony(url,path,3)
        assert path.stat().st_size <= 3
    finally:
        s.close()
