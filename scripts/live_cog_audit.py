"""Bounded local output diagnostics, including invalid/empty COGs. No URLs saved."""
import math
import numpy as np
import rasterio
from rasterio.warp import transform_bounds
from backend.app.rasters import inspect_cog
from backend.app.spatial import SpatialValidationError

KNOWN_FAILURES = {
    'Output is not identified as a Cloud Optimized GeoTIFF.':'invalid_cog_structure',
    'Missing CRS, unexpected band count, or raster exceeds pixel limit.':'invalid_crs_band_or_size',
    'Expected one float32 diagonal GCOV power layer.':'invalid_dtype',
    'Unsupported or invalid raster transform.':'invalid_transform',
    'Output does not independently identify the source granule and frequencyA/HHHH.':'identity_unconfirmed',
    'Output extent does not match the requested small subset within three pixels.':'extent_mismatch',
    'No readable, finite, unmasked positive radar power pixels.':'no_valid_positive_power_pixels',
}


def extent_diagnostics(crs,bounds,width,height,requested_bbox):
    actual=list(transform_bounds(crs,'EPSG:4326',*bounds,densify_pts=21))
    tolerance=max((actual[2]-actual[0])/width,(actual[3]-actual[1])/height)*3
    differences=[abs(a-b) for a,b in zip(actual,requested_bbox)]
    return {'bounds_wgs84':actual,'requested_bbox_wgs84':requested_bbox,
            'existing_extent_tolerance_degrees':tolerance,'absolute_edge_differences_degrees':differences,
            'existing_extent_check_passed':all(x<=tolerance for x in differences)}


def audit_cog(path,plan,asset_url):
    result = {'validation_passed':False,'source_granule_id':plan['scene']['id'],
              'requested_variable':plan['variable'],'statistics':None}
    try:
        with rasterio.open(path) as ds:
            nodata = ds.nodata
            result.update(crs=ds.crs.to_string() if ds.crs else None, width=ds.width,height=ds.height,
                bands=ds.count,dtypes=list(ds.dtypes),bounds=list(ds.bounds),resolution=list(ds.res),
                nodata=nodata if nodata is None or math.isfinite(nodata) else None,
                nodata_is_nan=nodata is not None and math.isnan(nodata),bytes=path.stat().st_size)
            if ds.crs and ds.width and ds.height:
                result.update(extent_diagnostics(ds.crs,ds.bounds,ds.width,ds.height,plan['bbox']))
            if ds.count != 1 or ds.width*ds.height > 4_000_000:
                result['failure_category']='invalid_crs_band_or_size'
                return result
            if ds.dtypes != ('float32',):
                result['failure_category']='invalid_dtype'
                return result
            count=positive=masked=nonfinite=0
            mean=m2=0.0
            minimum,maximum=math.inf,-math.inf
            for _,window in ds.block_windows(1):
                band=ds.read(1,window=window,masked=True)
                masked+=int(np.ma.getmaskarray(band).sum())
                values=band.compressed().astype('float64')
                nonfinite+=int((~np.isfinite(values)).sum())
                values=values[np.isfinite(values)]
                if not values.size:
                    continue
                n=int(values.size)
                block_mean=float(values.mean())
                delta=block_mean-mean
                m2+=float(np.square(values-block_mean).sum())+delta*delta*count*n/(count+n)
                mean+=delta*n/(count+n)
                count+=n
                positive+=int((values>0).sum())
                minimum,maximum=min(minimum,float(values.min())),max(maximum,float(values.max()))
            result.update(finite_unmasked_pixels=count,positive_power_pixels=positive,masked_pixels=masked,
                unmasked_nonfinite_pixels=nonfinite,readable_pixels=ds.width*ds.height)
            result['statistics']={'population':'all finite GDAL-unmasked pixels; no mangrove or GCOV subswath mask applied',
                'units':'linear frequencyA/HHHH power; not dB','count':count,
                'minimum':minimum if count else None,'maximum':maximum if count else None,
                'mean':mean if count else None,'standard_deviation_population':math.sqrt(max(0,m2/count)) if count else None}
        verified=inspect_cog(path,plan,asset_url)
        result.update(validation_passed=True,verified_metadata=verified,radar_variable_identity_verified=True)
    except SpatialValidationError as exc:
        result.update(failure_category='extent_mismatch',spatial_validation=exc.evidence,
            radar_variable_identity_verified=True,identity_verification_basis='Backend identity checks passed before CRS-aware spatial validation.')
    except ValueError as exc:
        result['failure_category']=KNOWN_FAILURES.get(str(exc),'local_raster_validation_failed')
        # These failures occur after source/variable identity has passed.
        result['radar_variable_identity_verified']=result['failure_category'] in {'extent_mismatch','no_valid_positive_power_pixels'}
        if result['radar_variable_identity_verified']:
            result['identity_verification_basis']='Backend inspector passed source/variable identity before reaching the failed extent or pixel check.'
    except Exception:
        result['failure_category']='raster_unreadable_or_validation_failed'
    return result
