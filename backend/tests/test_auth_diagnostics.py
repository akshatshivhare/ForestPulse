"""Offline diagnostic regression tests; fake credentials, no NASA calls."""
import json
import asyncio

import httpx
import pytest

from backend.app.auth_diagnostics import CAPABILITIES,JOBS,http_probe,safe_target
from backend.app import harmony
from fastapi import HTTPException

SECRET = 'DIAGNOSTIC_TEST_CREDENTIAL'


@pytest.mark.parametrize('status,category',[(401,'unauthorized'),(403,'forbidden'),(429,'rate_limited'),(500,'server_error'),(503,'server_error')])
def test_http_errors_remain_distinct_and_redacted(status,category):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status,headers={'Set-Cookie':'private-cookie=never-store'},
                              json={'error':SECRET,'signed_url':'https://example.test/?signature=never-store'})
    result = http_probe(JOBS,SECRET,transport=httpx.MockTransport(handler))
    assert result['http_status']==status and result['category']==category
    assert len(calls)==1
    exported = json.dumps(result)
    assert SECRET not in exported and 'private-cookie' not in exported and 'signature' not in exported
    assert result['token_accepted'] == (False if status in (401,403) else None)


@pytest.mark.parametrize('exc,category',[(httpx.ConnectTimeout,'connect_timeout'),(httpx.ReadTimeout,'read_timeout'),
                                      (httpx.WriteTimeout,'write_timeout'),(httpx.PoolTimeout,'pool_timeout'),
                                      (httpx.ConnectError,'connection_error')])
def test_timeout_stages_not_misreported_as_401_or_server_http(exc,category):
    calls=[]
    def handler(request):
        calls.append(request)
        raise exc(SECRET,request=request)
    result=http_probe(JOBS,SECRET,transport=httpx.MockTransport(handler))
    assert result['category']==category and result['http_status'] is None
    assert result['token_accepted'] is None and len(calls)==1
    assert SECRET not in json.dumps(result)


@pytest.mark.parametrize('destination,category',[('https://urs.earthdata.nasa.gov/oauth/authorize?code='+SECRET,'login_redirect'),
    ('https://evil.test/?token='+SECRET,'blocked_redirect'),
    ('http://harmony.earthdata.nasa.gov/jobs','blocked_redirect'),
    ('https://harmony.earthdata.nasa.gov.evil.test/jobs','blocked_redirect'),
    ('https://harmony.earthdata.nasa.gov/C1-ASF/ogc-api-coverages/1.0.0/collections/all/coverage/rangeset','blocked_redirect')])
def test_no_credentials_forwarded_to_login_untrusted_or_processing_redirects(destination,category):
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(303,headers={'location':destination,'set-cookie':'sensitive'})
    result=http_probe(JOBS,SECRET,transport=httpx.MockTransport(handler))
    assert result['category']==category and len(calls)==1
    assert SECRET not in json.dumps(result) and 'evil.test' not in json.dumps(result)


def test_same_origin_redirect_loop_is_bounded():
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(302,headers={'location':'/jobs?limit=1'})
    result=http_probe(JOBS,SECRET,transport=httpx.MockTransport(handler))
    assert result['category']=='redirect_loop' and len(calls)==1


def test_acceptance_requires_actual_authenticated_jobs_response():
    result=http_probe(JOBS,SECRET,transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'jobs':[], 'username':SECRET})))
    assert result['token_accepted'] is True and SECRET not in json.dumps(result)
    html=http_probe(JOBS,SECRET,transport=httpx.MockTransport(lambda _:httpx.Response(200,text='<html>Login</html>')))
    assert html['token_accepted'] is None and html['category']=='unexpected_success_body'


def test_public_capabilities_success_does_not_verify_token():
    result=http_probe(CAPABILITIES,transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'services':[]})))
    assert result['token_accepted'] is None
    calls=[]
    result=http_probe(CAPABILITIES,SECRET,transport=httpx.MockTransport(lambda req:calls.append(req)))
    assert result['category']=='blocked_credential_destination' and not calls


@pytest.mark.parametrize('url',['http://harmony.earthdata.nasa.gov/jobs', 'https://harmony.earthdata.nasa.gov:443/jobs',
    'https://harmony.earthdata.nasa.gov/jobs?limit=1000','https://harmony.earthdata.nasa.gov/jobs?token=secret',
    'https://harmony.earthdata.nasa.gov/jobs/id/cancel','https://harmony.earthdata.nasa.gov@evil.test/jobs'])
def test_only_small_read_only_destinations_are_permitted(url):
    assert not safe_target(url)
    result=http_probe(url,SECRET)
    assert result['category']=='blocked_destination' and result['attempts']==0


def test_jobs_response_limit():
    result=http_probe(JOBS,SECRET,transport=httpx.MockTransport(lambda _:httpx.Response(200,content=b'x'*65537)))
    assert result['category']=='response_body_limit' and result['token_accepted'] is None


def test_existing_client_timeout_stays_sanitized_and_has_no_retry_when_disabled(monkeypatch):
    calls=[]
    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout(SECRET,request=request)
    real_client=httpx.AsyncClient
    monkeypatch.setattr(harmony.httpx,'AsyncClient',lambda **kw:real_client(**kw,transport=httpx.MockTransport(handler)))
    with pytest.raises(HTTPException) as error:
        asyncio.run(harmony.Transport(harmony.Settings(token=SECRET)).json(JOBS,auth=True,retry=False))
    assert len(calls)==1 and error.value.detail['code']=='harmony_unavailable'
    assert SECRET not in json.dumps(error.value.detail)


def test_existing_client_untrusted_redirect_is_not_followed(monkeypatch):
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(303,headers={'location':'https://untrusted.test/?secret='+SECRET})
    real_client=httpx.AsyncClient
    monkeypatch.setattr(harmony.httpx,'AsyncClient',lambda **kw:real_client(**kw,transport=httpx.MockTransport(handler)))
    with pytest.raises(HTTPException) as error:
        asyncio.run(harmony.Transport(harmony.Settings(token=SECRET)).json(JOBS,auth=True,retry=False))
    assert len(calls)==1 and error.value.detail['code']=='unexpected_redirect'
    assert SECRET not in json.dumps(error.value.detail) and 'untrusted.test' not in json.dumps(error.value.detail)
