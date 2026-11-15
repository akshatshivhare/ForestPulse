r"""Read-only public metadata audit; no credentials, data downloads, or Harmony jobs.

Run from the workspace root: .venv\Scripts\python.exe -m scripts.audit_sundarbans
Evidence is intentionally separate from the original Phase 1 verification.
"""
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

import httpx
from shapely.geometry import box, shape

from backend.app.science import compare, coverage, normalize

ROOT = Path('docs/sundarbans-evidence')
CMR = 'https://cmr.earthdata.nasa.gov/search'
AOIS = {
    'existing_pilot': [88.4, 21.55, 89.1, 22.25],
    'central_forest_proposal': [88.65, 21.7, 88.9, 21.95],
    'sajnekhali_sector_proposal': [88.75, 22.05, 88.9, 22.2],
    'lothian_sector_proposal': [88.28, 21.62, 88.4, 21.75],
}
SEARCH_BBOX = [88.15, 21.45, 89.2, 22.5]


async def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    manifest = []
    semaphore = asyncio.Semaphore(3)
    async with httpx.AsyncClient(timeout=60, follow_redirects=False,
                                 headers={'Client-Id': 'ForestPulse-Feasibility-Audit'}) as client:
        async def fetch(name, url, params=None, required=True):
            async with semaphore:
                response = await client.get(url, params=params)
            stamp = datetime.now(timezone.utc).isoformat()
            path = ROOT / (name + '.json')
            try:
                data = response.json()
            except ValueError:
                data = {'response_text': response.text}
            payload = json.dumps(data, indent=2, ensure_ascii=False).encode('utf-8') + b'\n'
            path.write_bytes(payload)
            manifest.append({'file': path.name, 'url': str(response.request.url),
                             'retrieved_at_utc': stamp, 'status': response.status_code,
                             'content_type': response.headers.get('Content-Type'),
                             'cmr_hits_header': response.headers.get('CMR-Hits'),
                             'sha256': hashlib.sha256(payload).hexdigest()})
            (ROOT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
            print(name, response.status_code, flush=True)
            if required:
                response.raise_for_status()
            return data

        catalog = await fetch('collections', CMR + '/collections.umm_json',
                              {'keyword': 'NISAR', 'page_size': 200})
        collections = [x for x in catalog.get('items', [])
                       if x['umm'].get('ShortName', '').startswith('NISAR_')
                       and '_GCOV_' in x['umm']['ShortName']]
        summary = {'aois': AOIS, 'search_bbox': SEARCH_BBOX, 'collections': [], 'groups': []}
        for collection in collections:
            cid = collection['meta']['concept-id']
            all_items = []
            page = 1
            while True:
                raw = await fetch(cid + '-regional-' + str(page), CMR + '/granules.umm_json',
                                  {'collection_concept_id': cid, 'bounding_box': ','.join(map(str, SEARCH_BBOX)),
                                   'page_size': 200, 'page_num': page, 'sort_key': '-start_date'})
                all_items.extend(raw.get('items', []))
                if len(all_items) >= raw.get('hits', 0) or not raw.get('items'):
                    break
                page += 1
            pilot = await fetch(cid + '-pilot', CMR + '/granules.umm_json',
                                {'collection_concept_id': cid,
                                 'bounding_box': ','.join(map(str, AOIS['existing_pilot'])),
                                 'page_size': 200, 'page_num': 1, 'sort_key': '-start_date'})
            # Collection associations identify services and variables. Neither
            # service nor variable search accepts collection_concept_id.
            associations = collection['meta'].get('associations', {})
            await fetch(cid + '-capabilities', 'https://harmony.earthdata.nasa.gov/capabilities', {'collectionId': cid})
            for kind in ['variables', 'services']:
                ids = associations.get(kind, [])
                if ids:
                    await fetch(cid + '-' + kind, CMR + '/' + kind + '.umm_json',
                                [('concept_id[]', value) for value in ids] + [('page_size', '200')])
            if cid == 'C3622241360-ASF':
                for gid in ['G4405780437-ASF', 'G4405182121-ASF', 'G4404467079-ASF', 'G4409021162-ASF']:
                    record = await fetch(gid, CMR + '/concepts/' + gid + '.umm_json')
                    if gid in ['G4405780437-ASF', 'G4405182121-ASF']:
                        umm = record.get('umm', record)
                        for label, suffix in [('iso-metadata', '.iso.xml'), ('qa-summary', 'QA_SUMMARY.csv')]:
                            url = next((u['URL'] for u in umm.get('RelatedUrls', [])
                                        if u['URL'].startswith('https://nisar.asf.earthdatacloud.nasa.gov/NISAR/')
                                        and u['URL'].endswith(suffix)), None)
                            if url:
                                await fetch(gid + '-' + label, url, required=False)
            scenes = [normalize(x, AOIS['existing_pilot']) for x in all_items]
            (ROOT / (cid + '-normalized.json')).write_text(json.dumps(scenes, indent=2) + '\n', encoding='utf-8')
            summary['collections'].append({'id': cid, 'short_name': collection['umm']['ShortName'],
                                           'regional_hits': raw.get('hits'), 'regional_loaded': len(scenes),
                                           'pilot_hits': pilot.get('hits'),
                                           'aoi_intersection_counts': {name: sum(s['geometry'] is not None and shape(s['geometry']).intersects(box(*bbox)) for s in scenes) for name, bbox in AOIS.items()}})
            fields = ['collection_name', 'collection_version', 'product_version', 'instruments',
                      'frequencies', 'polarizations', 'bandwidth_mhz', 'orbit_direction', 'track', 'frame', 'look_direction']
            groups = {}
            for scene in scenes:
                key = json.dumps({k: scene[k] for k in fields}, sort_keys=True)
                groups.setdefault(key, []).append(scene)
            for key, members in groups.items():
                members.sort(key=lambda s: s['start_time'] or '')
                pairs = []
                for a, b in combinations(members, 2):
                    if not a['date'] or a['date'] == b['date']:
                        continue
                    result = compare(a, b, AOIS['existing_pilot'])
                    intersection = shape(a['geometry']).intersection(shape(b['geometry'])) if a['geometry'] and b['geometry'] else None
                    pairs.append({'baseline_id': a['id'], 'comparison_id': b['id'],
                                  'baseline_start': a['start_time'], 'comparison_start': b['start_time'],
                                  'status': result['status'],
                                  'unresolved_checks': [c for c in result['checks'] if c['status'] != 'compatible'],
                                  'shared_coverage_percent': {name: coverage(intersection, bbox) for name, bbox in AOIS.items()}})
                summary['groups'].append({'collection': cid, 'metadata': json.loads(key),
                                          'members': [{'id': s['id'], 'start': s['start_time']} for s in members], 'pairs': pairs})
        summary['note'] = 'AOIs other than existing_pilot are audit proposals; application selection is unchanged. Coverage is metadata polygon area, not valid mangrove pixels.'
        (ROOT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
        (ROOT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(summary['collections'], indent=2))


if __name__ == '__main__':
    asyncio.run(main())
