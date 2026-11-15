/** Public backend origin only. No credentials, paths or query parameters. */
export function resolveApiBase(value:string|undefined, production=false, hosted=false) {
  const input=(value||'').trim();
  // A missing origin is a supported frontend-only production deployment.
  // The API client must gate requests rather than fall back to this origin.
  if(!input)return '';
  let url:URL;
  try {url=new URL(input);}catch{throw new Error('VITE_API_BASE_URL must be a backend origin, without /api.');}
  const loopback=['localhost','0.0.0.0','[::1]'].includes(url.hostname)||url.hostname.startsWith('127.')||url.hostname.endsWith('.localhost');
  if(url.username||url.password||url.search||url.hash||url.pathname!=='/'||!['http:','https:'].includes(url.protocol)
      ||(production&&url.protocol!=='https:')||((production||hosted)&&loopback))
    throw new Error('VITE_API_BASE_URL must be a public HTTPS origin, without credentials, /api or query parameters.');
  return url.origin;
}
