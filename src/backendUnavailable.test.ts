import {afterEach,describe,it,expect,vi} from 'vitest';

afterEach(()=>{vi.unstubAllEnvs();vi.unstubAllGlobals();vi.resetModules();});

function frontendOnly(){
  vi.stubEnv('PROD',true);
  vi.stubEnv('VITE_API_BASE_URL','');
  vi.resetModules();
}

describe('frontend-only production deployment',()=>{
  it('loads the actual Vercel production build configuration without a backend URL',async()=>{
    vi.stubEnv('VITE_API_BASE_URL','');
    vi.stubEnv('VERCEL','1');
    const {loadConfigFromFile}=await import('vite');
    const result=await loadConfigFromFile({command:'build',mode:'production'},'vite.config.ts');
    expect(result?.config.build?.outDir).toBe('dist');
  });

  it('rejects GET and POST locally without any same-origin or localhost fallback',async()=>{
    frontendOnly();
    const fetch=vi.fn();vi.stubGlobal('fetch',fetch);
    const {api,backendAvailable,assetUrl,apiDocsUrl}=await import('./api');
    expect(backendAvailable).toBe(false);
    for(const path of ['/images','/collections?product=GCOV','/processing/capabilities'])
      await expect(api(path)).rejects.toMatchObject({code:'backend_unavailable'});
    await expect(api('/image-comparisons',{method:'POST',body:'{}'})).rejects.toMatchObject({code:'backend_unavailable'});
    expect(fetch).not.toHaveBeenCalled();
    expect(assetUrl('/api/images/example/preview')).toBeUndefined();
    expect(apiDocsUrl).toBeUndefined();
  });

  it('renders the existing navigation and explicit unavailable gallery without results',async()=>{
    frontendOnly();
    vi.stubGlobal('location',{hash:'#images'});
    const {createElement}=await import('react');
    const {renderToStaticMarkup}=await import('react-dom/server');
    const {default:App}=await import('./App');
    const html=renderToStaticMarkup(createElement(App));
    expect(html).toContain('Backend temporarily unavailable');
    expect(html).toContain('Gallery awaiting backend connection');
    expect(html).toContain('No analysis has been run.');
    expect(html).toContain('Simulated demonstration datasets remain clearly labeled');
    expect(html).toContain('href="#map"');
    expect(html).toContain('href="#comparison"');
    expect(html).not.toContain('Ready for demonstration');
    expect(html).not.toContain('Download detailed PDF');
    expect(html).not.toContain('FLAGGED IMAGE PIXELS');
    expect(html).not.toContain('http://127.0.0.1');
  });

  it('retains configured HTTPS API and asset requests',async()=>{
    vi.stubEnv('PROD',true);vi.stubEnv('VITE_API_BASE_URL','https://backend.example');vi.resetModules();
    const fetch=vi.fn().mockResolvedValue(new Response(JSON.stringify({images:[]}),{headers:{'Content-Type':'application/json'}}));
    vi.stubGlobal('fetch',fetch);
    const {api,assetUrl,backendAvailable}=await import('./api');
    expect(backendAvailable).toBe(true);
    expect(await api('/images')).toEqual({images:[]});
    expect(fetch.mock.calls[0][0]).toBe('https://backend.example/api/images');
    expect(assetUrl('/api/images/example/preview')).toBe('https://backend.example/api/images/example/preview');
  });
});
