"""Local fixtures only: no Harmony calls or satellite-data downloads."""
import copy
import json
import time
from uuid import uuid4

import cv2
import numpy as np
import pytest
import rasterio
from fastapi import HTTPException
from fastapi.testclient import TestClient
from rasterio.transform import from_origin

from backend.app import image_data as data, image_comparison as engine
from backend.app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, 'CACHE', tmp_path/'comparisons')
    return TestClient(app)


def pair(kind='rgb'):
    return data.get_image(f'sim-{kind}-before'), data.get_image(f'sim-{kind}-after')


def test_gallery_dates_and_one_genuine_observation(client):
    response=client.get('/api/images')
    assert response.status_code==200
    images=response.json()['images']
    assert len(images)==5
    assert len([i for i in images if not i['is_simulated']])==1
    assert all(i['acquisition_date'] is None for i in images if i['is_simulated'])
    assert response.json()['available_dates']==sorted({i['scenario_date'] or i['acquisition_date'] for i in images if i['available']})
    real=next(i for i in images if not i['is_simulated'])
    assert real['acquisition_date']=='2026-10-23'
    assert real['units']=='linear_HHHH_power' and real['calibration']=='normalization_not_independently_verified'
    assert 'file' not in images[0]


@pytest.mark.parametrize('field,value', [('area_id','elsewhere'),('pair_group','other'),('sensor','other'),('is_simulated',False),('data_type','sar_power'),('scenario_date','2025-01-01')])
def test_incompatible_pairs(field,value):
    a,b=map(copy.deepcopy,pair())
    b[field]=value
    with pytest.raises(HTTPException): engine.compatible(a,b)


def test_radar_units_and_polarization_required():
    a,b=map(copy.deepcopy,pair('sar'))
    b['units']='unknown'
    with pytest.raises(HTTPException): engine.compatible(a,b)
    b['units']=a['units']; b['polarization']='VV'
    with pytest.raises(HTTPException): engine.compatible(a,b)


def test_power_ratio_and_nodata_not_display_subtraction():
    a=np.ones((20,20),np.float32); b=a*2; valid=np.ones(a.shape,bool)
    valid[0,:]=False; a[0,:]=np.nan; b[0,:]=np.nan
    signal,_,mask,_,summary=engine.compare_arrays(a,b,valid,True,3,0,5)
    assert np.allclose(signal[valid],10*np.log10(2),atol=1e-5)
    assert summary['valid_pixels']==380 and summary['changed_pixels']==380
    assert not mask[0].any()


def test_filters_remove_small_regions_without_nodata_bleed():
    a=np.ones((20,20),np.float32); b=a.copy(); b[4,4]=10; valid=np.ones(a.shape,bool)
    assert engine.compare_arrays(a,b,valid,True,3,0,2)[4]['changed_pixels']==0
    b[:]=a; b[5:15,5:15]=10; valid[8:12,8:12]=False
    _,_,mask,_,_=engine.compare_arrays(a,b,valid,True,3,1,5)
    assert not mask[~valid].any() and mask.any()


@pytest.mark.parametrize('valid_count',[0,20])
def test_empty_or_tiny_overlap_rejected(valid_count):
    a=np.ones((10,10),np.float32); valid=np.zeros(a.shape,bool); valid.ravel()[:valid_count]=True
    with pytest.raises(HTTPException,match='64 shared valid pixels'):
        engine.compare_arrays(a,a,valid,True,3,1,5)


def test_feature_registration_measured_translation():
    a,b=pair(); (x,vx),(y,vy),alignment=engine.align(data.load(a),data.load(b),False)
    matrix=np.array(alignment['affine_after_to_before'])
    assert np.allclose(matrix[:,2],[-5,3],atol=.5)
    assert alignment['inliers']>100 and alignment['reprojection_rmse_pixels']<1.5
    assert alignment['geographic_location_verified'] is False
    assert (vx&vy).sum()>180000 and x.shape==y.shape


def test_unrelated_images_and_no_features_rejected():
    a=data.load(pair()[0]); b={**a,'data':np.zeros_like(a['data'])}
    with pytest.raises(HTTPException): engine.align(a,b,False)
    b={**a,'data':np.random.default_rng(1).integers(0,256,a['data'].shape,dtype=np.uint8)}
    with pytest.raises(HTTPException): engine.align(a,b,False)


def test_common_grid_shift_and_wrong_location():
    a=data.load(pair('sar')[0]); b=copy.deepcopy(a)
    t=a['transform']; dx=t.a*.5
    b['transform']=from_origin(t.c+dx,t.f,t.a,-t.e)
    bb=a['bounds']; b['bounds']=(bb.left+dx,bb.bottom,bb.right+dx,bb.top)
    (x,vx),(y,vy),alignment=engine.align(a,b,True)
    assert x.shape==y.shape and (vx&vy).any()
    assert alignment['resampling']=='bilinear in linear power space'
    b['bounds']=(0,0,100,100)
    with pytest.raises(HTTPException): engine.align(a,b,True)
    b['crs']=None
    with pytest.raises(HTTPException): engine.align(a,b,True)


