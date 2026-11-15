/** Public backend origin only. No credentials, paths or query parameters. */
export function resolveApiBase(value:string|undefined, production=false, hosted=false) {
  const input=(value||'').trim();
  if(!input){
    if(production)throw new Error('Set VITE_API_BASE_URL to the Render HTTPS origin before building.');
    return '';
  }
  let url:URL;
  try {url=new URL(input);}catch{throw new Error('VITE_API_BASE_URL must be a backend origin, without /api.');}
  const loopback=['localhost','127.0.0.1','[::1]'].includes(url.hostname);
  if(url.username||url.password||url.search||url.hash||url.pathname!=='/'||!['http:','https:'].includes(url.protocol)
      ||(production&&url.protocol!=='https:'&&!loopback)||(hosted&&loopback))
    throw new Error('VITE_API_BASE_URL must be a public HTTPS origin, without credentials, /api or query parameters.');
  return url.origin;
}
