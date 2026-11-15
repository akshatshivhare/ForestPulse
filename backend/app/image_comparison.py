"""Bounded automatic local comparison. Independent of CMR/Harmony processing."""
import json
import math
from pathlib import Path
import shutil
import threading
import time
from uuid import UUID,uuid4

import cv2
import numpy as np
from fastapi import APIRouter,BackgroundTasks,HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel,ConfigDict,Field
from rasterio.transform import from_origin
from rasterio.warp import reproject,Resampling,transform_bounds
from . import image_data as catalog
from .runtime import cache_root

cv2.setNumThreads(1)
router=APIRouter(prefix='/api',tags=['Preloaded image comparison'])
CACHE=cache_root()/'image-comparisons'
SERIAL=threading.Lock()
ADMISSION=threading.Lock()
STATE_LOCK=threading.RLock()
MAX_JOBS=20
MAX_CACHE=256*1024*1024
ASSETS={'before','after','heatmap','overlay','mask','valid','report'}


class CompareImages(BaseModel):
    model_config=ConfigDict(extra='forbid')
    before_id:str=Field(pattern=r'^[a-z0-9-]{1,64}$')
    after_id:str=Field(pattern=r'^[a-z0-9-]{1,64}$')
    threshold:float|None=Field(default=None,ge=.1,le=100)
    noise_radius:int=Field(default=1,ge=0,le=2)
    min_region_pixels:int=Field(default=64,ge=1,le=100000)


def compatible(a,b):
    if a['id']==b['id']:
        catalog.fail('same_image','Choose two different images.')
    for key,label in [('area_id','geographic area'),('pair_group','curated comparison group'),
                      ('data_type','data type'),('sensor','sensor'),('is_simulated','real/simulated provenance')]:
        if a.get(key)!=b.get(key) or a.get(key) is None:
            catalog.fail('incompatible_images',f'The images do not share the same {label}. Choose a matched gallery pair.')
    date_a=a.get('scenario_date') if a['is_simulated'] else a.get('acquisition_date')
    date_b=b.get('scenario_date') if b['is_simulated'] else b.get('acquisition_date')
    if not date_a or not date_b or date_a>=date_b:
        catalog.fail('invalid_image_dates','Choose an earlier baseline and a later available observation or scenario.')
    if a['data_type']=='sar_power':
        for key in ('calibration','frequency','polarization'):
            if not a.get(key) or a.get(key)!=b.get(key):
                catalog.fail('incompatible_radar','Radar comparison requires matching calibration, frequency and polarization.')
        if any(e.get('units') not in {'gamma0_linear_power','gamma0_db'} for e in (a,b)):
            catalog.fail('unknown_radar_units','Only identified calibrated power or power-dB values can be compared.')
    elif a['data_type']!='rgb':
        catalog.fail('unsupported_image_type','Choose a curated RGB or radar-power pair.')


