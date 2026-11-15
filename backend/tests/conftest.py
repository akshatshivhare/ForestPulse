"""Keep all regression runs independent of real local authentication settings.

Install before collection: imported application globals must never pick up real
credentials. Individual tests select modes and fake credentials explicitly.
The opt-in public metadata integration flag remains untouched.
"""
import pytest


def pytest_configure(config):
    config._forestpulse_environment = pytest.MonkeyPatch()
    for key,value in {'HARMONY_AUTH_MODE':'earthdata_token', 'EARTHDATA_TOKEN':'',
                      'EDL_USERNAME':'', 'EDL_PASSWORD':'', 'HARMONY_PROCESSING_ENABLED':'false'}.items():
        config._forestpulse_environment.setenv(key,value)


def pytest_unconfigure(config):
    guard = getattr(config,'_forestpulse_environment',None)
    if guard is not None:
        guard.undo()