def test_db_sources_converted_before_reprojection(tmp_path,monkeypatch):
    path=tmp_path/'db.tif'
    with rasterio.open(path,'w',driver='GTiff',height=10,width=10,count=1,dtype='float32',crs='EPSG:32645',transform=from_origin(680810,2420600,10,10)) as ds:
        ds.write(np.full((10,10),-10,np.float32),1)
    monkeypatch.setattr(data,'WORKSPACE',tmp_path)
    result=data.load({'file':'db.tif','data_type':'sar_power','units':'gamma0_db'})
    assert np.allclose(result['data'],.1)


@pytest.mark.parametrize('kind',['rgb','sar'])
def test_api_real_local_pipeline_and_pdf(client,kind):
    response=client.post('/api/image-comparisons',json={'before_id':f'sim-{kind}-before','after_id':f'sim-{kind}-after'})
    assert response.status_code==202
    job=client.get('/api/image-comparisons/'+response.json()['id']).json()
    assert job['status']=='completed',job.get('error')
    result=job['result']; summary=result['summary']
    assert result['is_simulated'] and result['ecological_validation'] is False
    assert 0<summary['changed_pixels']<summary['valid_pixels']
    assert summary['region_count']>=2
    assert 'hectares' not in summary
    pdf=client.get(result['assets']['report'])
    assert pdf.status_code==200 and pdf.content.startswith(b'%PDF-')
    assert len(pdf.content)<16*1024*1024
    for asset in ('before','after','heatmap','overlay','mask','valid'):
        image=client.get(result['assets'][asset]); assert image.status_code==200
        assert cv2.imdecode(np.frombuffer(image.content,np.uint8),cv2.IMREAD_UNCHANGED) is not None
    mask=cv2.imdecode(np.frombuffer(client.get(result['assets']['mask']).content,np.uint8),0)
    assert np.count_nonzero(mask)==summary['changed_pixels']


def test_api_error_paths_and_secret_redaction(client):
    response=client.post('/api/image-comparisons',json={'before_id':'sim-rgb-before','after_id':'sim-rgb-before'})
    assert response.status_code==422 and response.json()['detail']['code']=='same_image'
    response=client.post('/api/image-comparisons',json={'before_id':'SECRET-INJECTED','after_id':'sim-rgb-after','password':'SECRET-INJECTED'})
    assert response.status_code==422 and 'SECRET-INJECTED' not in response.text
    assert client.get('/api/image-comparisons/not-a-uuid').status_code==404
    assert client.get('/api/image-comparisons/'+str(uuid4())).status_code==404
    assert client.get('/api/images/missing/preview').status_code==404


def test_safe_worker_failure(client,monkeypatch):
    def broken(*args): raise RuntimeError('SECRET-INJECTED')
    monkeypatch.setattr(engine,'align',broken)
    response=client.post('/api/image-comparisons',json={'before_id':'sim-rgb-before','after_id':'sim-rgb-after'})
    job=client.get('/api/image-comparisons/'+response.json()['id'])
    assert job.json()['status']=='failed' and 'SECRET-INJECTED' not in job.text
    assert client.get('/api/image-comparisons/'+response.json()['id']+'/assets/report').status_code==409


def test_bounded_cache_and_expiry(client,monkeypatch):
    monkeypatch.setattr(engine,'MAX_JOBS',2)
    engine.CACHE.mkdir()
    for age in [10,30,20]:
        job={'id':str(uuid4()),'created_epoch':time.time()-age,'status':'completed'};engine._write(job)
    engine.cleanup()
    remaining=[json.loads(p.read_text()) for p in engine.CACHE.glob('*/state.json')]
    assert len(remaining)==1 and time.time()-remaining[0]['created_epoch']<11
    remaining[0]['created_epoch']=time.time()-86401;engine._write(remaining[0])
    assert client.get('/api/image-comparisons/'+remaining[0]['id']).status_code==410


def test_registry_path_escape_and_invalid_manifest(tmp_path,monkeypatch):
    with pytest.raises(HTTPException): data.asset_path({'file':'../outside.png'})
    manifest=tmp_path/'catalog.json';monkeypatch.setattr(data,'MANIFEST',manifest)
    assert data.entries()==[]
    manifest.write_text('{"images":[{"id":"missing-fields"}]}')
    with pytest.raises(HTTPException): data.entries()


def test_source_pixel_limit_and_queue_bound(client,monkeypatch):
    monkeypatch.setattr(data,'MAX_PIXELS',100)
    with pytest.raises(HTTPException) as exc: data.load(pair()[0])
    assert exc.value.status_code==413
    engine.CACHE.mkdir()
    for _ in range(2):
        engine._write({'id':str(uuid4()),'status':'queued','created_epoch':time.time()})
    response=client.post('/api/image-comparisons',json={'before_id':'sim-rgb-before','after_id':'sim-rgb-after'})
    assert response.status_code==409 and response.json()['detail']['code']=='comparison_busy'


def test_windows_transient_state_lock_retry(client,monkeypatch):
    from pathlib import Path
    replace=Path.replace;calls=[]
    def transient(path,target):
        calls.append(path)
        if len(calls)<3: raise PermissionError('Simulated Windows sharing lock')
        return replace(path,target)
    monkeypatch.setattr(Path,'replace',transient)
    job={'id':str(uuid4()),'created_epoch':time.time(),'status':'queued'}
    engine._write(job)
    assert len(calls)==3 and engine.read_job(job['id'])['status']=='queued'
    job['created_epoch']=time.time()-91;engine._write(job)
    assert engine.read_job(job['id'])['status']=='failed'
