"""Production policy and ephemeral-storage regression tests. No NASA jobs."""
import os
from pathlib import Path
import subprocess
import sys

from fastapi.testclient import TestClient
import pytest

from backend.app import runtime, harmony, image_comparison
from backend.app.config import allowed_origins
from backend.app.deployment import validate_demo_assets
from backend.app.main import app


@pytest.mark.parametrize('origin',['*','https://*.vercel.app','https://site.vercel.app/path','http://site.vercel.app','https://user:password@site.vercel.app','https://site.vercel.app?token=x',''])
def test_production_requires_exact_safe_origins(origin):
    with pytest.raises(ValueError): allowed_origins(origin,production=True)


def test_explicit_origins_and_loopback_smoke_origin():
    assert allowed_origins(' https://forestpulse.example/,https://forestpulse.example ',True)==['https://forestpulse.example']
    assert allowed_origins('http://127.0.0.1:4174',True)==['http://127.0.0.1:4174']


def test_production_uses_temporary_cache_and_wipes_processing_credentials(monkeypatch,tmp_path):
    monkeypatch.setattr(runtime,'PRODUCTION',True)
    monkeypatch.delenv('FORESTPULSE_CACHE_DIR',raising=False)
    assert runtime.cache_root()!=runtime.WORKSPACE/'artifacts'
    settings=harmony.Settings(enabled=True,token='FAKE-SECRET',username='FAKE-USER',password='FAKE-PASSWORD',cache=tmp_path)
    assert settings.enabled is False and not settings.authentication_configured
    assert settings.token==settings.username==settings.password==''
    monkeypatch.setenv('FORESTPULSE_CACHE_DIR',str(tmp_path))
    assert runtime.cache_root()==tmp_path.resolve()
    monkeypatch.setenv('FORESTPULSE_CACHE_DIR','relative')
    with pytest.raises(ValueError):runtime.cache_root()


def test_render_detection_is_fail_closed(monkeypatch):
    monkeypatch.setenv('FORESTPULSE_ENV','development')
    monkeypatch.setenv('RENDER','true')
    assert runtime.production_mode()


def test_prod_guard_blocks_private_routes_before_any_manager_action(monkeypatch,tmp_path):
    monkeypatch.setattr(runtime,'PRODUCTION',True)
    manager=harmony.Manager(harmony.Settings(cache=tmp_path))
    monkeypatch.setattr(harmony,'manager',manager)
    client=TestClient(app)
    for method,path in [('POST','/api/processing/jobs'),('GET','/api/processing/jobs'),
                        ('GET','/api/processing/jobs/private-id'),('POST','/api/processing/jobs/private-id/cancel'),
                        ('GET','/api/processing/jobs/private-id/raster')]:
        response=client.request(method,path,json={'dry_run':False,'password':'FAKE-SECRET'} if method=='POST' else None)
        assert response.status_code==403
        assert response.json()['detail']['code']=='processing_private'
        assert 'FAKE-SECRET' not in response.text
    capabilities=client.get('/api/processing/capabilities').json()
    assert capabilities['state']=='processing_disabled' and capabilities['public_deployment']
    assert client.get('/api/health').json()['harmony_processing_enabled'] is False


def test_production_startup_and_local_comparison_no_harmony_worker(monkeypatch,tmp_path):
    monkeypatch.setattr(runtime,'PRODUCTION',True)
    monkeypatch.setattr(image_comparison,'CACHE',tmp_path/'jobs')
    async def forbidden_worker():raise AssertionError('Production must never run Harmony worker')
    monkeypatch.setattr(harmony.manager,'worker',forbidden_worker)
    with TestClient(app) as client:
        assert client.get('/api/health').json()['generated_files_ephemeral'] is True
        response=client.post('/api/image-comparisons',json={'before_id':'sim-rgb-before','after_id':'sim-rgb-after'})
        assert response.status_code==202
        job=client.get('/api/image-comparisons/'+response.json()['id']).json()
        assert job['status']=='completed' and job['result']['is_simulated'] is True
        pdf=client.get(job['result']['assets']['report'])
        assert pdf.status_code==200 and pdf.content.startswith(b'%PDF-')
        assert client.get('/api/image-comparisons/00000000-0000-4000-8000-000000000000').status_code==404


def test_assets_do_not_depend_on_working_directory(monkeypatch,tmp_path):
    monkeypatch.chdir(tmp_path)
    assert validate_demo_assets()['required_demo_images']==4


def test_production_import_does_not_load_local_dotenv(tmp_path):
    env={**os.environ,'FORESTPULSE_ENV':'production','ALLOWED_ORIGINS':'https://forestpulse.example',
         'FORESTPULSE_CACHE_DIR':str(tmp_path),'HARMONY_PROCESSING_ENABLED':'true',
         'EDL_USERNAME':'FAKE-USER','EDL_PASSWORD':'FAKE-PASSWORD','EARTHDATA_TOKEN':'FAKE-TOKEN'}
    code="from backend.app import config,harmony; assert config.TOKEN==''; s=harmony.Settings(); assert not s.enabled and not s.authentication_configured; print('production-isolation-ok')"
    result=subprocess.run([sys.executable,'-c',code],cwd=runtime.WORKSPACE,env=env,capture_output=True,text=True,timeout=30)
    assert result.returncode==0 and result.stdout.strip()=='production-isolation-ok'
    assert 'FAKE-' not in result.stdout+result.stderr
