export interface GalleryImage {
  id:string; name:string; filename:string; area_id:string; area:string; source:string; sensor:string;
  data_type:'rgb'|'sar_power'; units:string; is_simulated:boolean; acquisition_date:string|null;
  scenario_date:string|null; date_kind:string; pair_group:string; available:boolean; thumbnail_url:string|null; notice:string;
}
export interface ImageRegion {id:number;pixels:number;bbox:number[];polygon:number[][];mean_indicator_magnitude:number;direction:string}
export interface ImageResult {
  id:string;before:GalleryImage;after:GalleryImage;is_simulated:boolean;method:string;scientific_status:string;
  parameters:{threshold:number;noise_radius:number;min_region_pixels:number;filter:string};
  alignment:{method:string;confidence:string;confidence_note:string;crs:string|null;resolution?:number[];matches?:number;inliers?:number;inlier_ratio?:number;reprojection_rmse_pixels?:number;geographic_note?:string};
  summary:{valid_pixels:number;invalid_or_nonoverlap_pixels:number;changed_pixels:number;changed_percent_of_valid:number;region_count:number;regions_displayed:number;indicator_units:string;mean_absolute_difference:number;p95_absolute_difference:number;mean_signed_difference_db:number|null};
  regions:ImageRegion[];width:number;height:number;heatmap_scale_max:number;warnings:string[];interpretation:string;
  assets:Record<'before'|'after'|'heatmap'|'overlay'|'mask'|'valid'|'report',string>;
}
export interface ImageJob {id:string;status:'queued'|'running'|'completed'|'failed';stage:string;progress:number;result:ImageResult|null;error:{code:string;message:string}|null}
export function dateLabel(image:GalleryImage) {
  const value=image.is_simulated?image.scenario_date:image.acquisition_date;
  const label=value?new Date(value+'T00:00:00Z').toLocaleDateString('en-GB',{day:'2-digit',month:'short',year:'numeric',timeZone:'UTC'}):'Date unavailable';
  return `${image.is_simulated?'Scenario':'Acquired'} · ${label}`;
}
export function imageIssue(a?:GalleryImage,b?:GalleryImage) {
  if (!a||!b) return 'Choose two available gallery images.';
  if (!a.available||!b.available) return 'One of these local images is unavailable.';
  if (a.id===b.id) return 'Choose two different images.';
  if (a.is_simulated!==b.is_simulated) return 'Real observations and simulated images cannot be mixed.';
  if (a.area_id!==b.area_id||a.pair_group!==b.pair_group||a.sensor!==b.sensor||a.data_type!==b.data_type) return 'Choose a matched pair with the same area, sensor and data type.';
  const da=a.is_simulated?a.scenario_date:a.acquisition_date,db=b.is_simulated?b.scenario_date:b.acquisition_date;
  if (!da||!db||da>=db) return 'The follow-up must have a later available date than the baseline.';
  return '';
}
