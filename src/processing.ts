export interface ProcessingSetup {
  real_processing_enabled: boolean; authentication_configured: boolean; state: string;
  candidate_ids: string[]; subset_bbox: number[]; variable: string; second_scene_unlocked: boolean;
  public_deployment?: boolean;
}
export interface ProcessingPlan {
  request_url: string; bbox: number[]; variable: string;
  scene: {id: string; name: string; start_time: string}; analysis_ready: false;
}
export interface ProcessingJob {
  id: string; status: string; progress: number; plan: ProcessingPlan;
  error: {code: string; message: string} | null; raster: Record<string, unknown> | null;
  alignment: Record<string, unknown> | null;
}
export const isProcessingActive = (status: string) => ['queued','submitting','running','paused','downloading','validating','cancel_pending'].includes(status);
export function liveBlockReason(setup?: ProcessingSetup) {
  if (!setup) return 'Checking processing configuration…';
  if (setup.public_deployment) return 'NASA Harmony processing and private job history are disabled on the public deployment. Use the preloaded Image Comparison workflow.';
  if (!setup.authentication_configured) return 'Earthdata authentication required. Configure credentials for the selected server authentication mode in the ignored .env and restart the backend.';
  if (!setup.real_processing_enabled) return 'Real processing is disabled. Set HARMONY_PROCESSING_ENABLED=true on the server to enable a small extraction.';
  return '';
}
