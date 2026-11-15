import os
from urllib.parse import urlsplit
from dotenv import load_dotenv
from . import runtime

if not runtime.PRODUCTION:
    load_dotenv(runtime.WORKSPACE / '.env')
CMR_BASE = os.getenv('CMR_BASE_URL', 'https://cmr.earthdata.nasa.gov/search').rstrip('/')
TOKEN = '' if runtime.PRODUCTION else os.getenv('EARTHDATA_TOKEN', '')
TIMEOUT = float(os.getenv('CMR_TIMEOUT_SECONDS', '30'))
CACHE_SECONDS = int(os.getenv('CMR_CACHE_SECONDS', '300'))
def allowed_origins(value, production=False):
    origins = list(dict.fromkeys(origin.strip().rstrip('/') for origin in value.split(',') if origin.strip()))
    if production and not origins:
        raise ValueError('Production requires ALLOWED_ORIGINS with the exact frontend origin.')
    for origin in origins:
        parsed = urlsplit(origin)
        local = parsed.hostname in {'localhost', '127.0.0.1', '::1'}
        if (parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment or '*' in origin
                or (production and parsed.scheme != 'https' and not local)):
            raise ValueError('ALLOWED_ORIGINS must contain exact HTTPS origins (HTTP loopback is allowed for local checks).')
    return origins


ORIGINS = allowed_origins(os.getenv('ALLOWED_ORIGINS', '' if runtime.PRODUCTION else
                                  'http://127.0.0.1:5173,http://localhost:5173'), runtime.PRODUCTION)
PILOT_BBOX = [88.4, 21.55, 89.1, 22.25]