def align(a,b,sar):
    if bool(a['crs'])!=bool(b['crs']):
        catalog.fail('mixed_georeferencing','Both images need georeferencing, or both must use verified image-space registration.')
    if a['crs']:
        t=a['transform']
        if t.a<=0 or t.e>=0 or t.b or t.d:
            catalog.fail('unsupported_reference_grid','Use a north-up reference grid for local comparison.')
        bb=transform_bounds(b['crs'],a['crs'],*b['bounds'],densify_pts=21)
        aa=a['bounds']
        left,bottom,right,top=max(aa[0],bb[0]),max(aa[1],bb[1]),min(aa[2],bb[2]),min(aa[3],bb[3])
        area=max(0,right-left)*max(0,top-bottom)
        fractions=[area/((v[2]-v[0])*(v[3]-v[1])) for v in (aa,bb)]
        if min(fractions)<.95:
            catalog.fail('different_coverage','Both georeferenced images must cover at least 95% of each other. No unrelated-area comparison was run.')
        rx,ry=t.a,-t.e
        left=t.c+math.ceil((left-t.c)/rx-1e-8)*rx
        top=t.f-math.ceil((t.f-top)/ry-1e-8)*ry
        width,height=math.floor((right-left)/rx+1e-8),math.floor((top-bottom)/ry+1e-8)
        if min(width,height)<8 or width*height>catalog.MAX_PIXELS:
            catalog.fail('invalid_common_grid','No bounded common grid is available.')
        target=from_origin(left,top,rx,ry)
        outputs=[]
        for item in (a,b):
            raw=item['data']
            channels=[raw] if sar else [raw[:,:,i] for i in range(3)]
            warped=[]
            for channel in channels:
                src=np.where(item['valid'],channel,np.nan).astype('float32')
                dst=np.full((height,width),np.nan,np.float32)
                reproject(src,dst,src_transform=item['transform'],src_crs=item['crs'],src_nodata=np.nan,
                    dst_transform=target,dst_crs=a['crs'],dst_nodata=np.nan,resampling=Resampling.bilinear,num_threads=1)
                warped.append(dst)
            data=warped[0] if sar else np.stack(warped,axis=2)
            valid=np.isfinite(data) if sar else np.isfinite(data).all(axis=2)
            if sar:
                valid&=data>0
            outputs.append((data,valid))
        return *outputs,{'method':'Georeferenced common grid','confidence':'georeferenced',
            'confidence_note':'Coordinate alignment is verified; source geolocation accuracy and ecological comparability are not.',
            'crs':a['crs'].to_string(),'resolution':[rx,ry],'transform':list(target)[:6],
            'bounds':[left,top-height*ry,left+width*rx,top],'coverage_fraction_each':fractions,
            'resampling':'bilinear in linear power space' if sar else 'bilinear RGB display values',
            'geographic_location_verified':True}
    if sar:
        catalog.fail('radar_georeferencing_required','Radar values require georeferencing; feature registration of speckle is not used.')
    orb=cv2.ORB_create(nfeatures=3500,fastThreshold=8,edgeThreshold=15)
    ka,da=orb.detectAndCompute(cv2.cvtColor(a['data'],cv2.COLOR_RGB2GRAY),a['valid'].astype('uint8')*255)
    kb,db=orb.detectAndCompute(cv2.cvtColor(b['data'],cv2.COLOR_RGB2GRAY),b['valid'].astype('uint8')*255)
    if da is None or db is None or min(len(ka),len(kb))<20:
        catalog.fail('alignment_unreliable','Too few shared features to align these images. Geographic change is not established.')
    matches=cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(db,da,k=2)
    good=[m for pair in matches if len(pair)==2 for m,n in [pair] if m.distance<.75*n.distance]
    if len(good)<12:
        catalog.fail('alignment_unreliable','No reliable feature match. Choose images of the same scene.')
    source=np.float32([kb[m.queryIdx].pt for m in good])
    destination=np.float32([ka[m.trainIdx].pt for m in good])
    cv2.setRNGSeed(42)
    matrix,inliers=cv2.estimateAffinePartial2D(source,destination,method=cv2.RANSAC,ransacReprojThreshold=2.5,maxIters=3000,confidence=.995)
    if matrix is None or inliers is None:
        catalog.fail('alignment_unreliable','Feature registration failed. No difference map was produced.')
    selected=inliers.ravel().astype(bool)
    count=int(selected.sum());ratio=count/len(good)
    predicted=cv2.transform(source[None,:,:],matrix)[0]
    rmse=float(np.sqrt(np.mean(np.square(predicted[selected]-destination[selected]).sum(axis=1)))) if count else math.inf
    h,w=a['valid'].shape
    cells={(min(2,int(x/w*3)),min(2,int(y/h*3))) for x,y in destination[selected]}
    scale=math.sqrt(abs(np.linalg.det(matrix[:,:2])))
    if count<12 or ratio<.35 or rmse>2.5 or len(cells)<4 or not .8<=scale<=1.25:
        catalog.fail('alignment_unreliable','Feature registration did not meet the inlier, distribution or residual limits.')
    data=cv2.warpAffine(b['data'],matrix,(w,h),flags=cv2.INTER_LINEAR,borderValue=0)
    mask=cv2.warpAffine(b['valid'].astype('uint8')*255,matrix,(w,h),flags=cv2.INTER_LINEAR,borderValue=0)>=254
    overlap=float((a['valid']&mask).sum()/max(1,a['valid'].sum()))
    if overlap<.6:
        catalog.fail('insufficient_visual_overlap','Registered images have insufficient shared valid coverage.')
    return (a['data'],a['valid']),(data,mask),{'method':'ORB features + RANSAC partial-affine registration',
        'confidence':'high' if count>=60 and ratio>=.7 and rmse<=1.5 else 'moderate',
        'confidence_note':'Heuristic registration confidence from measured matches, inliers and residuals; not an accuracy score.',
        'matches':len(good),'inliers':count,'inlier_ratio':ratio,'reprojection_rmse_pixels':rmse,
        'spatial_feature_cells':len(cells),'shared_coverage_fraction':overlap,'affine_after_to_before':matrix.tolist(),
        'crs':None,'geographic_location_verified':False,
        'geographic_note':'Same locality is curator metadata; feature alignment proves visual overlap, not geographic accuracy.'}


