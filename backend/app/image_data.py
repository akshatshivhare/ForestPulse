"""Curated local imagery only. No URL ingestion, NASA request or credentials."""
import json
from pathlib import Path
import re
from datetime import date
from uuid import uuid4
import cv2
import numpy as np
import rasterio
from fastapi import HTTPException
from PIL import Image
from .runtime import cache_root

WORKSPACE=Path(__file__).resolve().parents[2]
MANIFEST=WORKSPACE/'datasets/catalog.json'
MAX_PIXELS=1_048_576
MAX_SOURCE_BYTES=32*1024*1024


def fail(code,message,status=422):
    raise HTTPException(status,detail={'code':code,'message':message})


def asset_path(entry):
    path=(WORKSPACE/entry['file']).resolve()
    if (not path.is_relative_to(WORKSPACE) or path.suffix.lower() not in {'.tif','.tiff','.png','.jpg','.jpeg'}
            or Path(entry['file']).is_absolute()):
        fail('invalid_dataset','The curated dataset contains an unsupported asset.')
    if not path.is_file():
        fail('image_unavailable','This local image is unavailable. Choose a preloaded image.',404)
    if path.stat().st_size>MAX_SOURCE_BYTES:
        fail('image_too_large','This image exceeds the 32 MiB local source limit.',413)
    return path


def entries():
    if not MANIFEST.exists():
        return []
    try:
        data=json.loads(MANIFEST.read_text(encoding='utf-8'))
        images=data['images']
        ids=[e['id'] for e in images]
        if len(images)>100 or len(ids)!=len(set(ids)) or any(not re.fullmatch(r'[a-z0-9-]{1,64}',i) for i in ids):
            raise ValueError()
        for entry in images:
            required=('name','file','area_id','area','source','sensor','data_type','units','pair_group')
            if any(not isinstance(entry.get(k),str) or not entry[k] for k in required):
                raise ValueError()
            if type(entry.get('is_simulated')) is not bool:
                raise ValueError()
            value=entry.get('scenario_date') if entry['is_simulated'] else entry.get('acquisition_date')
            date.fromisoformat(value)
            if entry['is_simulated'] and entry.get('acquisition_date') is not None:
                raise ValueError()
        return images
    except (ValueError,KeyError,TypeError,OSError):
        fail('invalid_catalog','The local gallery manifest needs review.',500)


def get_image(image_id):
    entry=next((e for e in entries() if e['id']==image_id),None)
    if entry is None:
        fail('image_not_found','Choose an image from the available local gallery.',404)
    asset_path(entry)
    return entry


def public(entry):
    fields=('id','name','area_id','area','source','sensor','data_type','units','is_simulated','acquisition_date',
            'scenario_date','date_kind','pair_group','polarization','frequency','calibration','provenance','notice')
    result={k:entry.get(k) for k in fields}
    result['filename']=Path(entry['file']).name
    try:
        path=asset_path(entry)
        result.update(available=True,thumbnail_url=f'/api/images/{entry["id"]}/preview?v={path.stat().st_mtime_ns}')
    except HTTPException:
        result.update(available=False,thumbnail_url=None)
    return result


def load(entry):
    path=asset_path(entry)
    if path.suffix.lower() in {'.tif','.tiff'}:
        with rasterio.open(path) as ds:
            if ds.width*ds.height>MAX_PIXELS or ds.count not in (1,3,4):
                fail('image_too_large','Use one radar band or an RGB image of at most 1,048,576 pixels.',413)
            raw=ds.read(masked=True)
            valid=~np.ma.getmaskarray(raw).any(axis=0)&np.isfinite(raw.data).all(axis=0)
            if entry['data_type']=='sar_power':
                if ds.count!=1:
                    fail('invalid_radar','A radar comparison requires one identified power band.')
                data=raw.data[0].astype('float32')
                if entry['units']=='gamma0_db':
                    with np.errstate(over='ignore',invalid='ignore'):
                        data=np.power(10.,data/10.).astype('float32')
                valid&=np.isfinite(data)&(data>0)
            else:
                if ds.count<3 or raw.dtype!=np.uint8:
                    fail('invalid_rgb','RGB rasters require three uint8 display bands.')
                data=np.moveaxis(raw.data[:3],0,2)
                if ds.count==4:
                    valid&=raw.data[3]>0
            return {'data':data,'valid':valid,'crs':ds.crs,'transform':ds.transform,'bounds':ds.bounds}
    with Image.open(path) as header:
        if header.width*header.height>MAX_PIXELS:
            fail('image_too_large','Use images of at most 1,048,576 pixels.',413)
    raw=cv2.imread(str(path),cv2.IMREAD_UNCHANGED)
    if raw is None or raw.ndim!=3 or raw.shape[2] not in (3,4) or raw.dtype!=np.uint8:
        fail('invalid_rgb','The curated image is not a readable uint8 RGB/RGBA image.')
    if raw.shape[0]*raw.shape[1]>MAX_PIXELS:
        fail('image_too_large','Use images of at most 1,048,576 pixels.',413)
    valid=raw[:,:,3]>0 if raw.shape[2]==4 else np.ones(raw.shape[:2],bool)
    data=cv2.cvtColor(raw[:,:,:3],cv2.COLOR_BGR2RGB)
    if entry.get('nodata_rgb') is not None:
        valid&=np.any(data!=np.asarray(entry['nodata_rgb']),axis=2)
    return {'data':data,'valid':valid,'crs':None,'transform':None,'bounds':None}


def display(data,valid,sar=False,stretch=None):
    if sar:
        db=np.full(data.shape,np.nan,dtype='float32')
        db[valid]=10*np.log10(data[valid])
        limits=stretch if stretch is not None else (np.percentile(db[valid],[2,98]) if valid.any() else [-30,0])
        low,high=float(limits[0]),float(limits[1])
        scale=np.clip((np.nan_to_num(db,nan=low)-low)/max(high-low,1e-6),0,1)
        # Display-only forest/teal ramp; quantitative calculations use raw power.
        rgb=np.stack([18+scale*158,44+scale*174,48+scale*143],axis=2).astype('uint8')
    else:
        rgb=np.clip(np.nan_to_num(data),0,255).astype('uint8').copy()
    rgb[~valid]=[12,28,31]
    return rgb


def preview(entry):
    source=asset_path(entry)
    folder=cache_root()/'image-previews'
    folder.mkdir(parents=True,exist_ok=True)
    target=folder/(entry['id']+'.png')
    if not target.exists() or target.stat().st_mtime<source.stat().st_mtime:
        image=load(entry)
        rgb=display(image['data'],image['valid'],entry['data_type']=='sar_power')
        scale=min(1,480/max(rgb.shape[:2]))
        rgb=cv2.resize(rgb,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA)
        temp=folder/(entry['id']+'.'+str(uuid4())+'.tmp.png')
        if not cv2.imwrite(str(temp),cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR)):
            fail('preview_failed','Could not create the local preview.',500)
        temp.replace(target)
    return target
