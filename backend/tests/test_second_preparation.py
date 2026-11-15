"""No NASA calls: second-request scope and lossless first-reference recovery."""
import copy
import hashlib
import json
import shutil
from pathlib import Path
import pytest
from backend.tests.test_harmony import manager,execute
from scripts.prepare_second_harmony_test import register_first_reference,request_checks


def second_plan():
    p=json.loads((Path(__file__).resolve().parents[2]/'docs/harmony-first-test-readiness.json').read_text())['dry_run']['plan']
    p=copy.deepcopy(p)
    p['scene']['id']='G4405182121-ASF'
    p['request_url']=p['request_url'].replace('G4405780437-ASF','G4405182121-ASF')
    return p


def test_second_scope_and_unknown_incidence_remain_explicit():
    p=second_plan()
    request_checks(p,{'status':'unknown'})
    with pytest.raises(RuntimeError,match='incompatibility'):
        request_checks(p,{'status':'incompatible'})
    for before,after in [('G4405182121-ASF','G4405780437-ASF'),('maxResults=1','maxResults=2'),
                         ('image%2Ftiff','application%2Fx-hdf5')]:
        q=copy.deepcopy(p)
        q['request_url']=q['request_url'].replace(before,after)
        with pytest.raises(RuntimeError,match='frozen'):
            request_checks(q,{'status':'unknown'})


def failed_reference(manager):
    job=execute(manager)  # SYNTHETIC upstream and pixels in isolated temp cache.
    source=manager.settings.cache/'audit'/'first.tif'
    source.parent.mkdir()
    target=manager.path(job['id'],'.tif')
    shutil.copyfile(target,source)
    target.unlink()
    job.update(status='failed',raster=None,error={'code':'extent_mismatch','message':'Historical spatial failure'})
    manager.save(job)
    manager.settings.enabled=False
    sha=hashlib.sha256(source.read_bytes()).hexdigest()
    name=job['plan']['scene']['name']+'_frequencyA_HHHH.tif'
    return job,source,target,sha,name


def test_reference_registration_preserves_source_and_original_provenance(manager):
    job,source,target,sha,name=failed_reference(manager)
    before=manager.path(job['id']).read_bytes()
    result=register_first_reference(manager,job['id'],source,name,sha)
    assert result['registered'] and result['changed']
    assert hashlib.sha256(source.read_bytes()).hexdigest()==sha==hashlib.sha256(target.read_bytes()).hexdigest()
    assert (source.parent/'first-job-before-reference-registration.json').read_bytes()==before
    new=manager.get(job['id'])
    assert new['status']=='verified' and new['remote_job_id']==job['remote_job_id']
    assert new['local_spatial_revalidation']['previous_error']==job['error']
    assert len(manager.jobs())==1 and not manager.settings.enabled
    assert manager.capabilities()['second_scene_unlocked']
    assert not register_first_reference(manager,job['id'],source,name,sha)['changed']


def test_changed_reference_or_existing_file_never_overwritten(manager):
    job,source,target,sha,name=failed_reference(manager)
    with pytest.raises(RuntimeError,match='changed'):
        register_first_reference(manager,job['id'],source,name,'0'*64)
    target.write_bytes(b'EXISTING_KEEP')
    with pytest.raises(RuntimeError,match='no data overwritten'):
        register_first_reference(manager,job['id'],source,name,sha)
    assert target.read_bytes()==b'EXISTING_KEEP'
    assert manager.get(job['id'])['status']=='failed'


def test_registration_cannot_run_with_processing_enabled(manager):
    job,source,target,sha,name=failed_reference(manager)
    manager.settings.enabled=True
    with pytest.raises(RuntimeError,match='disabled'):
        register_first_reference(manager,job['id'],source,name,sha)
    assert not target.exists()
