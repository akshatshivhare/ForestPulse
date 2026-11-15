"""Bounded COG inspection and technical grid checks; no disturbance analysis."""
import hashlib
import math
import re
from urllib.parse import unquote, urlsplit

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_bounds
from .spatial import validate_spatial


def inspect_cog(path, plan, asset_url, max_pixels=4_000_000):
    with rasterio.open(path) as ds:
        tiled = bool(ds.profile.get('tiled'))
        if ds.driver != 'GTiff' or not tiled or ds.tags(ns='IMAGE_STRUCTURE').get('LAYOUT') != 'COG':
            raise ValueError('Output is not identified as a Cloud Optimized GeoTIFF.')
        if not ds.crs or ds.count != 1 or ds.width * ds.height > max_pixels:
            raise ValueError('Missing CRS, unexpected band count, or raster exceeds pixel limit.')
        if ds.dtypes != ('float32',):
            raise ValueError('Expected one float32 diagonal GCOV power layer.')
        t = ds.transform
        if not all(math.isfinite(v) for v in t) or t.a <= 0 or t.e >= 0 or t.b or t.d:
            raise ValueError('Unsupported or invalid raster transform.')
        # Do not infer identity from the request alone. Require output evidence.
        name = unquote(urlsplit(asset_url).path)
        tags = ' '.join(str(v) for v in {**ds.tags(), **ds.tags(1)}.values())
        identity = name + ' ' + tags + ' ' + ' '.join(x or '' for x in ds.descriptions)
        variable_evidence = re.search(r'frequencyA[/_:\-]+HHHH(?:\b|_)', identity)
        contradictory = any(x and re.search(r'frequency[A-B][/_:\-]+(HVHV|VVVV|VHVH)', x) for x in ds.descriptions)
        if plan['scene']['name'] not in identity or not variable_evidence or contradictory:
            raise ValueError('Output does not independently identify the source granule and frequencyA/HHHH.')
        bounds = transform_bounds(ds.crs, 'EPSG:4326', *ds.bounds, densify_pts=21)
        readable = finite = positive = masked = 0
        positive_mask = np.zeros(ds.shape,dtype=bool)
        for _, window in ds.block_windows(1):
            data = ds.read(1, window=window, masked=True)
            valid = ~np.ma.getmaskarray(data)
            readable += data.size
            masked += int((~valid).sum())
            finite += int((valid & np.isfinite(data.data)).sum())
            positive += int((valid & np.isfinite(data.data) & (data.data > 0)).sum())
            row,col=int(window.row_off),int(window.col_off)
            positive_mask[row:row+data.shape[0],col:col+data.shape[1]]=valid & np.isfinite(data.data) & (data.data>0)
        if not positive:
            raise ValueError('No readable, finite, unmasked positive radar power pixels.')
        spatial=validate_spatial(ds,plan['bbox'],positive_mask)
        nodata = ds.nodata
        return {'verified': True, 'driver': ds.driver, 'layout': 'COG', 'crs': ds.crs.to_string(),
                'tiled': tiled, 'overviews': ds.overviews(1),
                'bounds': list(ds.bounds), 'bounds_wgs84': list(bounds), 'resolution': list(ds.res),
                'transform': list(t)[:6], 'width': ds.width, 'height': ds.height, 'bands': ds.count,
                'dtypes': list(ds.dtypes), 'nodata': nodata if nodata is None or math.isfinite(nodata) else None,
                'nodata_is_nan': nodata is not None and math.isnan(nodata),
                'mask_flags': [[f.name for f in flags] for flags in ds.mask_flag_enums],
                'readable_pixels': readable, 'finite_unmasked_pixels': finite, 'masked_pixels': masked,
                'positive_power_pixels': positive, 'variable': plan['variable'],
                'spatial_validation':spatial,
                'identity_verified_from_output': True, 'source_granule_id': plan['scene']['id'],
                'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'warnings': ['COG validity masks do not replace the separate GCOV focusing/subswath mask.',
                             'No tide, incidence, mangrove mask, or disturbance validation.'], 'analysis_ready': False}


def check_alignment(first_path, second_path, max_pixels=4_000_000):
    """Actually warp both bounded outputs onto the intersection grid in memory."""
    with rasterio.open(first_path) as a, rasterio.open(second_path) as b:
        bb = transform_bounds(b.crs, a.crs, *b.bounds, densify_pts=21)
        left, bottom = max(a.bounds.left, bb[0]), max(a.bounds.bottom, bb[1])
        right, top = min(a.bounds.right, bb[2]), min(a.bounds.top, bb[3])
        rx, ry = a.res
        left = a.transform.c + math.ceil((left - a.transform.c) / rx) * rx
        top = a.transform.f - math.ceil((a.transform.f - top) / ry) * ry
        width, height = math.floor((right - left) / rx), math.floor((top - bottom) / ry)
        if min(width, height) <= 0 or width * height > max_pixels:
            raise ValueError('No bounded common pixel grid.')
        grid = from_origin(left, top, rx, ry)
        valid = []
        for ds in (a, b):
            source = ds.read(1, masked=True).filled(np.nan)
            out = np.full((height, width), np.nan, dtype='float32')
            reproject(source, out, src_transform=ds.transform, src_crs=ds.crs, src_nodata=np.nan,
                      dst_transform=grid, dst_crs=a.crs, dst_nodata=np.nan, resampling=Resampling.nearest)
            valid.append(np.isfinite(out) & (out > 0))
        shared = int((valid[0] & valid[1]).sum())
        if not shared:
            raise ValueError('No shared valid positive pixels after technical alignment.')
        exact = a.crs == b.crs and a.transform.almost_equals(b.transform) and a.shape == b.shape
        return {'verified': True, 'already_same_grid': exact, 'can_align': True,
                'crs': a.crs.to_string(), 'transform': list(grid)[:6], 'width': width, 'height': height,
                'resolution': [rx, ry], 'shared_valid_pixels': shared,
                'method': 'Nearest-neighbor reprojection to first scene intersection grid; technical check only',
                'analysis_ready': False}
