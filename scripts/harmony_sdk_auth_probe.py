"""Isolated Harmony-Py GET-only probe. Emits only a sanitized result."""
import json
import logging
import os
import time
from urllib.parse import urlsplit


def main():
    for name in ['requests','urllib3','harmony']:
        logging.getLogger(name).setLevel(logging.CRITICAL + 1)
    result = {'client':'harmony-py', 'endpoint_category':'jobs_list', 'method':'GET',
              'token_accepted':None, 'http_status':None, 'redirect_following':False,
              'retry_count':0, 'trust_environment':False}
    started = time.monotonic()
    try:
        from dotenv import load_dotenv
        from harmony import Client
        from importlib.metadata import version
        import requests
        from requests.adapters import HTTPAdapter
        load_dotenv()
        if os.getenv('HARMONY_PROCESSING_ENABLED','').lower() == 'true':
            result['category'] = 'blocked_processing_enabled'
            return result
        token = os.getenv('EARTHDATA_TOKEN','').strip()
        if not token:
            result['category'] = 'authentication_missing'
            return result
        result['client_version'] = version('harmony-py')
        # The constructor is NOT used as evidence of successful authentication.
        client = Client(token=token, should_validate_auth=False)
        session = client._session()
        session.trust_env = False  # Avoid .netrc fallback and proxy ambiguity.
        class ReadOnlyAdapter(HTTPAdapter):
            def send(self, request, **kwargs):
                u = urlsplit(request.url)
                if request.method != 'GET' or u.scheme != 'https' or u.netloc != 'harmony.earthdata.nasa.gov' or u.path != '/jobs' or u.query != 'limit=1':
                    raise RuntimeError('Blocked non-diagnostic request.')
                kwargs['timeout'] = (4,6)
                return super().send(request,**kwargs)
        session.mount('https://',ReadOnlyAdapter(max_retries=0))
        session.mount('http://',ReadOnlyAdapter(max_retries=0))
        try:
            response = session.get('https://harmony.earthdata.nasa.gov/jobs?limit=1',
                                   timeout=(4,6),allow_redirects=False,stream=True)
            with response:
                result['http_status'] = response.status_code
                if response.status_code == 401:
                    result.update(category='unauthorized',token_accepted=False)
                elif response.status_code == 403:
                    result.update(category='forbidden',token_accepted=False)
                elif response.status_code >= 500:
                    result['category'] = 'server_error'
                elif 300 <= response.status_code < 400:
                    result['category'] = 'redirect_not_followed'
                elif response.status_code == 200:
                    body = bytearray()
                    for chunk in response.iter_content(16*1024):
                        body.extend(chunk)
                        if len(body)>64*1024:
                            result['category'] = 'response_body_limit'
                            return result
                    data = json.loads(body)
                    accepted = isinstance(data,dict) and isinstance(data.get('jobs'),list)
                    result.update(category='http_success' if accepted else 'unexpected_success_body',
                                  token_accepted=True if accepted else None)
                else:
                    result['category'] = 'http_error'
        except requests.exceptions.ConnectTimeout:
            result['category'] = 'connect_timeout'
        except requests.exceptions.ReadTimeout:
            result['category'] = 'read_timeout'
        except requests.exceptions.SSLError:
            result['category'] = 'tls_error'
        except requests.exceptions.RequestException:
            result['category'] = 'transport_error'
        finally:
            session.close()
            client.executor.shutdown(wait=False,cancel_futures=True)
    except Exception:
        result['category'] = 'sdk_diagnostic_error'
    finally:
        result['elapsed_seconds'] = round(time.monotonic()-started,3)
        print(json.dumps(result),flush=True)
    return result


if __name__ == '__main__':
    main()
