"""Metadata-only normalization and conservative screening. No raster analysis."""
import re
import numpy as np
from shapely import make_valid, transform
from shapely.geometry import Polygon, box, mapping, shape
from shapely.ops import unary_union


def footprint(umm):
    geometry = umm.get('SpatialExtent', {}).get('HorizontalSpatialDomain', {}).get('Geometry', {})
    polygons = []
    try:
        for polygon in geometry.get('GPolygons', []):
            points = [(p['Longitude'], p['Latitude']) for p in polygon['Boundary']['Points']]
            holes = [[(p['Longitude'], p['Latitude']) for p in ring['Boundary']['Points']]
                     for ring in polygon.get('ExclusiveZone', {}).get('Boundaries', [])]
            polygons.append(make_valid(Polygon(points, holes)))
        # Prefer actual polygons; bounding rectangles are a fallback, never their envelope.
        if not polygons:
            for rect in geometry.get('BoundingRectangles', []):
                west, east = rect['WestBoundingCoordinate'], rect['EastBoundingCoordinate']
                if west > east:  # Dateline-crossing fallback is unsupported, not falsely global.
                    continue
                polygons.append(box(west, rect['SouthBoundingCoordinate'], east, rect['NorthBoundingCoordinate']))
        return unary_union(polygons) if polygons else None
    except (KeyError, ValueError, TypeError):
        return None


def area(geometry):
    """Approximate equal-area cylindrical area; not a validated coverage assessment."""
    return transform(geometry, lambda coords: np.column_stack((np.radians(coords[:, 0]), np.sin(np.radians(coords[:, 1]))))).area


def coverage(geometry, bbox):
    if geometry is None:
        return None
    aoi = box(*bbox)
    return round(100 * area(geometry.intersection(aoi)) / area(aoi), 2)


def normalize(item, bbox):
    u, m = item['umm'], item['meta']
    attrs = {a['Name'].upper(): a.get('Values', []) for a in u.get('AdditionalAttributes', [])}

    def one(*names):
        for name in names:
            values = attrs.get(name)
            if values:
                return values[0]
        return None

    instruments = [i for p in u.get('Platforms', []) for i in p.get('Instruments', [])]
    characteristics = {c['Name'].upper(): c.get('Value') for i in instruments for c in i.get('Characteristics', [])}
    geom = footprint(u)
    temporal = u.get('TemporalExtent', {})
    start = temporal.get('RangeDateTime', {}).get('BeginningDateTime') or temporal.get('SingleDateTime')
    end = temporal.get('RangeDateTime', {}).get('EndingDateTime')
    frequencies = sorted(attrs.get('FREQUENCIES', []))
    polarizations = {f: sorted(attrs.get(f'FREQUENCY_{f}_POLARIZATION', [])) for f in frequencies}
    bandwidth = {f: one(f'FREQUENCY_{f}_RANGE_BANDWIDTH') for f in frequencies}
    reference = u.get('CollectionReference', {})
    short_name = reference.get('ShortName', '')
    # Only collection short name is used as a product fallback, never a filename guess.
    product = one('PRODUCT_TYPE') or next((p for p in ['GCOV', 'GSLC', 'RSLC', 'GUNW', 'GOFF', 'RUNW', 'RIFG', 'ROFF'] if re.search(rf'_{p}_', short_name)), None)
    return {
        'id': m['concept-id'], 'name': u.get('GranuleUR', m['concept-id']),
        'collection_id': m.get('collection-concept-id'), 'collection_name': short_name,
        'collection_version': reference.get('Version'), 'start_time': start, 'end_time': end,
        'date': start[:10] if start else None, 'product': product,
        'product_version': one('PRODUCT_VERSION'), 'frequencies': frequencies,
        'polarizations': polarizations, 'bandwidth_mhz': bandwidth,
        'instruments': sorted(i['ShortName'] for i in instruments if i.get('ShortName')),
        'orbit_direction': one('ASCENDING_DESCENDING', 'ORBIT_DIRECTION'),
        'track': one('TRACK_NUMBER', 'PATH_NUMBER'), 'frame': one('FRAME_NUMBER'),
        'look_direction': one('LOOK_DIRECTION') or characteristics.get('LOOKDIRECTION'),
        'incidence_angle': one('INCIDENCE_ANGLE'),
        'orbit_numbers': [o['OrbitNumber'] for o in u.get('OrbitCalculatedSpatialDomains', []) if 'OrbitNumber' in o],
        'geometry': mapping(geom) if geom is not None else None,
        'footprint_source': 'polygon' if u.get('SpatialExtent', {}).get('HorizontalSpatialDomain', {}).get('Geometry', {}).get('GPolygons') else 'bounding_rectangle_or_unknown',
        'aoi_coverage_percent_approx': coverage(geom, bbox),
        'metadata_url': f"https://cmr.earthdata.nasa.gov/search/concepts/{m['concept-id']}.umm_json",
        'attributes': attrs, 'metadata_revision': m.get('revision-date'),
    }


