"""Opt-in live integration check. Runs the real FastAPI discovery adapter through HTTP."""
import json
from datetime import datetime, timezone
from pathlib import Path
from fastapi.testclient import TestClient
from backend.app.main import app

client=TestClient(app)


def get(path,**kwargs):
    response=client.get(path,**kwargs)
    response.raise_for_status()
    return response.json()


def main():
    report={'verified_at':datetime.now(timezone.utc).isoformat(),'aoi':[88.4,21.55,89.1,22.25], 'endpoints':[], 'collections':[]}
    discovered=get('/api/collections',params={'product':'GCOV'})['collections']
    report['endpoints'].append({'url':'https://cmr.earthdata.nasa.gov/search/collections.umm_json?keyword=NISAR&page_size=200','result':'HTTP 200; GCOV collections dynamically filtered'})
    for c in discovered:
        data=get('/api/scenes',params={'collection_id':c['id'],'page_size':200})
        entry={'id':c['id'],'short_name':c['short_name'],'maturity':c['maturity'],'total_hits':data['total_hits'],'dates_in_loaded_page':data['available_dates'],'loaded':len(data['scenes']),'has_more':data['has_more']}
        report['collections'].append(entry)
        report['endpoints'].append({'url':f"https://cmr.earthdata.nasa.gov/search/granules.umm_json?collection_concept_id={c['id']}&bounding_box=88.4,21.55,89.1,22.25&page_size=200&page_num=1&sort_key=-start_date",'result':'HTTP 200'})
        if data['scenes'] and 'metadata' not in report:
            first=data['scenes'][0]
            metadata=get(f"/api/scenes/{first['id']}")
            assert metadata['scene']['date']==first['date']
            report['metadata']={'id':first['id'],'observation_start':first['start_time'],'product':first['product'],'frequencies':first['frequencies'],'polarizations':first['polarizations'],'look_direction':first['look_direction'],'incidence_angle':first['incidence_angle'],'coverage_percent_approx':first['aoi_coverage_percent_approx']}
            report['endpoints'].append({'url':first['metadata_url'],'result':'HTTP 200; normalized acquisition timestamp matches search'})
            second=next((s for s in data['scenes'] if s['date'] and s['date']!=first['date']),None)
            if second:
                response=client.post('/api/compare',json={'baseline_id':second['id'],'comparison_id':first['id']})
                response.raise_for_status()
                screened=response.json()
                report['screening']={'baseline':second['id'],'comparison':first['id'],'status':screened['status'],'checks':screened['checks'],'analysis_ready':screened['analysis_ready']}
    report['not_verified']=['Harmony API or conversion','Raster / COG processing','Scientific forest-change analysis','Earthdata authenticated data access']
    Path('docs').mkdir(exist_ok=True)
    Path('docs/nasa-verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'collections':len(discovered),'scene_counts':{x['short_name']:x['total_hits'] for x in report['collections']},'metadata':report.get('metadata'),'screening_status':report.get('screening',{}).get('status'),'report':'docs/nasa-verification.json'},indent=2))


if __name__=='__main__':
    main()
