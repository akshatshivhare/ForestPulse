"""Safety tests for the one-shot runner; raster samples are SYNTHETIC."""
import asyncio
import copy
import json
from pathlib import Path

import pytest

from backend.tests.test_harmony import cog
from scripts.live_cog_audit import audit_cog
from scripts import validate_harmony_live as runner
from backend.app.harmony import Transport


def plan():
    return copy.deepcopy(json.loads((Path(__file__).resolve().parents[2]/'docs/harmony-first-test-readiness.json').read_text())['dry_run']['plan'])


def test_frozen_authorization_accepts_only_exact_scope():
    p=plan()
    runner.check_authorized_scope(p)
    for field,value in [('bbox',[88.76,21.85,88.78,21.88]),('variable','frequencyA/HVHV')]:
        q=copy.deepcopy(p)
        q[field]=value
        with pytest.raises(RuntimeError):
            runner.check_authorized_scope(q)
    for before,after in [('G4405780437-ASF','G4405182121-ASF'),('maxResults=1','maxResults=2'),
                         ('forceAsync=true','forceAsync=false'),('https://harmony.earthdata.nasa.gov','https://untrusted.test')]:
        q=copy.deepcopy(p)
        q['request_url']=q['request_url'].replace(before,after)
        with pytest.raises(RuntimeError):
            runner.check_authorized_scope(q)


def test_consumed_authorization_cannot_be_reused(tmp_path,monkeypatch):
    path=tmp_path/'evidence.json'
    path.write_text(json.dumps({'submission_attempts':1}))
    monkeypatch.setattr(runner,'DESTINATION',path)
    with pytest.raises(RuntimeError,match='already been consumed'):
        asyncio.run(runner.main(True,True))
    assert json.loads(path.read_text())=={'submission_attempts':1}


@pytest.mark.parametrize('invalid',[False,True])
def test_audit_preserves_actual_counts_even_when_pixels_invalid(tmp_path,invalid):
    p=plan()
    path=tmp_path/'synthetic-only.tif'
    cog(path,p['bbox'],invalid=invalid)
    asset='https://example.test/'+p['scene']['name']+'_frequencyA_HHHH.tif?signature=DO_NOT_RECORD'
    result=audit_cog(path,p,asset)
    assert result['validation_passed'] is not invalid
    assert result['finite_unmasked_pixels']==(0 if invalid else 10000)
    assert result['statistics']['mean']==(None if invalid else 2)
    assert result['statistics']['standard_deviation_population']==(None if invalid else 0)
    assert result['radar_variable_identity_verified']
    assert 'DO_NOT_RECORD' not in json.dumps(result)
    if invalid:
        assert result['failure_category']=='no_valid_positive_power_pixels'


def test_audit_does_not_infer_identity_from_request(tmp_path):
    p=plan()
    path=tmp_path/'synthetic-only.tif'
    cog(path,p['bbox'])
    result=audit_cog(path,p,'https://example.test/unidentified.tif')
    assert not result['validation_passed']
    assert result['failure_category']=='identity_unconfirmed'


def test_live_observed_distribution_is_exact_and_https_only():
    assert Transport.asset_allowed('https://dqzb5lcolc8fj.cloudfront.net/output.tif?signature=FAKE')
    for url in ['https://other.cloudfront.net/output.tif','http://dqzb5lcolc8fj.cloudfront.net/output.tif',
                'https://dqzb5lcolc8fj.cloudfront.net.evil.test/output.tif',
                'https://user:password@dqzb5lcolc8fj.cloudfront.net/output.tif']:
        assert not Transport.asset_allowed(url)


def test_identity_pass_is_recorded_when_later_extent_check_fails(tmp_path):
    p=plan()
    path=tmp_path/'synthetic-extent-only.tif'
    cog(path,p['bbox'],offset=.001)
    asset='https://example.test/'+p['scene']['name']+'_frequencyA_HHHH.tif'
    result=audit_cog(path,p,asset)
    assert not result['validation_passed'] and result['failure_category']=='extent_mismatch'
    assert result['radar_variable_identity_verified']
    assert result['finite_unmasked_pixels']==10000
    assert not result['existing_extent_check_passed']