def compare_arrays(a,b,valid,sar,threshold,radius,min_region):
    if not valid.any() or int(valid.sum())<64:
        catalog.fail('no_valid_pixels','Fewer than 64 shared valid pixels remain. No comparison was produced.')
    if sar:
        signal=np.zeros(valid.shape,np.float32)
        signal[valid]=10*np.log10(b[valid])-10*np.log10(a[valid])
        units='dB power difference'
    else:
        aa=cv2.cvtColor(np.nan_to_num(a).astype('float32')/255,cv2.COLOR_RGB2LAB)
        bb=cv2.cvtColor(np.nan_to_num(b).astype('float32')/255,cv2.COLOR_RGB2LAB)
        signal=np.linalg.norm(bb-aa,axis=2).astype('float32')
        units='CIE76 visual color difference'
    signal[~valid]=0
    if radius:
        k=radius*2+1
        numerator=cv2.GaussianBlur(signal,(k,k),0)
        weights=cv2.GaussianBlur(valid.astype('float32'),(k,k),0)
        filtered=np.divide(numerator,weights,out=np.zeros_like(signal),where=weights>0)
    else:
        filtered=signal.copy()
    magnitude=np.abs(filtered)
    raw_mask=(magnitude>=threshold)&valid
    n,labels,stats,_=cv2.connectedComponentsWithStats(raw_mask.astype('uint8'),8)
    keep=[i for i in range(1,n) if int(stats[i,cv2.CC_STAT_AREA])>=min_region]
    changed=np.isin(labels,keep)&valid
    regions=[]
    for rank,i in enumerate(sorted(keep,key=lambda j:stats[j,cv2.CC_STAT_AREA],reverse=True)[:50],1):
        region=labels==i
        contours,_=cv2.findContours(region.astype('uint8'),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        contours=sorted(contours,key=cv2.contourArea,reverse=True)
        polygon=cv2.approxPolyDP(contours[0],1.2,True).reshape(-1,2).tolist() if contours else []
        mean=float(filtered[region].mean())
        regions.append({'id':rank,'pixels':int(stats[i,cv2.CC_STAT_AREA]),'bbox':stats[i,:4].astype(int).tolist(),
            'mean_indicator_magnitude':float(magnitude[region].mean()),'polygon':polygon,
            'direction':('brightening' if mean>0 else 'darkening') if sar else 'visual difference'})
    summary={'valid_pixels':int(valid.sum()),'invalid_or_nonoverlap_pixels':int(valid.size-valid.sum()),
        'changed_pixels':int(changed.sum()),'changed_percent_of_valid':float(changed.sum()/valid.sum()*100),
        'region_count':len(keep),'regions_displayed':len(regions),'indicator_units':units,
        'mean_absolute_difference':float(np.abs(signal[valid]).mean()),
        'p95_absolute_difference':float(np.percentile(np.abs(signal[valid]),95)),
        'mean_signed_difference_db':float(signal[valid].mean()) if sar else None,
        'brightening_pixels':int((changed&(filtered>0)).sum()) if sar else None,
        'darkening_pixels':int((changed&(filtered<0)).sum()) if sar else None}
    return signal,magnitude,changed,regions,summary


def _directory(job_id):
    try:
        safe=str(UUID(job_id))
    except ValueError:
        catalog.fail('comparison_not_found','Comparison not found or expired.',404)
    path=CACHE/safe
    if path.is_symlink() or path.resolve().parent!=CACHE.resolve():
        catalog.fail('unsafe_cache','Unsafe comparison cache entry.',500)
    return path


def _write(job):
    directory=_directory(job['id'])
    directory.mkdir(parents=True,exist_ok=True)
    with STATE_LOCK:
        temp=directory/'state.tmp'
        temp.write_text(json.dumps(job,allow_nan=False),encoding='utf-8')
        # Windows readers and sync/antivirus tools can briefly prevent replacement.
        # Serialize local reads and bound retries to 620 ms; never retry processing.
        for attempt in range(6):
            try:
                temp.replace(directory/'state.json')
                break
            except PermissionError:
                if attempt==5:
                    raise
                time.sleep(.02*2**attempt)


def _read_state(path):
    with STATE_LOCK:
        return json.loads(path.read_text(encoding='utf-8'))


def read_job(job_id):
    path=_directory(job_id)/'state.json'
    if not path.exists():
        catalog.fail('comparison_not_found','Comparison not found or expired. Run the local comparison again.',404)
    job=_read_state(path)
    if time.time()-job['created_epoch']>86400:
        catalog.fail('comparison_expired','This comparison expired. Run it again to recreate the report.',410)
    if job['status'] in {'queued','running'} and time.time()-job['created_epoch']>90:
        job.update(status='failed',stage='Interrupted',error={'code':'comparison_interrupted',
            'message':'The local comparison stopped updating. Run it again; no successful result is assumed.'})
    return job


def cleanup():
    CACHE.mkdir(parents=True,exist_ok=True)
    completed=[]
    usage=0
    for directory in CACHE.iterdir():
        if directory.is_symlink() or not directory.is_dir():
            continue
        try:
            _directory(directory.name)
            state=_read_state(directory/'state.json')
        except (ValueError,OSError,HTTPException):
            continue
        if state['status'] in {'queued','running'}:
            if time.time()-state['created_epoch']>120:
                state.update(status='failed',stage='interrupted',error={'code':'interrupted','message':'The previous local comparison was interrupted. Run it again.'})
                _write(state)
            else:
                usage+=sum(p.stat().st_size for p in directory.iterdir() if p.is_file());continue
        size=sum(p.stat().st_size for p in directory.iterdir() if p.is_file())
        if time.time()-state['created_epoch']>86400:
            shutil.rmtree(_directory(directory.name))
        else:
            completed.append((state['created_epoch'],directory,size));usage+=size
    completed.sort(key=lambda item:item[0])
    while completed and (len(completed)>=MAX_JOBS or usage+16*1024*1024>MAX_CACHE):
        _,directory,size=completed.pop(0)
        shutil.rmtree(_directory(directory.name));usage-=size
    return usage


def run_job(job_id,body):
    with SERIAL:
        job=read_job(job_id)
        started=time.monotonic()
        def step(stage,progress):
            if time.monotonic()-started>30:
                catalog.fail('comparison_timeout','The bounded local comparison timed out. Choose smaller images.',504)
            job.update(status='running',stage=stage,progress=progress)
            _write(job)
        try:
            step('Validating local images',8)
            before,after=catalog.get_image(body.before_id),catalog.get_image(body.after_id)
            compatible(before,after)
            sar=before['data_type']=='sar_power'
            raw_a,raw_b=catalog.load(before),catalog.load(after)
            step('Aligning images',24)
            (a,va),(b,vb),alignment=align(raw_a,raw_b,sar)
            valid=va&vb
            step('Calculating change indicators',50)
            threshold=body.threshold if body.threshold is not None else (3. if sar else 15.)
            _,magnitude,changed,regions,summary=compare_arrays(a,b,valid,sar,threshold,body.noise_radius,body.min_region_pixels)
            step('Drawing heatmap and regions',70)
            stretch=np.percentile(10*np.log10(np.concatenate([a[valid],b[valid]])),[2,98]) if sar else None
            first=catalog.display(a,valid,sar,stretch);second=catalog.display(b,valid,sar,stretch)
            scale=max(threshold,float(np.percentile(magnitude[valid],99)),1e-5)
            heat=cv2.cvtColor(cv2.applyColorMap(np.uint8(np.clip(magnitude/scale,0,1)*255),cv2.COLORMAP_INFERNO),cv2.COLOR_BGR2RGB)
            heat[~valid]=[12,28,31]
            overlay=second.copy()
            overlay[changed]=(.48*overlay[changed]+.52*np.array([255,110,72])).astype('uint8')
            for region in regions:
                contour=np.array(region['polygon'],np.int32)
                if len(contour)>=3:
                    cv2.polylines(overlay,[contour],True,(255,235,165),1,cv2.LINE_AA)
                    x,y=region['bbox'][:2]
                    cv2.putText(overlay,str(region['id']),(x+3,y+13),cv2.FONT_HERSHEY_SIMPLEX,.38,(255,245,210),1,cv2.LINE_AA)
            directory=_directory(job_id)
            for name,image in [('before',first),('after',second),('heatmap',heat),('overlay',overlay),
                               ('mask',changed.astype('uint8')*255),('valid',valid.astype('uint8')*255)]:
                data=cv2.cvtColor(image,cv2.COLOR_RGB2BGR) if image.ndim==3 else image
                if not cv2.imwrite(str(directory/(name+'.png')),data):
                    raise OSError()
            warnings=['Indicators are not confirmed deforestation, mangrove loss or hectares of forest lost.',
                'Thresholds and registration-confidence categories are heuristic, not validated detection accuracy.',
                'Region outlines show outer pixel boundaries; statistics use the actual mask, including holes.']
            if before['is_simulated']:
                warnings.insert(0,'SIMULATED DATA. Scenario dates are fictional labels, not satellite acquisition dates. No observed environmental change is represented.')
            if sar:
                warnings.append('Power values are compared on a common grid. Tide, incidence, focusing/subswath QA, mangrove masks and ecological validation are not established.')
            else:
                warnings.append('RGB display differences can reflect illumination, compression, rendering or registration. They are visual indicators, not calibrated reflectance or radar measurements.')
            if not alignment['geographic_location_verified']:
                warnings.append('No geographic area measurement: alignment is in image space; locality comes from curated metadata.')
            result={'id':job_id,'before':catalog.public(before),'after':catalog.public(after),'is_simulated':before['is_simulated'],
                'method':'Power ratio in decibels: 10 log10(after/before)' if sar else 'Visual RGB difference: CIE76 distance in CIELAB',
                'scientific_status':'simulated_method_demonstration' if before['is_simulated'] else ('technical_backscatter_comparison_only' if sar else 'visual_change_only'),
                'parameters':{'threshold':threshold,'noise_radius':body.noise_radius,'min_region_pixels':body.min_region_pixels,
                    'filter':'valid-weighted Gaussian' if body.noise_radius else 'none'},
                'alignment':alignment,'summary':summary,'regions':regions,'width':valid.shape[1],'height':valid.shape[0],
                'heatmap_scale_max':scale,'warnings':warnings,'ecological_validation':False,
                'interpretation':('Changed regions indicate synthetic signal differences introduced for a methods demonstration.' if before['is_simulated'] else
                    'Flagged regions are candidate image differences requiring independent sensor, environmental and ecological validation.'),
                'assets':{name:f'/api/image-comparisons/{job_id}/assets/{name}' for name in ASSETS},
                'created_at_utc':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}
            step('Creating PDF report',88)
            from .image_report import make_pdf
            make_pdf(result,directory)
            job.update(status='completed',stage='Report ready',progress=100,result=result,error=None)
        except HTTPException as exc:
            job.update(status='failed',stage='Needs attention',error=exc.detail)
        except Exception:
            job.update(status='failed',stage='Needs attention',error={'code':'comparison_failed','message':'Local comparison could not complete. Check the curated image files and try again.'})
        finally:
            _write(job)


@router.get('/images')
def gallery():
    images=[catalog.public(e) for e in catalog.entries()]
    return {'images':images,'available_dates':sorted({e.get('scenario_date') or e.get('acquisition_date') for e in images if e['available'] and (e.get('scenario_date') or e.get('acquisition_date'))}),
        'notice':'Scenario dates belong only to SIMULATED assets. Real acquisition dates are shown only for real gallery observations.'}


@router.get('/images/{image_id}/preview')
def image_preview(image_id:str):
    return FileResponse(catalog.preview(catalog.get_image(image_id)),media_type='image/png')


@router.post('/image-comparisons',status_code=202)
def submit_images(body:CompareImages,tasks:BackgroundTasks):
    before,after=catalog.get_image(body.before_id),catalog.get_image(body.after_id)
    compatible(before,after)
    with ADMISSION:
        usage=cleanup()
        active=[]
        for path in CACHE.glob('*/state.json'):
            item=_read_state(path)
            if item['status'] in {'queued','running'}:
                active.append(item)
        if len(active)>=2 or usage+16*1024*1024>MAX_CACHE:
            catalog.fail('comparison_busy','The local comparison queue is full. Wait for the current job, then retry.',409)
        job={'id':str(uuid4()),'status':'queued','stage':'Queued locally','progress':0,'created_epoch':time.time(),'result':None,'error':None}
        _write(job)
    tasks.add_task(run_job,job['id'],body)
    return job


@router.get('/image-comparisons/{job_id}')
def comparison_status(job_id:str):
    return read_job(job_id)


@router.get('/image-comparisons/{job_id}/assets/{asset}')
def comparison_asset(job_id:str,asset:str):
    job=read_job(job_id)
    if asset not in ASSETS:
        catalog.fail('asset_not_found','Unknown comparison asset.',404)
    if job['status']!='completed':
        catalog.fail('comparison_not_ready','Images and report are available after a successful comparison.',409)
    path=_directory(job_id)/(asset+('.pdf' if asset=='report' else '.png'))
    if not path.exists():
        catalog.fail('asset_not_found','Comparison asset expired. Run the comparison again.',404)
    return FileResponse(path,media_type='application/pdf' if asset=='report' else 'image/png',
        filename=f'ForestPulse-{job_id}.pdf' if asset=='report' else None,headers={'Cache-Control':'no-store'})
