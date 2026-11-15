export type Status = 'compatible' | 'incompatible' | 'unknown';
export interface Collection { id: string; short_name: string; title: string; version: string; provider: string; maturity: string; metadata_url: string }
export interface Scene {
  id: string; name: string; collection_id: string; collection_name: string; collection_version: string | null;
  start_time: string | null; end_time: string | null; date: string | null; product: string | null; product_version: string | null;
  frequencies: string[]; polarizations: Record<string, string[]>; bandwidth_mhz: Record<string, string | null>; instruments: string[];
  orbit_direction: string | null; track: string | null; frame: string | null; look_direction: string | null;
  incidence_angle: string | null; orbit_numbers: number[]; geometry: GeoJSON.Geometry | null;
  aoi_coverage_percent_approx: number | null; metadata_url: string; footprint_source: string;
}
export interface Discovery { scenes: Scene[]; available_dates: string[]; total_hits: number; page: number; has_more: boolean; dates_complete: boolean; retrieved_at: string; bbox: number[] }
export interface Comparison { status: Status; checks: { key: string; label: string; status: Status; left: unknown; right: unknown }[]; shared_aoi_coverage_percent_approx: number | null; incidence_angle: {status:string}; notice: string; analysis_ready: false }
export const PILOT = [88.4, 21.55, 89.1, 22.25];
export const displayDate = (value: string | null) => value ? new Date(value.slice(0, 10) + 'T12:00:00Z').toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' }) : 'Not selected';
export const isoDate = (date: Date) => date.toISOString().slice(0, 10);

// Calendar hints are conservative metadata previews; authoritative screening uses /api/compare.
export function candidateStatus(scene: Scene, baseline?: Scene): 'available' | 'candidate' | 'unknown' | 'incompatible' {
  if (!baseline) return 'available';
  if (scene.date === baseline.date) return 'incompatible';
  const keys = ['product', 'collection_name', 'collection_version', 'product_version', 'instruments', 'frequencies', 'polarizations', 'bandwidth_mhz', 'orbit_direction', 'track', 'frame', 'look_direction'] as const;
  let unknown = !scene.geometry || !baseline.geometry || !scene.incidence_angle || !baseline.incidence_angle || scene.incidence_angle !== baseline.incidence_angle;
  for (const key of keys) {
    const a = scene[key], b = baseline[key];
    if (a == null || b == null || (Array.isArray(a) && !a.length) || (Array.isArray(b) && !b.length)) unknown = true;
    else if (typeof a === 'object' && !Array.isArray(a) && (Object.values(a).some(v => v == null || (Array.isArray(v) && !v.length)) || Object.values(b).some(v => v == null || (Array.isArray(v) && !v.length)))) unknown = true;
    else if (JSON.stringify(a) !== JSON.stringify(b)) return 'incompatible';
  }
  if (scene.aoi_coverage_percent_approx === 0 || baseline.aoi_coverage_percent_approx === 0) return 'incompatible';
  return unknown ? 'unknown' : 'candidate';
}
