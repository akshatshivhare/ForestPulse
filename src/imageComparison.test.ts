import {describe,it,expect} from 'vitest';
import {dateLabel,imageIssue} from './imageComparison';
import type {GalleryImage} from './imageComparison';

const first:GalleryImage={id:'a',name:'Generated baseline',filename:'a.png',area_id:'illustrative',area:'Illustrative landscape',source:'Procedural generator',sensor:'SIMULATED RGB',data_type:'rgb',units:'display_rgb',is_simulated:true,acquisition_date:null,scenario_date:'2026-01-01',date_kind:'simulated_scenario',pair_group:'pair',available:true,thumbnail_url:null,notice:'SIMULATED'};
const second={...first,id:'b',scenario_date:'2026-02-01'};
describe('curated image selection',()=>{
  it('labels simulated dates as scenarios and real dates as acquisitions',()=>{
    expect(dateLabel(first)).toBe('Scenario · 01 Jan 2026');
    expect(dateLabel({...first,is_simulated:false,acquisition_date:'2026-10-23'})).toBe('Acquired · 23 Oct 2026');
  });
  it('accepts a curated chronological pair',()=>expect(imageIssue(first,second)).toBe(''));
  it('rejects same, missing and unavailable images',()=>{
    expect(imageIssue(first,first)).toContain('different');
    expect(imageIssue(first,undefined)).toContain('Choose');
    expect(imageIssue(first,{...second,available:false})).toContain('unavailable');
  });
  it('rejects real/simulated mixing and unrelated images',()=>{
    expect(imageIssue(first,{...second,is_simulated:false})).toContain('cannot be mixed');
    expect(imageIssue(first,{...second,area_id:'elsewhere'})).toContain('matched pair');
    expect(imageIssue(first,{...second,data_type:'sar_power'})).toContain('matched pair');
  });
  it('rejects reverse chronology and absent observation dates',()=>{
    expect(imageIssue(second,first)).toContain('later');
    expect(imageIssue(first,{...second,scenario_date:null})).toContain('later');
  });
});
