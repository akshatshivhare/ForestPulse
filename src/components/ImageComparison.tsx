import {useEffect,useRef,useState} from 'react';
import {ArrowDownToLine,ArrowLeftRight,Check,ChevronRight,Images,Layers,LoaderCircle,MapPin,Maximize2,Play,ScanLine,ShieldCheck,SlidersHorizontal,TriangleAlert} from 'lucide-react';
import {api,assetUrl,ApiError} from '../api';
import {dateLabel,imageIssue} from '../imageComparison';
import type {GalleryImage,ImageJob,ImageResult} from '../imageComparison';
import './image-comparison.css';

export default function ImageComparison(){
  const [images,setImages]=useState<GalleryImage[]>([]);
  const [loading,setLoading]=useState(true),[error,setError]=useState<string>();
  const [beforeId,setBefore]=useState(''),[afterId,setAfter]=useState('');
  const [job,setJob]=useState<ImageJob>(),[result,setResult]=useState<ImageResult>();
  const [submitting,setSubmitting]=useState(false),[view,setView]=useState('swipe'),[divider,setDivider]=useState(50);
  const [rgbThreshold,setRgbThreshold]=useState(15),[sarThreshold,setSarThreshold]=useState(3);
  const [noise,setNoise]=useState(1),[minimum,setMinimum]=useState(64),[selectedRegion,setRegion]=useState<number>();
  const auto=useRef(false);
  const before=images.find(x=>x.id===beforeId),after=images.find(x=>x.id===afterId);
  const sar=before?.data_type==='sar_power';
  const threshold=sar?sarThreshold:rgbThreshold;
  const issue=imageIssue(before,after);
  const busy=submitting||job?.status==='queued'||job?.status==='running';
  function fetchGallery(signal?:AbortSignal){
    setLoading(true);setError(undefined);
    api<{images:GalleryImage[]}>('/images',{signal}).then(data=>{
      setImages(data.images);
      const a=data.images.find(x=>x.available&&data.images.some(y=>!imageIssue(x,y))),b=a?data.images.find(y=>!imageIssue(a,y)):undefined;
      if(a&&b){setBefore(a.id);setAfter(b.id);}
    }).catch(e=>{if(!signal?.aborted)setError((e as Error).message)}).finally(()=>{if(!signal?.aborted)setLoading(false)});
  }
  useEffect(()=>{const controller=new AbortController();fetchGallery(controller.signal);return()=>controller.abort()},[]);
  async function run(){
    if(issue||busy)return;
    setSubmitting(true);setError(undefined);setResult(undefined);setRegion(undefined);
    try{
      setJob(await api<ImageJob>('/image-comparisons',{method:'POST',body:JSON.stringify({before_id:beforeId,after_id:afterId,threshold,noise_radius:noise,min_region_pixels:minimum})}));
    }catch(e){setError((e as Error).message)}finally{setSubmitting(false)}
  }
  useEffect(()=>{if(beforeId&&afterId&&!auto.current){auto.current=true;void run()}},[beforeId,afterId]);
  useEffect(()=>{
    if(!job?.id)return;
    const id=job.id,controller=new AbortController();let timer:ReturnType<typeof setTimeout>;let polls=0;
    async function poll(){
      try{
        const current=await api<ImageJob>(`/image-comparisons/${id}`,{signal:controller.signal});
        if(controller.signal.aborted)return;
        setJob(current);
        if(current.status==='completed'&&current.result){setResult(current.result);setView('swipe');return;}
        if(current.status==='failed'){setError(current.error?.message||'Comparison could not complete.');return;}
        if(++polls>120){setError('Status checking timed out. Reload the gallery or try again.');setJob(j=>j?{...j,status:'failed'}:j);return;}
        timer=setTimeout(poll,500);
      }catch(e){if(!controller.signal.aborted){setError((e as ApiError).message);setJob(j=>j?{...j,status:'failed'}:j)}}
    }
    void poll();return()=>{controller.abort();clearTimeout(timer)};
  },[job?.id]);
  function choose(id:string,which:'before'|'after'){
    if(busy)return;
    setResult(undefined);setJob(undefined);setError(undefined);
    if(which==='before')setBefore(id);else setAfter(id);
  }
  const available=images.filter(i=>i.available);
  const simulated=before?.is_simulated;
  const image=(name:'before'|'after'|'heatmap'|'overlay')=>result?assetUrl(result.assets[name]):'';
  return <div className="ic-workflow">
    <div className="ic-intro"><div><span className="ic-kicker"><span/> PRELOADED IMAGERY WORKSPACE</span><h2>See the difference.<br/><em>Understand the evidence.</em></h2><p>Select a matched pair. Alignment, filtering, change indicators and a detailed report happen locally, without a live satellite-processing job.</p></div><div className="ic-intro-mark"><ScanLine size={43}/><strong>Compare. Inspect. Explain.</strong><span>Local processing · Traceable inputs</span><div><i/> Ready for demonstration</div></div></div>
    <div className={`ic-provenance ${simulated?'simulated':''}`} role="note"><ShieldCheck size={22}/><div><strong>{simulated?'SIMULATED DATA · METHODS DEMONSTRATION':'PROVENANCE FIRST'}</strong><p>{simulated?'These are generated fixtures. Scenario dates are labels, not satellite acquisitions. Indicators are not observed mangrove loss.':'Real comparisons require a matched pair from the same area, sensor and calibration. Simulations cannot be paired with real observations.'}</p></div></div>
    {error&&<div className="ic-error" role="alert"><TriangleAlert size={19}/><span>{error}</span><button className="button small" onClick={()=>{if(!images.length)fetchGallery();else void run()}} disabled={busy}>Retry</button></div>}
    {loading?<div className="ic-empty" role="status"><LoaderCircle className="spin"/><h3>Loading the local image library</h3><p>No NASA connection is needed.</p></div>:!available.length?<div className="ic-empty"><Images/><h3>No preloaded images available</h3><p>Restore the dataset assets or run the documented demo-data preparation command.</p><button className="button" onClick={()=>fetchGallery()}>Reload gallery</button></div>:<>
      <section className="ic-pair-bar" aria-label="Choose image dates"><label><span>01 / BASELINE</span><select aria-label="Baseline image date" value={beforeId} disabled={busy} onChange={e=>choose(e.target.value,'before')}><option value="">Choose an available image</option>{available.map(i=><option key={i.id} value={i.id}>{dateLabel(i)} · {i.name}</option>)}</select></label><ArrowLeftRight className="ic-pair-arrow" size={19}/><label><span>02 / FOLLOW-UP</span><select aria-label="Follow-up image date" value={afterId} disabled={busy} onChange={e=>choose(e.target.value,'after')}><option value="">Choose an available image</option>{available.map(i=><option key={i.id} value={i.id}>{dateLabel(i)} · {i.name}</option>)}</select></label><button className="ic-run" disabled={!!issue||busy} onClick={()=>void run()}>{busy?<LoaderCircle size={16} className="spin"/>:<Play size={15}/>} {busy?'Comparing…':'Compare images'}</button></section>
      {issue&&<p className="ic-selection-note" role="status"><TriangleAlert size={14}/>{issue}</p>}
      <div className="ic-workbench"><section className="ic-canvas-panel"><header><div><span className="ic-kicker">COMPARISON VIEW</span><h3>{result?'The same scene, brought into focus':'Your comparison workspace'}</h3></div><span className="ic-local"><i/> LOCAL ENGINE</span></header>
        <div className="ic-view-tabs" role="tablist" aria-label="Comparison view">{[['swipe','Before / after'],['side','Side by side'],['heatmap','Heatmap'],['regions','Regions']].map(([id,label])=><button role="tab" aria-selected={view===id} disabled={!result} key={id} onClick={()=>setView(id)}>{id==='swipe'?<ArrowLeftRight size={14}/>:id==='regions'?<ScanLine size={14}/>:<Layers size={14}/>} {label}</button>)}</div>
        {busy?<div className="ic-processing" role="status" aria-live="polite"><div className="ic-scan"><ScanLine size={42}/></div><span className="ic-kicker">AUTOMATIC LOCAL ANALYSIS</span><h3>{job?.stage||'Preparing your comparison'}</h3><p>Checking coverage, matching pixels and tracing image indicators.</p><progress value={job?.progress||3} max={100}/><span>{job?.progress||3}%</span></div>:result?<>
          <div className={`ic-viewer ${view==='side'?'side':''}`} style={{aspectRatio:view==='side'?undefined:`${result.width}/${result.height}`}}>
            {view==='swipe'?<><img src={image('before')} alt="Aligned baseline"/><img src={image('after')} className="ic-after" style={{clipPath:`inset(0 0 0 ${divider}%)`}} alt="Aligned follow-up"/><div className="ic-divider" style={{left:`${divider}%`}}><span><ArrowLeftRight size={17}/></span></div><input className="ic-divider-input" aria-label="Before and after divider" type="range" min="0" max="100" value={divider} onChange={e=>setDivider(Number(e.target.value))}/><span className="ic-image-label left">BASELINE</span><span className="ic-image-label right">FOLLOW-UP</span></>:view==='side'?<><figure><img src={image('before')} alt="Baseline side-by-side"/><figcaption>Baseline · {dateLabel(result.before)}</figcaption></figure><figure><img src={image('after')} alt="Follow-up side-by-side"/><figcaption>Follow-up · {dateLabel(result.after)}</figcaption></figure></>:<><img src={image(view==='heatmap'?'heatmap':'overlay')} alt={view==='heatmap'?'Computed change magnitude heatmap':'Computed highlighted change regions'}/>{view==='regions'&&<svg className="ic-region-svg" viewBox={`0 0 ${result.width} ${result.height}`} aria-label="Detected region outlines">{result.regions.map(r=><polygon key={r.id} points={r.polygon.map(p=>p.join(',')).join(' ')} className={selectedRegion===r.id?'selected':''} onClick={()=>setRegion(r.id)}><title>Region {r.id}: {r.pixels} pixels</title></polygon>)}</svg>}</>}
            <span className="ic-image-watermark">{result.is_simulated?'SIMULATED · NO OBSERVED FOREST CHANGE':result.before.data_type==='rgb'?'VISUAL INDICATORS ONLY':'BACKSCATTER INDICATORS · SCIENCE QA PENDING'}</span>
          </div>
          <div className="ic-view-caption"><span><Maximize2 size={13}/> {result.width} × {result.height} common pixels</span><span>{view==='swipe'?'Drag the divider or use the arrow keys':view==='heatmap'?`Scale 0–${result.heatmap_scale_max.toFixed(1)} ${result.summary.indicator_units}; color saturates at the upper limit`:'Dark areas indicate invalid or non-overlapping pixels'}</span></div>
          {view==='heatmap'&&<div className="ic-heat-legend"><span>Lower magnitude</span><i/><span>Higher magnitude · not a probability</span></div>}
          <div className="ic-result-stats"><div><span>SHARED VALID PIXELS</span><strong>{result.summary.valid_pixels.toLocaleString()}</strong></div><div><span>FLAGGED IMAGE PIXELS</span><strong>{result.summary.changed_percent_of_valid.toFixed(2)}<small>%</small></strong></div><div><span>DETECTED REGIONS</span><strong>{result.summary.region_count}</strong></div></div>
        </>:<div className="ic-empty ic-canvas-empty"><ArrowLeftRight size={35}/><h3>Two images. One clear comparison.</h3><p>{issue||'Your pair is ready. Run the comparison to align the imagery and generate indicators.'}</p></div>}
      </section>
      <aside className="ic-analysis"><header><SlidersHorizontal size={18}/><h3>Analysis controls</h3></header><div className="ic-controls"><label><span>Change threshold <b>{threshold} {sar?'dB':'delta-E'}</b></span><input aria-label="Change threshold" type="range" min={sar ? 0.5 : 2} max={sar?12:60} step={sar ? 0.5 : 1} value={threshold} disabled={busy} onChange={e=>sar?setSarThreshold(Number(e.target.value)):setRgbThreshold(Number(e.target.value))}/><small>{sar?'Absolute power-dB difference':'Visual color difference; not reflectance'}</small></label><label><span>Noise filtering</span><select aria-label="Noise filtering" disabled={busy} value={noise} onChange={e=>setNoise(Number(e.target.value))}><option value={0}>None</option><option value={1}>Light · 3 × 3 Gaussian</option><option value={2}>Moderate · 5 × 5 Gaussian</option></select></label><label><span>Minimum region size</span><select aria-label="Minimum region size" disabled={busy} value={minimum} onChange={e=>setMinimum(Number(e.target.value))}><option value={16}>16 pixels · fine</option><option value={64}>64 pixels · balanced</option><option value={256}>256 pixels · broad</option></select></label><p>Settings apply when you run the comparison. Thresholds are heuristic and do not identify confirmed deforestation.</p></div>
        <div className="ic-method"><span className="ic-kicker">METHOD & ALIGNMENT</span>{result?<><h4>{result.method}</h4><span className="ic-confidence"><Check size={12}/>{result.alignment.confidence==='georeferenced'?'Common grid verified':`${result.alignment.confidence} registration confidence`}</span><p>{result.alignment.method}</p>{result.alignment.matches!==undefined&&<dl><div><dt>Feature matches / inliers</dt><dd>{result.alignment.matches} / {result.alignment.inliers}</dd></div><div><dt>Registration residual</dt><dd>{result.alignment.reprojection_rmse_pixels?.toFixed(2)} px RMSE</dd></div></dl>}{result.alignment.crs&&<dl><div><dt>Coordinate system</dt><dd>{result.alignment.crs}</dd></div><div><dt>Grid resolution</dt><dd>{result.alignment.resolution?.join(' × ')}</dd></div></dl>}<small>{result.alignment.confidence_note}</small></>:<p>Registration and confidence diagnostics appear after processing. No accuracy score is assumed.</p>}</div>
        <div className="ic-download"><FileReport/><h4>An explanation, not just an image.</h4><p>Source metadata, dates, methods, highlighted regions and uncertainty in one report. Generated files are temporary; rerun the comparison after a backend restart.</p>{result?<a className="ic-pdf" href={assetUrl(result.assets.report)} download><ArrowDownToLine size={16}/>Download detailed PDF</a>:<button className="ic-pdf" disabled><ArrowDownToLine size={16}/>PDF available after comparison</button>}</div>
      </aside></div>
      {result&&<section className="ic-evidence"><div><span className="ic-kicker">INTERPRETATION & UNCERTAINTY</span><h3>What the indicators can tell you</h3><p>{result.interpretation}</p><ul>{result.warnings.map(w=><li key={w}><ShieldCheck size={14}/><span>{w}</span></li>)}</ul></div><div className="ic-regions-list"><span className="ic-kicker">HIGHLIGHTED IMAGE REGIONS</span>{result.regions.length?result.regions.slice(0,8).map(r=><button key={r.id} className={selectedRegion===r.id?'selected':''} onClick={()=>{setRegion(r.id);setView('regions')}}><span>{r.id.toString().padStart(2,'0')}</span><div><strong>{r.direction}</strong><small>{r.pixels.toLocaleString()} pixels · magnitude {r.mean_indicator_magnitude.toFixed(2)}</small></div><ChevronRight size={15}/></button>):<p>No region exceeds these settings. This does not prove an absence of environmental change.</p>}<small>Pixel regions, not mapped forest boundaries. Up to 8 largest regions shown here.</small></div></section>}
      <section className="ic-gallery"><header><div><span className="ic-kicker">THE LOCAL IMAGE LIBRARY</span><h3>Every image has a story. Keep its source.</h3></div><span>{available.length} available images</span></header><div className="ic-gallery-grid">{images.map(i=><article key={i.id} className={`ic-image-card ${beforeId===i.id||afterId===i.id?'chosen':''} ${!i.available?'unavailable':''}`}><div className="ic-thumb">{i.thumbnail_url?<img src={assetUrl(i.thumbnail_url)} alt={i.name} loading="lazy"/>:<Images size={28}/>}<span className={i.is_simulated?'sim':'real'}>{i.is_simulated?'SIMULATED':'REAL OBSERVATION'}</span>{(beforeId===i.id||afterId===i.id)&&<b>{beforeId===i.id?'BASELINE':'FOLLOW-UP'}</b>}</div><div className="ic-card-body"><small>{dateLabel(i)}</small><h4>{i.name}</h4><p><MapPin size={11}/>{i.area}</p><dl><div><dt>Sensor</dt><dd>{i.sensor}</dd></div><div><dt>Data</dt><dd>{i.data_type==='rgb'?'Display RGB':'Linear radar power'}</dd></div></dl><p className="ic-source">{i.source}</p>{!i.is_simulated&&<p className="ic-real-note">Real comparison requires a later, compatible observation in this gallery.</p>}<div className="ic-card-select"><button disabled={busy||!i.available} onClick={()=>choose(i.id,'before')}>{beforeId===i.id?<Check size={12}/>:null}Baseline</button><button disabled={busy||!i.available} onClick={()=>choose(i.id,'after')}>{afterId===i.id?<Check size={12}/>:null}Follow-up</button></div></div></article>)}</div></section>
    </>}
  </div>;
}
function FileReport(){return <div className="ic-report-icon"><Layers size={22}/></div>}
