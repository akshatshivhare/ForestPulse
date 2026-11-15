"""CRS-aware validation of a small requested crop, not registration or science QA.

Work in source pixel coordinates. One-cell window quantization and half-cell
boundary sample loss are allowed; missing interior samples and valid cells wholly
outside the AOI are rejected. No geographic-envelope acceptance tolerance.
"""
import math
import numpy as np
from pyproj import Transformer
import shapely
from shapely.geometry import Polygon,box

NUMERICAL_PIXELS=1e-6
WINDOW_SNAP_PIXELS=1.0
BOUNDARY_CENTER_LOSS_PIXELS=0.5
MAX_PIXELS=4_000_000


class SpatialValidationError(ValueError):
    def __init__(self,code,evidence=None):
        super().__init__('Output failed CRS-aware crop validation.')
        self.code=code
        self.evidence={**(evidence or {}),'verified':False,'failure_category':code}


def _aoi_in_pixels(ds,bbox):
    w,s,e,n=bbox
    if not all(math.isfinite(v) for v in bbox) or not (-180<=w<e<=180 and -90<s<n<90):
        raise SpatialValidationError('invalid_requested_aoi')
    forward=Transformer.from_crs('EPSG:4326',ds.crs,always_xy=True,allow_ballpark=False)
    inv=~ds.transform
    previous=None
    corners=[(w,s),(e,s),(e,n),(w,n),(w,s)]
    for segments in (16,32,64,128,256,512,1024,2048):
        ring=[]
        for a,b in zip(corners,corners[1:]):
            lon=np.linspace(a[0],b[0],segments,endpoint=False)
            lat=np.linspace(a[1],b[1],segments,endpoint=False)
            x,y=forward.transform(lon,lat,errcheck=True)
            col=inv.a*x+inv.b*y+inv.c
            row=inv.d*x+inv.e*y+inv.f
            if not np.isfinite(col).all() or not np.isfinite(row).all():
                raise SpatialValidationError('invalid_crs_transform')
            ring.extend(zip(col,row))
        polygon=Polygon(ring)
        if not polygon.is_valid or polygon.area<=0:
            raise SpatialValidationError('invalid_crs_transform')
        error=polygon.hausdorff_distance(previous) if previous is not None else math.inf
        if error<=NUMERICAL_PIXELS:
            return polygon,segments,error
        previous=polygon
    raise SpatialValidationError('aoi_transform_not_converged')


def _missing_centers(aoi,width,height):
    """Inspect virtual source-grid centers outside the returned raster only."""
    x0,y0,x1,y1=aoi.bounds
    c0,r0=math.floor(x0)-1,math.floor(y0)-1
    c1,r1=math.ceil(x1)+1,math.ceil(y1)+1
    rectangles=[(c0,r0,c1,min(r1,0)),(c0,max(r0,height),c1,r1),
                (c0,max(r0,0),min(c1,0),min(r1,height)),
                (max(c0,width),max(r0,0),c1,min(r1,height))]
    expanded=aoi.buffer(NUMERICAL_PIXELS)
    shapely.prepare(expanded)
    missing=0
    max_depth=0.0
    for left,top,right,bottom in rectangles:
        for row in range(top,bottom,256):
            for col in range(left,right,256):
                xs=np.arange(col,min(col+256,right))+.5
                ys=np.arange(row,min(row+256,bottom))+.5
                hit=shapely.intersects_xy(expanded,xs[None,:],ys[:,None])
                rr,cc=np.nonzero(hit)
                if cc.size:
                    points=shapely.points(xs[cc],ys[rr])
                    depth=shapely.distance(points,aoi.boundary)
                    missing+=int(cc.size)
                    max_depth=max(max_depth,float(depth.max()))
    return missing,max_depth


