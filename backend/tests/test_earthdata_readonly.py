"""Mocked independent EDL checks. No token/profile data is exported."""
import base64
import json
from types import SimpleNamespace

import httpx
import pytest

from backend.app.earthdata_readonly import profile_target_uid,verify_profile_access
from scripts import harmony_auth_followup


def fake_token(uid='private-test-user'):
    segment=base64.urlsafe_b64encode(json.dumps({'uid':uid}).encode()).decode().rstrip('=')
    return 'unverified.'+segment+'.fake-signature'


def test_decoded_uid_selects_target_but_does_not_prove_authentication():
    token=fake_token()
    assert profile_target_uid(token)=='private-test-user'
    calls=[]
    def handler(request):
        calls.append(request)
        assert request.url.host=='urs.earthdata.nasa.gov' and request.method=='GET'
        return httpx.Response(401,json={'error':'invalid_token','secret':token})
    result=verify_profile_access(token,transport=httpx.MockTransport(handler))
    assert result['http_status']==401 and result['token_accepted_for_profile_api'] is False and len(calls)==1
    exported=json.dumps(result)
    assert token not in exported and 'private-test-user' not in exported and 'fake-signature' not in exported


def test_matching_profile_200_confirms_only_that_scoped_api():
    token=fake_token()
    result=verify_profile_access(token,transport=httpx.MockTransport(lambda _:httpx.Response(200,
        json={'uid':'private-test-user','email_address':'private@example.test','access_token':token})))
    assert result['category']=='profile_access_confirmed' and result['profile_identity_match']
    assert result['token_accepted_for_profile_api'] is True
    assert 'private@example.test' not in json.dumps(result) and token not in json.dumps(result)


@pytest.mark.parametrize('location',['https://urs.earthdata.nasa.gov/login','https://untrusted.test/?token=secret'])
def test_profile_redirects_never_forward_credentials(location):
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(303,headers={'location':location,'set-cookie':'private-cookie'})
    result=verify_profile_access(fake_token(),transport=httpx.MockTransport(handler))
    assert result['category']=='redirect_not_followed' and len(calls)==1
    assert 'private-cookie' not in json.dumps(result) and location not in json.dumps(result)


@pytest.mark.parametrize('uid',['../tokens','..','.','name?token=secret','name/another','name@other.test'])
def test_claim_cannot_change_profile_endpoint(uid):
    calls=[]
    result=verify_profile_access(fake_token(uid),transport=httpx.MockTransport(lambda req:calls.append(req)))
    assert result['category']=='blocked_missing_token_or_profile_target' and result['attempts']==0 and not calls


def test_profile_read_timeout_is_not_an_auth_rejection():
    def handler(request):
        raise httpx.ReadTimeout(fake_token(),request=request)
    result=verify_profile_access(fake_token(),transport=httpx.MockTransport(handler))
    assert result['category']=='read_timeout' and result['http_status'] is None
    assert result['token_accepted_for_profile_api'] is None and fake_token() not in json.dumps(result)


def test_alternative_network_requires_explicit_confirmation(monkeypatch):
    import backend.app.harmony as harmony
    monkeypatch.setattr(harmony,'Settings',lambda:SimpleNamespace(enabled=False))
    for confirmed,network in [(False,None),(False,'trusted_mobile_hotspot'),(True,None)]:
        args=SimpleNamespace(mode='alternative',confirm_network_switch=confirmed,network_type=network)
        with pytest.raises(RuntimeError,match='explicitly confirmed'):
            harmony_auth_followup.main(args)


def test_alternative_child_allows_exactly_one_harmony_request(monkeypatch):
    from backend.app import auth_diagnostics
    monkeypatch.setenv('HARMONY_PROCESSING_ENABLED','false')
    monkeypatch.setenv('EARTHDATA_TOKEN',fake_token())
    calls=[]
    def probe(url,token,**kwargs):
        calls.append((url,kwargs))
        return {'category':'read_timeout'}
    monkeypatch.setattr(auth_diagnostics,'http_probe',probe)
    result=harmony_auth_followup.child('alternative')
    assert len(calls)==1 and calls[0][0]==auth_diagnostics.JOBS
    assert calls[0][1]=={'trust_env':False,'max_redirects':0} and result['category']=='read_timeout'
