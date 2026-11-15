"""Spatial regression fixtures have SYNTHETIC pixels, never observations."""
import math
import numpy as np
import pytest
import rasterio
from affine import Affine
from pyproj import Transformer
import shapely
from shapely.geometry import Polygon
from backend.app.spatial import SpatialValidationError,validate_spatial

BBOX=[88.75,21.85,88.78,21.88]
REAL_GRID=Affine(10,0,680810,0,-10,2420600)


def projected_aoi(t,crs='EPSG:32645'):
    # Fixed high-density geometry supplies fixture masks; no real pixel values.
    w,s,e,n=BBOX
    ring=[]
    corners=[(w,s),(e,s),(e,n),(w,n),(w,s)]
    f=Transformer.from_crs('EPSG:4326',crs,always_xy=True)
    inverse=~t
    for a,b in zip(corners,corners[1:]):
        lon=np.linspace(a[0],b[0],512,endpoint=False)
        lat=np.linspace(a[1],b[1],512,endpoint=False)
        x,y=f.transform(lon,lat)
        c=inverse.a*x+inverse.b*y+inverse.c
        r=inverse.d*x+inverse.e*y+inverse.f
        ring.extend(zip(c,r))
    return Polygon(ring)


def fixture(tmp_path,*,t=REAL_GRID,shape=(334,313),crs='EPSG:32645',mode='aoi',extra_edge=False):
    data=np.full(shape,np.nan,dtype='float32')
    if mode=='aoi':
        polygon=projected_aoi(t,crs)
        inside=shapely.intersects_xy(polygon,np.arange(shape[1])[None,:]+.5,np.arange(shape[0])[:,None]+.5)
        data[inside]=2
        if extra_edge:
            rows,cols=np.nonzero(~inside)
            cells=shapely.box(cols,rows,cols+1,rows+1)
            touched=shapely.intersects(cells,polygon)
            r,c=rows[touched][0],cols[touched][0]
            data[r,c]=2
    elif mode=='full':
        data[:]=2
    elif mode=='zero':
        data[:]=0
    path=tmp_path/'synthetic-spatial.tif'
    with rasterio.open(path,'w',driver='COG',height=shape[0],width=shape[1],count=1,
                       dtype='float32',crs=crs,transform=t,nodata=np.nan) as ds:
        ds.write(data,1)
    return path


def validate(path,bbox=BBOX):
    with rasterio.open(path) as ds:
        return validate_spatial(ds,bbox)


def test_projected_real_grid_geometry_accepts_only_boundary_sample_loss(tmp_path):
    result=validate(fixture(tmp_path))
    assert result['verified']
    assert result['aoi_centers_missing_at_boundary']==82
    assert result['max_missing_center_depth_pixels']<.5
    assert result['positive_centers_inside_aoi']==102933
    assert result['positive_centers_outside_aoi']==0
    assert result['valid_cells_disjoint_from_aoi']==0
    assert 0.999<result['positive_center_coverage_of_full_aoi_grid']<1


def test_projected_grid_outer_padding_is_not_wrong_area(tmp_path):
    padded=Affine(10,0,680800,0,-10,2420610)
    result=validate(fixture(tmp_path,t=padded,shape=(336,315)))
    assert result['verified'] and result['aoi_centers_missing_at_boundary']==0
    assert result['positive_valid_pixels']==103015


def test_partial_edge_cell_may_touch_aoi_without_center_inside(tmp_path):
    result=validate(fixture(tmp_path,extra_edge=True))
    assert result['verified'] and result['positive_centers_outside_aoi']==1
    assert result['valid_cells_disjoint_from_aoi']==0


@pytest.mark.parametrize('t,crs',[(Affine(10,0,681810,0,-10,2420600),'EPSG:32645'),
                                (REAL_GRID,'EPSG:32646'),(REAL_GRID,'EPSG:4326')])
def test_displaced_or_wrong_crs_outputs_rejected(tmp_path,t,crs):
    with pytest.raises(SpatialValidationError):
        validate(fixture(tmp_path,t=t,crs=crs,mode='full'))


@pytest.mark.parametrize('mode',['empty','zero'])
def test_empty_or_no_positive_power_rejected(tmp_path,mode):
    with pytest.raises(SpatialValidationError) as exc:
        validate(fixture(tmp_path,mode=mode))
    assert exc.value.code=='no_positive_valid_pixels_in_aoi'


def test_full_bbox_with_disjoint_valid_corners_rejected(tmp_path):
    with pytest.raises(SpatialValidationError) as exc:
        validate(fixture(tmp_path,mode='full'))
    assert exc.value.code=='valid_data_outside_aoi'
    assert exc.value.evidence['valid_cells_disjoint_from_aoi']>0


def test_one_pixel_snap_bound_is_explicit_not_a_degree_tolerance(tmp_path):
    dx=(BBOX[2]-BBOX[0])/100
    dy=(BBOX[3]-BBOX[1])/100
    exact=Affine(dx,0,BBOX[0],0,-dy,BBOX[3])
    assert validate(fixture(tmp_path,t=exact,shape=(100,101),crs='EPSG:4326'))['verified']
    beyond=Affine(dx,0,BBOX[0]-dx*1.0001,0,-dy,BBOX[3])
    with pytest.raises(SpatialValidationError) as exc:
        validate(fixture(tmp_path,t=beyond,shape=(100,100),crs='EPSG:4326'))
    assert exc.value.code=='grid_extent_mismatch'


def test_genuine_edge_loss_and_oversized_outputs_rejected(tmp_path):
    for t,shape in [(Affine(10,0,680830,0,-10,2420600),(334,311)),
                    (Affine(10,0,680710,0,-10,2420700),(354,333))]:
        with pytest.raises(SpatialValidationError) as exc:
            validate(fixture(tmp_path,t=t,shape=shape))
        assert exc.value.code=='grid_extent_mismatch'


def test_axis_order_is_longitude_latitude_even_for_epsg4326(tmp_path):
    path=fixture(tmp_path)
    assert validate(path)['axis_order'].startswith('always_xy=True')
    with pytest.raises(SpatialValidationError):
        validate(path,[21.85,88.75,21.88,88.78])


def test_missing_crs_and_non_affine_grid_rejected(tmp_path):
    for t,crs in [(REAL_GRID,None),(Affine(10,1,680810,0,-10,2420600),'EPSG:32645')]:
        with pytest.raises(SpatialValidationError) as exc:
            validate(fixture(tmp_path,t=t,crs=crs,mode='full'))
        assert exc.value.code=='invalid_spatial_grid'