def validate_spatial(ds,bbox,positive=None):
    """Return auditable crop/valid-cell metrics or raise a fixed safe error.

    A valid cell is GDAL-unmasked, finite and positive power. Its closed cell
    must intersect the AOI. This is not a focusing/subswath or mangrove mask.
    """
    result={'policy':'source-pixel-crop-v1','verified':False,'axis_order':'always_xy=True: longitude,latitude',
            'window_snap_limit_pixels':WINDOW_SNAP_PIXELS,'boundary_center_loss_limit_pixels':BOUNDARY_CENTER_LOSS_PIXELS,
            'numerical_geometry_limit_pixels':NUMERICAL_PIXELS,'requested_bbox_wgs84':list(bbox)}
    def reject(code):
        raise SpatialValidationError(code,result)
    try:
        if not ds.crs or ds.count!=1 or ds.width*ds.height>MAX_PIXELS:
            reject('invalid_spatial_grid')
        t=ds.transform
        if not all(math.isfinite(v) for v in t) or t.a<=0 or t.e>=0 or t.b or t.d:
            reject('invalid_spatial_grid')
        aoi,segments,error=_aoi_in_pixels(ds,bbox)
        left,top,right,bottom=aoi.bounds
        padding=[left,top,ds.width-right,ds.height-bottom]
        result.update(aoi_bounds_pixels=list(aoi.bounds),edge_padding_pixels_left_top_right_bottom=padding,
                      densification_segments_per_edge=segments,densification_error_pixels=error)
        # Both excessive padding and clipping are bounded in source pixels.
        if any(abs(x)>WINDOW_SNAP_PIXELS+NUMERICAL_PIXELS for x in padding):
            reject('grid_extent_mismatch')
        if min(right-left,bottom-top)<=2:
            reject('aoi_too_small_for_spatial_validation')
        raster=box(0,0,ds.width,ds.height)
        if aoi.intersection(raster).area<=0:
            reject('no_aoi_intersection')
        expanded=aoi.buffer(NUMERICAL_PIXELS)
        shapely.prepare(expanded)
        xs=np.arange(ds.width)+.5
        ys=np.arange(ds.height)+.5
        centers=shapely.intersects_xy(expanded,xs[None,:],ys[:,None])
        center_count=int(centers.sum())
        missing,max_depth=_missing_centers(aoi,ds.width,ds.height)
        result.update(aoi_centers_in_raster=center_count,aoi_centers_missing_at_boundary=missing,
            expected_aoi_centers_on_full_source_grid=center_count+missing,max_missing_center_depth_pixels=max_depth,
            raster_aoi_intersection_fraction=float(raster.intersection(aoi).area/aoi.area))
        if max_depth>BOUNDARY_CENTER_LOSS_PIXELS+NUMERICAL_PIXELS:
            reject('missing_interior_aoi_centers')
        if positive is None:
            band=ds.read(1,masked=True)
            positive=~np.ma.getmaskarray(band)&np.isfinite(band.data)&(band.data>0)
        if positive.shape!=ds.shape:
            reject('invalid_valid_data_mask')
        positive_count=int(positive.sum())
        inside=int((positive&centers).sum())
        result.update(positive_valid_pixels=positive_count,positive_centers_inside_aoi=inside,
                      positive_centers_outside_aoi=positive_count-inside)
        if not inside:
            reject('no_positive_valid_pixels_in_aoi')
        # Cells deeper than half their diagonal are wholly inside the AOI.
        # Evaluate exact closed-cell intersections only for boundary candidates.
        deep=aoi.buffer(-math.sqrt(.5)-NUMERICAL_PIXELS)
        deep_centers=shapely.intersects_xy(deep,xs[None,:],ys[:,None])
        interior=int((positive&deep_centers).sum())
        rows,cols=np.nonzero(positive&~deep_centers)
        area_inside=float(interior)
        disjoint=0
        for start in range(0,len(rows),4096):
            rr,cc=rows[start:start+4096],cols[start:start+4096]
            cells=shapely.box(cc,rr,cc+1,rr+1)
            disjoint+=int((~shapely.intersects(cells,expanded)).sum())
            area_inside+=float(shapely.area(shapely.intersection(cells,aoi)).sum())
        area_inside=min(float(positive_count),max(0,area_inside))
        result.update(valid_cells_disjoint_from_aoi=disjoint,valid_data_cell_area_pixels=float(positive_count),
            valid_data_intersection_aoi_area_pixels=area_inside,
            valid_data_outside_aoi_area_pixels=max(0,float(positive_count)-area_inside),
            valid_data_cell_aoi_area_fraction=area_inside/aoi.area,
            positive_center_coverage_of_available_aoi_centers=inside/center_count if center_count else 0,
            positive_center_coverage_of_full_aoi_grid=inside/(center_count+missing) if center_count+missing else 0,
            valid_data_footprint_definition='union of finite positive GDAL-unmasked source pixel cells; not its bounding envelope')
        if disjoint:
            reject('valid_data_outside_aoi')
        result['verified']=True
        return result
    except SpatialValidationError:
        raise
    except Exception:
        raise SpatialValidationError('spatial_transform_or_geometry_failed',result) from None
