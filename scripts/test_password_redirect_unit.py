"""Official SDK cookie/redirect regressions, with fake credentials and HTTP."""
from email.message import Message
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import quote,urlsplit

import requests
from scripts.harmony_password_redirect_flow import CALLBACK,EDL,HARMONY,JOBS,route,run_flow

AUTHORIZE=EDL+'/oauth/authorize?response_type=code&client_id=TEST_APP&redirect_uri='+quote(CALLBACK,safe='')+'&state=PRIVATE_STATE'
RETURN=CALLBACK+'?code=PRIVATE_CODE&state=PRIVATE_STATE'


def response(request,status,location=None,body=None,cookie=None):
    result=requests.Response()
    result.status_code=status
    result.url=request.url
    result.request=request
    result._content=json.dumps(body or {}).encode()
    result._content_consumed=True
    if location:
        result.headers['Location']=location
    message=Message()
    if cookie:
        message.add_header('Set-Cookie',cookie)
    result.raw=SimpleNamespace(_original_response=SimpleNamespace(msg=message),
                               close=lambda:None,release_conn=lambda:None)
    return result


class RedirectTests(unittest.TestCase):
    def setUp(self):
        env=patch.dict(os.environ,{'EDL_USERNAME':'FAKE_USER','EDL_PASSWORD':'FAKE_PASSWORD',
            'EARTHDATA_TOKEN':'DO_NOT_USE_THIS_TOKEN','HARMONY_PROCESSING_ENABLED':'false'})
        env.start()
        self.addCleanup(env.stop)

    def test_trusted_flow_preserves_cookies_and_uses_sdk_auth_rebuilding(self):
        calls=[]
        def send(request,**kwargs):
            calls.append(request)
            self.assertEqual(request.method,'GET')
            self.assertLessEqual(kwargs['timeout'][1],6)
            if len(calls)==1:
                self.assertTrue(request.headers['Authorization'].startswith('Basic '))
                return response(request,303,AUTHORIZE)
            if len(calls)==2:
                self.assertTrue(request.headers['Authorization'].startswith('Basic '))
                return response(request,302,RETURN)
            if len(calls)==3:
                self.assertNotIn('Authorization',request.headers)
                return response(request,303,JOBS,cookie='harmony_session=PRIVATE_COOKIE; Path=/; Secure; HttpOnly')
            self.assertIn('harmony_session=PRIVATE_COOKIE',request.headers.get('Cookie',''))
            return response(request,200,body={'jobs':[],'username':'FAKE_USER'})
        with patch('requests.adapters.HTTPAdapter.send',side_effect=send):
            result=run_flow()
        self.assertEqual(result['status'],'VERIFIED')
        self.assertEqual(len(calls),4)
        self.assertTrue(result['cookie_jar_populated'])
        self.assertFalse(result['token_used'])
        for private in ['FAKE_USER','FAKE_PASSWORD','PRIVATE_CODE','PRIVATE_STATE','PRIVATE_COOKIE','DO_NOT_USE_THIS_TOKEN']:
            self.assertNotIn(private,json.dumps(result))

    def test_untrusted_redirect_blocked_before_second_request(self):
        calls=[]
        def send(request,**kwargs):
            calls.append(request)
            return response(request,303,'https://untrusted.test/?secret=PRIVATE_CODE')
        with patch('requests.adapters.HTTPAdapter.send',side_effect=send):
            result=run_flow()
        self.assertEqual(len(calls),1)
        self.assertEqual(result['failure_category'],'untrusted_or_unsupported_redirect')
        self.assertNotIn('untrusted.test',json.dumps(result))

    def test_untrusted_registered_callback_blocks_credentials(self):
        bad=EDL+'/oauth/authorize?response_type=code&client_id=X&redirect_uri=https%3A%2F%2Fevil.test%2Fcallback'
        with patch('requests.adapters.HTTPAdapter.send',side_effect=lambda req,**kw:response(req,303,bad)) as send:
            result=run_flow()
        self.assertEqual(send.call_count,1)
        self.assertEqual(result['failure_category'],'unexpected_oauth_authorization_parameters')

    def test_rejection_is_explicit_and_not_retried(self):
        def send(req,**kwargs):
            return response(req,303,AUTHORIZE) if urlsplit(req.url).hostname=='harmony.earthdata.nasa.gov' else response(req,401)
        with patch('requests.adapters.HTTPAdapter.send',side_effect=send) as requests_sent:
            result=run_flow()
        self.assertEqual(result['status'],'REJECTED')
        self.assertEqual(result['http_status'],401)
        self.assertEqual(requests_sent.call_count,2)

    def test_timeout_is_unconfirmed_without_retry(self):
        with patch('requests.adapters.HTTPAdapter.send',side_effect=requests.exceptions.ReadTimeout('FAKE_PASSWORD')) as send:
            result=run_flow()
        self.assertEqual(result['status'],'STILL UNCONFIRMED')
        self.assertEqual(result['failure_category'],'read_timeout')
        self.assertEqual(send.call_count,1)
        self.assertNotIn('FAKE_PASSWORD',json.dumps(result))

    def test_same_state_loop_stops(self):
        with patch('requests.adapters.HTTPAdapter.send',side_effect=lambda req,**kw:response(req,303,JOBS)) as send:
            result=run_flow()
        self.assertEqual(send.call_count,1)
        self.assertEqual(result['failure_category'],'redirect_loop')

    def test_interactive_page_is_not_success(self):
        def send(req,**kwargs):
            return response(req,303,AUTHORIZE) if urlsplit(req.url).hostname=='harmony.earthdata.nasa.gov' else response(req,200)
        with patch('requests.adapters.HTTPAdapter.send',side_effect=send):
            result=run_flow()
        self.assertEqual(result['status'],'STILL UNCONFIRMED')
        self.assertEqual(result['failure_category'],'interactive_login_or_consent_required')

    def test_processing_and_job_control_destinations_are_not_allowed(self):
        for url in [HARMONY+'/jobs/123/cancel',HARMONY+'/C1/ogc-api-coverages/1.0.0/collections/all/coverage/rangeset',
                    'http://urs.earthdata.nasa.gov/oauth/authorize','https://urs.earthdata.nasa.gov.evil.test/oauth/authorize']:
            self.assertIsNone(route(url))

    def test_processing_enabled_blocks_all_requests(self):
        os.environ['HARMONY_PROCESSING_ENABLED']='true'
        with patch('requests.adapters.HTTPAdapter.send') as send:
            result=run_flow()
        self.assertEqual(result['failure_category'],'processing_enabled')
        send.assert_not_called()

    def test_callback_state_mismatch_blocks_callback_request(self):
        def send(req,**kwargs):
            return response(req,303,AUTHORIZE if req.url==JOBS else RETURN.replace('PRIVATE_STATE','WRONG_STATE'))
        with patch('requests.adapters.HTTPAdapter.send',side_effect=send) as calls:
            result=run_flow()
        self.assertEqual(calls.call_count,2)
        self.assertEqual(result['failure_category'],'callback_state_mismatch')

    def test_redirect_count_is_bounded(self):
        counter=0
        def send(req,**kwargs):
            nonlocal counter
            counter+=1
            # Distinct allowlisted URLs avoid the earlier same-state loop guard.
            return response(req,302,AUTHORIZE+'&step='+str(counter))
        with patch('requests.adapters.HTTPAdapter.send',side_effect=send) as calls:
            result=run_flow()
        self.assertEqual(result['failure_category'],'redirect_limit')
        self.assertEqual(calls.call_count,5)

    def test_shared_deadline_blocks_network(self):
        with patch('scripts.harmony_password_redirect_flow.time.monotonic',side_effect=[0,21,22]), patch('requests.adapters.HTTPAdapter.send') as calls:
            result=run_flow()
        self.assertEqual(result['failure_category'],'shared_deadline_exceeded')
        calls.assert_not_called()


if __name__=='__main__':
    unittest.main()
