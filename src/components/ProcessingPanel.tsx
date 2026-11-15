import { useEffect, useState } from 'react';
import { api, ApiError } from '../api';
import { isProcessingActive, liveBlockReason } from '../processing';
import type { ProcessingJob, ProcessingPlan, ProcessingSetup } from '../processing';

export default function ProcessingPanel() {
  const [setup,setSetup]=useState<ProcessingSetup>();
  const [scene,setScene]=useState('G4405780437-ASF');
  const [plan,setPlan]=useState<ProcessingPlan>();
  const [job,setJob]=useState<ProcessingJob>();
  const [error,setError]=useState<ApiError>();
  const [busy,setBusy]=useState(false);
  useEffect(()=>{
    const controller=new AbortController();
    api<ProcessingSetup>('/processing/capabilities',{signal:controller.signal})
      .then(async config=>{
        if(controller.signal.aborted)return;
        setSetup(config);
        if(!config.public_deployment){const data=await api<{jobs:ProcessingJob[]}>('/processing/jobs',{signal:controller.signal});if(!controller.signal.aborted)setJob(data.jobs.at(-1));}
      })
      .catch(e=>{if(!controller.signal.aborted)setError(e);});
    return()=>controller.abort();
  },[]);
  useEffect(()=>{
    if(!job||!isProcessingActive(job.status))return;
    const controller=new AbortController();
    const timer=setTimeout(()=>{
      api<ProcessingJob>(`/processing/jobs/${job.id}`,{signal:controller.signal}).then(async next=>{
        if(controller.signal.aborted)return;
        if(next.status==='verified')setSetup(await api<ProcessingSetup>('/processing/capabilities',{signal:controller.signal}));
        setJob(next);
      }).catch(e=>{if(!controller.signal.aborted)setError(e);});
    },3000);
    return()=>{clearTimeout(timer);controller.abort();};
  },[job]);
  async function submit(dryRun:boolean){
    setBusy(true);setError(undefined);
    try{
      const result=await api<ProcessingJob|{status:'dry_run';plan:ProcessingPlan;setup:ProcessingSetup}>('/processing/jobs',{
        method:'POST',body:JSON.stringify({granule_id:scene,dry_run:dryRun}),
      });
      if('setup' in result){setPlan(result.plan);setSetup(result.setup);}else setJob(result);
    }catch(e){setError(e as ApiError);}finally{setBusy(false);}
  }
  async function refreshJob(){
    setError(undefined);
    try{if(job)setJob(await api<ProcessingJob>(`/processing/jobs/${job.id}`));setSetup(await api<ProcessingSetup>('/processing/capabilities'));}
    catch(e){setError(e as ApiError);}
  }
  async function cancel(){
    if(!job)return;setBusy(true);setError(undefined);
    try{setJob(await api<ProcessingJob>(`/processing/jobs/${job.id}/cancel`,{method:'POST'}));}
    catch(e){setError(e as ApiError);}finally{setBusy(false);}
  }
  const blocked=liveBlockReason(setup);
  const active=job&&isProcessingActive(job.status);
  return <section className="panel processing-panel" aria-label="NASA Harmony processing">
    <div className="panel-heading"><div><div className="eyebrow">PHASE 2B · CANDIDATE EXTRACTION</div><h2>Prepare a small radar subset</h2></div><span className="badge amber">NO CHANGE MEASUREMENTS</span></div>
    <p className="panel-copy">Extract one frequency A HH power layer as a COG. These observations remain scientific candidates. The pilot is unchanged; this test uses a small proposed forest-sector subset.</p>
    <p className="fine-print">Subset (west, south, east, north): {setup?.subset_bbox.join(', ')||'88.75, 21.85, 88.78, 21.88'} · WGS84. Variable: frequencyA / HHHH.</p>
    {blocked&&<div className="error-notice" role="status"><div><strong>{setup?.state==='authentication_required'?'Earthdata authentication required':'Processing setup'}</strong><p>{blocked} {!setup?.public_deployment&&'Dry-run validates public metadata without submitting a job.'} Never enter credentials in this browser.</p></div></div>}
    <div className="processing-actions"><label>Candidate observation <select aria-label="Processing candidate" value={scene} disabled={busy||!!active||setup?.public_deployment} onChange={e=>{setScene(e.target.value);setPlan(undefined);}}>
      <option value="G4405780437-ASF">23 Oct 2026 · G4405780437-ASF</option>
      <option value="G4405182121-ASF" disabled={!setup?.second_scene_unlocked}>04 Nov 2026 · G4405182121-ASF (first output required)</option>
    </select></label>
    <button className="button" disabled={busy||!!active||setup?.public_deployment} onClick={()=>submit(true)}>{busy?'Checking…':'Validate dry run'}</button>
    <button className="button primary" disabled={busy||!!active||!!blocked||!plan||plan.scene.id!==scene} onClick={()=>submit(false)}>Submit one real extraction</button></div>
    {!setup?.second_scene_unlocked&&<p className="fine-print">Second-scene processing stays locked until the first candidate passes real COG validation for the same subset.</p>}
    {error&&<div className="error-notice" role="alert"><div><strong>{error.code==='authentication_required'?'Earthdata authentication required':'Processing needs attention'}</strong><p>{error.message}</p></div><button className="button small" onClick={refreshJob}>Refresh status</button></div>}
    {plan&&<details><summary>Validated dry-run request · not submitted</summary><pre>{JSON.stringify(plan,null,2)}</pre></details>}
    {job&&<div className="processing-result" role="status"><strong>{job.status==='verified'?'COG technically verified':job.status.replaceAll('_',' ')} · {job.progress}% NASA processing</strong>
      <p className="mono">{job.plan.scene.id} · {job.id}</p><p>{job.error?.message||'Technical extraction status only. Incidence, tides, masks and disturbance remain unvalidated.'}</p>
      <div className="processing-actions"><button className="button small" onClick={refreshJob}>Refresh status</button>{active&&<button className="button small" disabled={busy||job.status==='cancel_pending'} onClick={cancel}>Cancel extraction</button>}</div>
      {job.raster&&<details open><summary>Verified raster metadata</summary><pre>{JSON.stringify({raster:job.raster,alignment:job.alignment},null,2)}</pre></details>}
    </div>}
  </section>;
}
