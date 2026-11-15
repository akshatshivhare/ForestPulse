import { describe, expect, it } from 'vitest';
import { candidateStatus, displayDate } from './types';
import type { Scene } from './types';
const scene = {id:'G1-TEST',date:'2026-01-01',product:'GCOV',collection_name:'TEST',collection_version:'1',product_version:'1',frequencies:['A'],polarizations:{A:['HH']},bandwidth_mhz:{A:'40'},instruments:['L-SAR'],orbit_direction:'ASCENDING',track:'1',frame:'1',look_direction:'LEFT',geometry:{type:'Polygon',coordinates:[]},aoi_coverage_percent_approx:90,incidence_angle:null} as unknown as Scene;
describe('calendar hints preserve uncertainty',()=>{
  it('marks a real scene available only without a baseline',()=>expect(candidateStatus(scene)).toBe('available'));
  it('rejects same-date acquisitions',()=>expect(candidateStatus(scene,scene)).toBe('incompatible'));
  it('keeps missing incidence angle unknown',()=>expect(candidateStatus({...scene,date:'2026-01-13'},scene)).toBe('unknown'));
  it('blocks known track mismatch',()=>expect(candidateStatus({...scene,date:'2026-01-13',track:'2'},scene)).toBe('incompatible'));
  it('does not synthesize a display date',()=>expect(displayDate(null)).toBe('Not selected'));
});
