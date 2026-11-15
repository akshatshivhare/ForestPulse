"""SDK-environment unit tests. All network responses and credentials are fake."""
import json
import os
import unittest
from unittest.mock import patch

import requests
from harmony import Client
from scripts.harmony_password_auth_probe import run_probe


class PasswordProbeTests(unittest.TestCase):
    def setUp(self):
        self.environment=patch.dict(os.environ,{'EDL_USERNAME':'FAKE_USER','EDL_PASSWORD':'FAKE_PASSWORD',
            'EARTHDATA_TOKEN':'FAKE_TOKEN_MUST_NOT_BE_USED','HARMONY_PROCESSING_ENABLED':'false'})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def response(self,status,body=None):
        result=requests.Response()
        result.status_code=status
        result.url='https://harmony.earthdata.nasa.gov/jobs?limit=1'
        result.request=requests.Request('GET',result.url).prepare()
        result._content=json.dumps(body or {}).encode()
        result._content_consumed=True
        return result

    def test_password_explicitly_selected_even_when_token_exists(self):
        with patch('harmony.Client',wraps=Client) as factory,patch('requests.adapters.HTTPAdapter.send',
                return_value=self.response(200,{'jobs':[],'username':'FAKE_USER','private':'FAKE_PASSWORD'})) as send:
            result=run_probe()
        factory.assert_called_once_with(auth=('FAKE_USER','FAKE_PASSWORD'),token=None,should_validate_auth=False)
        self.assertEqual(send.call_count,1)
        self.assertTrue(send.call_args.args[0].headers['Authorization'].startswith('Basic '))
        self.assertEqual(send.call_args.kwargs['timeout'],(4,6))
        self.assertEqual(result['outcome'],'succeeded')
        self.assertTrue(result['authentication_confirmed'])
        self.assertFalse(result['token_used'])
        self.assertNotIn('FAKE_USER',json.dumps(result))
        self.assertNotIn('FAKE_PASSWORD',json.dumps(result))
        self.assertNotIn('FAKE_TOKEN',json.dumps(result))

    def test_401_failure(self):
        with patch('requests.adapters.HTTPAdapter.send',return_value=self.response(401)) as send:
            result=run_probe()
        self.assertEqual(result['outcome'],'failed_unauthorized')
        self.assertEqual(send.call_count,1)

    def test_timeout_no_retry_or_secret_exception(self):
        with patch('requests.adapters.HTTPAdapter.send',side_effect=requests.exceptions.ReadTimeout('FAKE_PASSWORD')) as send:
            result=run_probe()
        self.assertEqual(result['outcome'],'timed_out_read')
        self.assertEqual(result['stage'],'waiting_response_headers')
        self.assertEqual(send.call_count,1)
        self.assertNotIn('FAKE_PASSWORD',json.dumps(result))

    def test_redirect_is_not_authentication_success(self):
        redirect=self.response(303)
        redirect.headers['Location']='https://untrusted.test/'
        with patch('requests.adapters.HTTPAdapter.send',return_value=redirect) as send:
            result=run_probe()
        self.assertEqual(send.call_count,1)
        self.assertFalse(result['authentication_confirmed'])
        self.assertEqual(result['outcome'],'unconfirmed_redirect_requires_authentication_flow')
        self.assertNotIn('untrusted.test',json.dumps(result))

    def test_processing_enabled_blocks_network(self):
        os.environ['HARMONY_PROCESSING_ENABLED']='true'
        with patch('requests.adapters.HTTPAdapter.send') as send:
            result=run_probe()
        self.assertEqual(result['outcome'],'blocked_processing_enabled')
        send.assert_not_called()

    def test_missing_password_never_falls_back_to_token(self):
        os.environ['EDL_PASSWORD']=''
        with patch('requests.adapters.HTTPAdapter.send') as send:
            result=run_probe()
        self.assertEqual(result['outcome'],'blocked_missing_username_or_password')
        send.assert_not_called()


if __name__=='__main__':
    unittest.main()
