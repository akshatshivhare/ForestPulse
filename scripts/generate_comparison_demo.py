"""Deterministic SIMULATED fixtures, not satellite imagery or observation dates."""
import json
from pathlib import Path
import cv2
import numpy as np
import rasterio
from rasterio.transform import from_bounds

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'datasets/sundarbans-simulated-v1'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    rng=np.random.default_rng(20261115)
    h,w=384,512
    yy,xx=np.indices((h,w))
    texture=cv2.GaussianBlur(rng.normal(0,1,(h,w)).astype('float32'),(0,0),1.1)
    canopy=np.stack([43+texture*23,96+texture*32,65+texture*25],axis=2)
    water=(np.abs(xx-(235+42*np.sin(yy/53)))<26)|(np.abs(yy-(155+35*np.sin(xx/83)))<13)
    canopy[water]=np.stack([25+texture[water]*9,63+texture[water]*13,73+texture[water]*14],axis=1)
    before=np.clip(canopy,0,255).astype('uint8')
    # Small deterministic spatial texture gives reproducible image features.
    for _ in range(1700):
        x,y=int(rng.integers(8,w-8)),int(rng.integers(8,h-8))
        color=tuple(int(v) for v in (rng.integers(28,88),rng.integers(75,155),rng.integers(42,100)))
        cv2.circle(before,(x,y),int(rng.integers(1,4)),color,-1,cv2.LINE_AA)
    after=before.copy()
    cv2.ellipse(after,(126,117),(40,30),-24,0,360,(154,133,86),-1)
    cv2.ellipse(after,(362,270),(35,22),15,0,360,(37,116,80),-1)
    cv2.rectangle(after,(385,75),(437,107),(155,150,109),-1)
    alpha=np.full((h,w),255,np.uint8)
    alpha[:6]=0;alpha[-6:]=0;alpha[:,:6]=0;alpha[:,-6:]=0
    for name,rgb,mask in [('rgb-before',before,alpha),('rgb-after',after,alpha)]:
        if name.endswith('after'):
            matrix=np.float32([[1,0,5],[0,1,-3]])
            rgb=cv2.warpAffine(rgb,matrix,(w,h),flags=cv2.INTER_LINEAR,borderValue=0)
            mask=cv2.warpAffine(mask,matrix,(w,h),flags=cv2.INTER_NEAREST,borderValue=0)
        cv2.imwrite(str(OUT/(name+'.png')),cv2.cvtColor(np.dstack([rgb,mask]),cv2.COLOR_RGBA2BGRA))
    base=np.exp(-2.2+cv2.GaussianBlur(rng.normal(0,.7,(h,w)).astype('float32'),(0,0),1.2)).astype('float32')
    base[water]*=.22
    later=base*np.exp(rng.normal(0,.06,(h,w))).astype('float32')
    drop=((xx-125)/40)**2+((yy-117)/30)**2<1
    rise=((xx-365)/35)**2+((yy-270)/22)**2<1
    later[drop]*=10**(-5/10)
    later[rise]*=10**(4/10)
    transform=from_bounds(680810,2417260,683940,2420600,w,h)
    for name,data in [('sar-before',base),('sar-after',later)]:
        data=data.copy();data[alpha==0]=np.nan
        with rasterio.open(OUT/(name+'.tif'),'w',driver='GTiff',height=h,width=w,count=1,dtype='float32',
            crs='EPSG:32645',transform=transform,nodata=np.nan,compress='deflate') as ds:
            ds.write(data,1)
            ds.set_band_description(1,'SIMULATED gamma0-like power; NOT NISAR')
    records=[]
    for kind in ('rgb','sar'):
        for index,stage in enumerate(('before','after')):
            radar=kind=='sar'
            records.append({'id':f'sim-{kind}-{stage}','name':f'Simulated {"radar power" if radar else "optical delta"} · {"baseline" if index==0 else "follow-up"}',
                'file':f'datasets/sundarbans-simulated-v1/{kind}-{stage}.{"tif" if radar else "png"}',
                'area_id':f'sundarbans-simulated-{kind}-v1','area':'Sundarbans-inspired illustrative tile; not a real observed landscape',
                'source':'ForestPulse deterministic procedural simulation v1 (seed 20261115)',
                'sensor':'SIMULATED radar' if radar else 'SIMULATED RGB camera',
                'data_type':'sar_power' if radar else 'rgb','units':'gamma0_linear_power' if radar else 'display_rgb',
                'is_simulated':True,'acquisition_date':None,'scenario_date':'2026-01-01' if index==0 else '2026-02-01',
                'date_kind':'simulated_scenario','pair_group':f'sim-{kind}-v1','frequency':'A' if radar else None,
                'polarization':'HH' if radar else None,'calibration':'synthetic_power' if radar else 'uncalibrated_display_rgb',
                'provenance':{'generator':'scripts/generate_comparison_demo.py','seed':20261115},
                'notice':'SIMULATED. Scenario dates are labels, not satellite acquisition dates. No real forest-change evidence.'})
    records.append({'id':'nisar-20261023-hhhh','name':'NISAR frequency A HH power · 23 Oct 2026',
        'file':'artifacts/harmony-spatial-audit/first-real-cog.tif','area_id':'sundarbans-pilot-test-sector',
        'area':'Sundarbans test sector [88.75, 21.85, 88.78, 21.88]',
        'source':'NASA NISAR / ASF; G4405780437-ASF','sensor':'NISAR L-SAR','data_type':'sar_power',
        'units':'linear_HHHH_power','is_simulated':False,'acquisition_date':'2026-10-23',
        'scenario_date':None,'date_kind':'satellite_acquisition','pair_group':'nisar-track170-frame13-frequencyA-HH',
        'frequency':'A','polarization':'HH','calibration':'normalization_not_independently_verified',
        'provenance':{'granule_id':'G4405780437-ASF','acquisition_start_utc':'2026-10-23T23:29:18.000000Z',
            'collection':'C3622241360-ASF','variable':'/science/LSAR/GCOV/grids/frequencyA/HHHH',
            'sha256':'f9f232f2743c2839835d59726456a7d2eaa3bf7c04188d5a2d5d87cfd650df5d'},
        'notice':'REAL observation, spatially validated. No matched second real COG is preloaded. Science QA, tides and comparison remain unverified.'})
    (ROOT/'datasets/catalog.json').write_text(json.dumps({'schema_version':1,'images':records},indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('Prepared 4 SIMULATED assets; catalog references the one existing real COG without copying or inventing a second observation.')


if __name__=='__main__':
    main()
