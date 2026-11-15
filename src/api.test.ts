import {afterEach,describe,it,expect,vi} from 'vitest';
import {resolveApiBase} from './apiBase';
import {api,assetUrl} from './api';

afterEach(()=>vi.unstubAllGlobals());
describe('production API configuration',()=>{
  it('normalizes an HTTPS origin and keeps dev proxy support',()=>{
    expect(resolveApiBase(' https://forestpulse-api.example/ ',true)).toBe('https://forestpulse-api.example');
    expect(resolveApiBase('',false)).toBe('');
    expect(assetUrl('/api/images/example/preview')).toContain('/api/images/example/preview');
  });
  it('allows a missing production origin for a frontend-only build',()=>{
    expect(resolveApiBase(undefined,true,true)).toBe('');
    expect(resolveApiBase('',true,true)).toBe('');
    expect(resolveApiBase('  ',true,true)).toBe('');
  });
  it.each(['not a url','https://host.example/api','https://user:secret@host.example','http://public.example','https://host.example?token=secret'])('rejects unsafe production configuration',value=>{
    expect(()=>resolveApiBase(value,true)).toThrow();
  });
  it('allows local development, rejects local addresses in production',()=>{
    expect(resolveApiBase('http://127.0.0.1:8010',false)).toBe('http://127.0.0.1:8010');
    expect(()=>resolveApiBase('http://127.0.0.1:8010',true,true)).toThrow();
    expect(()=>resolveApiBase('https://localhost',true)).toThrow();
    expect(()=>resolveApiBase('https://127.0.0.2',true)).toThrow();
    expect(()=>resolveApiBase('https://[::1]',true)).toThrow();
  });
  it('does not retry submissions or send browser credentials',async()=>{
    const fetch=vi.fn().mockResolvedValue(new Response(JSON.stringify({id:'local-job'}),{status:202,headers:{'Content-Type':'application/json'}}));
    vi.stubGlobal('fetch',fetch);
    expect(await api('/image-comparisons',{method:'POST',body:'{}'})).toEqual({id:'local-job'});
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][1]).toMatchObject({credentials:'omit',redirect:'error',cache:'no-store'});
  });
  it('explains a cold-start HTML response without displaying its body',async()=>{
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('SENSITIVE-UPSTREAM-TEXT',{status:503})));
    await expect(api('/images')).rejects.toMatchObject({code:'service_warming_up'});
  });
  it('handles network errors and ephemeral-file errors clearly',async()=>{
    vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new Error('SENSITIVE-UPSTREAM-TEXT')));
    await expect(api('/images')).rejects.toMatchObject({code:'connection_error'});
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({detail:{code:'comparison_not_found',message:'Comparison expired; run again.'}}),{status:404})));
    await expect(api('/image-comparisons/missing')).rejects.toMatchObject({code:'comparison_not_found',message:'Comparison expired; run again.'});
  });
});
