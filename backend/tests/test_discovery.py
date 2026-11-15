import copy
import httpx
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import box, Polygon
from backend.app.main import app
from backend.app import cmr
from backend.app.science import coverage, normalize, compare

client = TestClient(app)
BBOX = [88.4, 21.55, 89.1, 22.25]


@pytest.fixture
def item():
    """Synthetic test metadata only. Never shipped as available scenes."""
    attributes = {'PRODUCT_TYPE':['GCOV'], 'PRODUCT_VERSION':['test'], 'FREQUENCIES':['A'], 'FREQUENCY_A_POLARIZATION':['HH','HV'], 'FREQUENCY_A_RANGE_BANDWIDTH':['40'], 'ASCENDING_DESCENDING':['ASCENDING'], 'TRACK_NUMBER':['1'], 'FRAME_NUMBER':['2']}
    return {'meta': {'concept-id':'G1-TEST', 'collection-concept-id':'C1-TEST'}, 'umm': {
        'GranuleUR':'TEST ONLY', 'CollectionReference':{'ShortName':'NISAR_L2_GCOV_TEST_V1','Version':'1'},
        'TemporalExtent':{'RangeDateTime':{'BeginningDateTime':'2026-01-01T12:34:56Z'}},
        'AdditionalAttributes':[{'Name':k,'Values':v} for k,v in attributes.items()],
        'Platforms':[{'ShortName':'NISAR','Instruments':[{'ShortName':'L-SAR','Characteristics':[{'Name':'LookDirection','Value':'LEFT'}]}]}],
        'SpatialExtent':{'HorizontalSpatialDomain':{'Geometry':{'BoundingRectangles':[{'WestBoundingCoordinate':88.4,'SouthBoundingCoordinate':21.55,'EastBoundingCoordinate':89.1,'NorthBoundingCoordinate':22.25}]}}}}}


def test_normalization_uses_acquisition_date_and_metadata(item):
    s = normalize(item, BBOX)
    assert s['date'] == '2026-01-01'
    assert s['frequencies'] == ['A'] and s['polarizations'] == {'A':['HH','HV']}
    assert s['look_direction'] == 'LEFT'
    assert s['incidence_angle'] is None
    assert s['aoi_coverage_percent_approx'] == 100


def test_missing_dates_are_never_invented(item):
    item['umm'].pop('TemporalExtent')
    assert normalize(item, BBOX)['date'] is None


def test_polygon_coverage_is_not_its_bounding_envelope():
    assert coverage(Polygon([(0,0),(2,0),(0,2),(0,0)]), [1.2,1.2,1.8,1.8]) == 0
    assert 49 < coverage(box(0,0,1,1), [0,0,2,1]) < 51
    assert coverage(None, BBOX) is None


def pair(item):
    a = normalize(item, BBOX)
    b = copy.deepcopy(a)
    b['id'] = 'G2-TEST'
    b['date'] = '2026-01-13'
    return a, b


def test_unknown_geometry_metadata_does_not_pass(item):
    a,b = pair(item)
    result = compare(a,b,BBOX)
    assert result['status'] == 'unknown'
    assert result['analysis_ready'] is False
    assert next(c for c in result['checks'] if c['key']=='incidence_angle')['status']=='unknown'
    b['geometry'] = None
    assert compare(a,b,BBOX)['shared_aoi_coverage_percent_approx'] is None


def test_known_mismatches_block_and_dates_must_differ(item):
    a,b = pair(item)
    b['polarizations']={'A':['VV']}
    assert compare(a,b,BBOX)['status']=='incompatible'
    b=copy.deepcopy(a)
    assert compare(a,b,BBOX)['status']=='incompatible'


def test_missing_polarization_is_unknown(item):
    a,b = pair(item)
    b['polarizations']={'A':[]}
    check=next(c for c in compare(a,b,BBOX)['checks'] if c['key']=='polarizations')
    assert check['status']=='unknown'


def test_disjoint_shared_coverage_blocks(item):
    a,b = pair(item)
    b['geometry']={'type':'Polygon','coordinates':[[[80,20],[81,20],[81,21],[80,21],[80,20]]]}
    result=compare(a,b,BBOX)
    assert result['status']=='incompatible' and result['shared_aoi_coverage_percent_approx']==0


@pytest.mark.parametrize('bbox',['1,2,3','89,22,88,23','nan,21,89,22','88,-91,89,22'])
def test_invalid_aoi_returns_422(bbox):
    response=client.get('/api/scenes',params={'collection_id':'C1-TEST','bbox':bbox})
    assert response.status_code==422


def test_processing_never_claims_scientific_readiness():
    response=client.get('/api/processing/capabilities').json()
    assert response['implemented'] is True and response['raw_file_upload_required'] is False
    assert response['analysis_ready'] is False


def test_scene_pagination_does_not_claim_complete_calendar(monkeypatch,item):
    async def validate(_):return {}
    async def request(*args,**kwargs):return {'hits':201,'items':[item]}
    monkeypatch.setattr(cmr,'validate_collection',validate)
    monkeypatch.setattr(cmr,'request',request)
    body=client.get('/api/scenes',params={'collection_id':'C1-TEST','page_size':200}).json()
    assert body['has_more'] is True and body['dates_complete'] is False
    assert body['available_dates']==['2026-01-01']


@pytest.mark.parametrize('upstream_status,expected,code',[(401,401,'authentication_required'),(403,401,'authentication_required'),(429,503,'rate_limited'),(500,502,'upstream_error')])
def test_upstream_errors_are_explicit(monkeypatch,upstream_status,expected,code):
    cmr._cache.clear()
    async def get(self,url,**kwargs):return httpx.Response(upstream_status,request=httpx.Request('GET',url),json={})
    monkeypatch.setattr(httpx.AsyncClient,'get',get)
    response=client.get('/api/collections')
    assert response.status_code==expected
    assert response.json()['detail']['code']==code


def test_unrelated_keyword_matches_are_filtered(monkeypatch):
    async def request(*args,**kwargs):return {'items':[{'meta':{'concept-id':'C1-TEST'},'umm':{'ShortName':'OTHER_MISSION','EntryTitle':'NISAR mentioned in abstract'}}]}
    monkeypatch.setattr(cmr,'request',request)
    assert client.get('/api/collections').json()['collections']==[]


def test_invalid_scene_id_is_rejected_without_upstream_request():
    assert client.get('/api/scenes/not-a-concept').status_code==422


def test_reversed_date_range_is_rejected(monkeypatch):
    async def validate(_):return {}
    monkeypatch.setattr(cmr,'validate_collection',validate)
    assert client.get('/api/scenes?collection_id=C1-TEST&start=2026-02-01&end=2026-01-01').status_code==422
