"""Deployment policy and writable paths; source datasets stay in the repository."""
import os
from pathlib import Path
import tempfile

WORKSPACE = Path(__file__).resolve().parents[2]


def production_mode():
    return os.getenv('FORESTPULSE_ENV', '').lower() == 'production' or os.getenv('RENDER', '').lower() == 'true'


PRODUCTION = production_mode()


def cache_root():
    configured = os.getenv('FORESTPULSE_CACHE_DIR', '').strip()
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            raise ValueError('FORESTPULSE_CACHE_DIR must be an absolute writable cache directory.')
        return path.resolve()
    return Path(tempfile.gettempdir()) / 'forestpulse' if PRODUCTION else WORKSPACE / 'artifacts'
