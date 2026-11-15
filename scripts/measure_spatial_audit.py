"""Offline measurements on the recovered real COG; no HTTP or credentials."""
import json
import math
from pathlib import Path
import numpy as np
import rasterio
from affine import Affine
from pyproj import Geod,Transformer
import shapely
from shapely.geometry import Polygon,box,mapping,shape
from shapely.ops import unary_union
from rasterio.features import shapes

ROOT=Path('artifacts/harmony-spatial-audit')


def main():
    history=json.loads(Path('docs/harmony-first-live-test.json').read_text())
    bbox=history['plan']['bbox']
    w,s,e,n=bbox
    with rasterio.open(ROOT/'first-real-cog.tif') as ds:
        forward=Transformer.from_crs('EPSG:4326',ds.crs,always_xy=True)
        inverse=Transformer.from_crs(ds.crs,'EPSG:4326',always_xy=True)
        def aoi(segments):
            ring=[]
            corners=[(w,s),(e,s),(e,n),(w,n),(w,s)]
            for a,b in zip(corners,corners[1:]):
                ring.extend(zip(np.linspace(a[0],b[0],segments,endpoint=False),np.linspace(a[1],b[1],segments,endpoint=False)))
            return shapely.transform(Polygon(ring),lambda c:np.column_stack(forward.transform(c[:,0],c[:,1])))
        native=aoi(256)
        inv=~ds.transform
        def to_pixels(x,y,z=None):
            return inv.a*np.asarray(x)+inv.b*np.asarray(y)+inv.c,inv.d*np.asarray(x)+inv.e*np.asarray(y)+inv.f
        pixels=shapely.transform(native,lambda c:np.column_stack(to_pixels(c[:,0],c[:,1])))
        coarse=shapely.transform(aoi(128),lambda c:np.column_stack(to_pixels(c[:,0],c[:,1])))
        rr,cc=np.indices(ds.shape)
        inside=shapely.intersects_xy(pixels.buffer(1e-7),cc+.5,rr+.5)
        minx,miny,maxx,maxy=pixels.bounds
        vc,vr=np.meshgrid(np.arange(math.floor(minx)-1,math.ceil(maxx)+1),np.arange(math.floor(miny)-1,math.ceil(maxy)+1))
        expected=shapely.intersects_xy(pixels.buffer(1e-7),vc+.5,vr+.5)
        missing=expected&((vc<0)|(vc>=ds.width)|(vr<0)|(vr>=ds.height))
        missing_points=shapely.points(vc[missing]+.5,vr[missing]+.5)
        missing_depths=shapely.distance(missing_points,pixels.boundary)
        data=ds.read(1,masked=True)
        positive=~np.ma.getmaskarray(data)&np.isfinite(data.data)&(data.data>0)
        px,py=ds.transform.c+ds.transform.a*(cc[positive]+.5),ds.transform.f+ds.transform.e*(rr[positive]+.5)
        lon,lat=inverse.transform(px,py,errcheck=True)
        positive_centers_in_lonlat=int(((lon>=w-1e-10)&(lon<=e+1e-10)&(lat>=s-1e-10)&(lat<=n+1e-10)).sum())
        outside_rows,outside_cols=np.nonzero(positive&~inside)
        boundary_cells=shapely.box(outside_cols,outside_rows,outside_cols+1,outside_rows+1)
        disjoint=int((~shapely.intersects(boundary_cells,pixels.buffer(1e-7))).sum())
        pieces=[shape(g) for g,v in shapes(positive.astype('uint8'),mask=positive,transform=ds.transform) if v==1]
        support=unary_union(pieces)
        outer=box(*ds.bounds)
        corners_native=[ds.transform*p for p in [(0,0),(ds.width,0),(ds.width,ds.height),(0,ds.height)]]
        corners_geo=[list(inverse.transform(*p)) for p in corners_native]
        geo_bounds=list(inverse.transform_bounds(*ds.bounds,densify_pts=21))
        old_tol=max((geo_bounds[2]-geo_bounds[0])/ds.width,(geo_bounds[3]-geo_bounds[1])/ds.height)*3
        geod=Geod(ellps='WGS84')
        meter_errors=[geod.inv(a,(s+n)/2,b,(s+n)/2)[2] for a,b in [(w,geo_bounds[0]),(e,geo_bounds[2])]]
        meter_lat=[geod.inv((w+e)/2,a,(w+e)/2,b)[2] for a,b in [(s,geo_bounds[1]),(n,geo_bounds[3])]]
        tags=' '.join(str(v) for v in {**ds.tags(),**ds.tags(1)}.values())+' '+' '.join(x or '' for x in ds.descriptions)
        result={'requested_bbox_wgs84':bbox,'crs':ds.crs.to_string(),'dimensions':[ds.width,ds.height],
            'affine':list(ds.transform)[:6],'native_bounds':list(ds.bounds),'corners_wgs84_NW_NE_SE_SW':corners_geo,
            'geographic_envelope':geo_bounds,'old_tolerance_degrees':old_tol,
            'edge_difference_m_approx_W_S_E_N':[meter_errors[0],meter_lat[0],meter_errors[1],meter_lat[1]],
            'requested_aoi_projected_bounds':list(native.bounds),'requested_aoi_pixel_bounds':list(pixels.bounds),
            'padding_pixels_left_top_right_bottom':[pixels.bounds[0],pixels.bounds[1],ds.width-pixels.bounds[2],ds.height-pixels.bounds[3]],
            'densification_convergence_pixels':pixels.hausdorff_distance(coarse),'axis_order':'always_xy=True; longitude,latitude',
            'outer_raster_area_native_units_squared':outer.area,'aoi_area_native_units_squared':native.area,
            'outer_intersection_aoi_area_native_units_squared':outer.intersection(native).area,
            'positive_pixel_cell_area_native_units_squared':support.area,
            'valid_cell_intersection_aoi_area_native_units_squared':support.intersection(native).area,
            'valid_cell_outside_aoi_area_native_units_squared':support.difference(native).area,
            'raster_pixels':ds.width*ds.height,'aoi_center_count_in_raster':int(inside.sum()),
            'expected_aoi_center_count_full_grid':int(expected.sum()),'aoi_centers_missing_at_raster_edge':int(missing.sum()),
            'max_missing_center_depth_pixels':float(missing_depths.max()) if missing_depths.size else 0,
            'positive_centers_inside_aoi':int((positive&inside).sum()),'positive_centers_outside_aoi':int((positive&~inside).sum()),
            'positive_cell_count_disjoint_from_aoi':disjoint,'positive_pixels':int(positive.sum()),'valid_footprint_polygon_count':len(pieces),
            'positive_centers_inside_aoi_direct_inverse_lonlat':positive_centers_in_lonlat,
            'positive_center_lonlat_bounds':[float(lon.min()),float(lat.min()),float(lon.max()),float(lat.max())],
            'source_identity_in_tags':history['plan']['scene']['name'] in tags,
            'variable_identity_in_tags':'frequencyA' in tags and 'HHHH' in tags}
        (ROOT/'valid-data-footprint-native.json').write_text(json.dumps({'crs':ds.crs.to_string(),'geometry':mapping(support)}))
        geographic=shapely.transform(shapely.segmentize(support,max_segment_length=min(ds.res)),lambda c:np.column_stack(inverse.transform(c[:,0],c[:,1])))
        (ROOT/'valid-data-footprint-wgs84.geojson').write_text(json.dumps({'type':'Feature','properties':{'positive_cell_count':int(positive.sum())},'geometry':mapping(geographic)}))
        (ROOT/'valid-data-footprint-native.geojson').unlink(missing_ok=True)
        Path('docs/harmony-spatial-measurements.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
        print(json.dumps(result,indent=2,allow_nan=False))


if __name__=='__main__':
    main()