def compare(a, b, bbox):
    checks = []

    def check(key, label, left, right):
        missing = left is None or right is None or left == [] or right == [] or left == {} or right == {}
        checks.append({'key': key, 'label': label, 'status': 'unknown' if missing else ('compatible' if left == right else 'incompatible'), 'left': left, 'right': right})

    check('distinct_dates', 'Different observation dates', a.get('date'), b.get('date'))
    checks[-1]['status'] = 'unknown' if not a.get('date') or not b.get('date') else ('compatible' if a['date'] != b['date'] else 'incompatible')
    for key, label in [('product', 'Product type'), ('collection_name', 'Collection / maturity'), ('collection_version', 'Collection version'), ('product_version', 'Product version'), ('instruments', 'Radar instrument / band'), ('frequencies', 'Frequency sub-bands'), ('orbit_direction', 'Orbit direction'), ('track', 'Relative track'), ('frame', 'Frame'), ('look_direction', 'Look direction')]:
        check(key, label, a.get(key), b.get(key))
    for key, label in [('polarizations', 'Polarization per frequency'), ('bandwidth_mhz', 'Range bandwidth per frequency')]:
        left, right = a.get(key, {}), b.get(key, {})
        check(key, label, left, right)
        if not a.get('frequencies') or not b.get('frequencies') or any(not v for v in [*left.values(), *right.values()]):
            checks[-1]['status'] = 'unknown'
    overlap = None
    if a.get('geometry') and b.get('geometry'):
        overlap = coverage(shape(a['geometry']).intersection(shape(b['geometry'])), bbox)
    checks.append({'key': 'overlap', 'label': 'Shared coverage within pilot AOI', 'status': 'unknown' if overlap is None else ('compatible' if overlap > 0 else 'incompatible'), 'left': overlap, 'right': 'percent of AOI (approx.)'})
    # Incidence angles are not interchangeable with geometry equality. Surface them as context.
    incidence = {'left': a.get('incidence_angle'), 'right': b.get('incidence_angle'), 'status': 'unknown' if a.get('incidence_angle') is None or b.get('incidence_angle') is None else 'requires_scientific_review'}
    checks.append({'key': 'incidence_angle', 'label': 'Incidence angle', 'status': 'unknown' if incidence['status'] == 'unknown' or incidence['left'] != incidence['right'] else 'compatible', 'left': incidence['left'], 'right': incidence['right']})
    statuses = {c['status'] for c in checks}
    return {'status': 'incompatible' if 'incompatible' in statuses else ('unknown' if 'unknown' in statuses else 'compatible'),
            'checks': checks, 'shared_aoi_coverage_percent_approx': overlap, 'incidence_angle': incidence,
            'analysis_ready': False,
            'notice': 'Metadata screening only. Compatible means candidate metadata match, not scientific readiness. Incidence angle, tides, calibration, co-registration and mangrove masks require Phase 2 validation.'}
