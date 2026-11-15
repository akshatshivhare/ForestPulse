import {resolveApiBase} from './apiBase';
const BASE=resolveApiBase(import.meta.env.VITE_API_BASE_URL,import.meta.env.PROD);
export const backendAvailable=!import.meta.env.PROD||Boolean(BASE);
export const BACKEND_UNAVAILABLE_TITLE='Backend temporarily unavailable';
export const BACKEND_UNAVAILABLE_MESSAGE='This frontend-only deployment is not connected to the backend. Gallery images, NASA discovery, automatic comparison and PDF reports require that connection. No analysis has been run.';
export const apiDocsUrl=BASE?`${BASE}/docs`:import.meta.env.PROD?undefined:'http://127.0.0.1:8000/docs';
export const assetUrl = (path:string) => backendAvailable?`${BASE}${path}`:undefined;
export class ApiError extends Error { constructor(message: string, public code: string) { super(message); } }
export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  if(!backendAvailable)throw new ApiError(BACKEND_UNAVAILABLE_MESSAGE,'backend_unavailable');
  let response: Response;
  const deadline=AbortSignal.timeout(90000);
  const signal=options?.signal?AbortSignal.any([options.signal,deadline]):deadline;
  try { response = await fetch(`${BASE}/api${path}`, {...options, credentials:'omit', redirect:'error', cache:'no-store', headers: {'Content-Type': 'application/json', ...options?.headers}, signal}); }
  catch (e) {
    if(options?.signal?.aborted)throw e;
    throw new ApiError(signal.aborted?'The service took too long to respond. A sleeping backend may need about a minute to start. Retry after it wakes up.':'Cannot reach the ForestPulse service. It may be starting up; wait a minute and retry. Check the configured API address if this continues.',signal.aborted?'service_timeout':'connection_error');
  }
  let body;
  try { body = await response.json(); } catch {
    if([502,503,504].includes(response.status))throw new ApiError('The backend is waking up or temporarily unavailable. Wait a minute and retry.','service_warming_up');
    throw new ApiError('The API returned an unreadable response. Check the backend address and retry.', 'invalid_response');
  }
  if (!response.ok) { const detail = body?.detail; throw new ApiError(detail&&typeof detail === 'object' && !Array.isArray(detail) ? detail.message || 'The request failed.' : typeof detail === 'string' ? detail : 'The request was rejected. Check the AOI and date range.', detail?.code || (response.status === 401 ? 'authentication_required' : 'request_error')); }
  return body as T;
}
