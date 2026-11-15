import { useEffect, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { Scene } from '../types';
import { candidateStatus, displayDate } from '../types';

export default function DateCalendar({label, scenes, selected, onSelect, baseline}: {label:string;scenes:Scene[];selected?:Scene;onSelect:(s:Scene)=>void;baseline?:Scene}) {
  const latest = scenes.find(s=>s.date)?.date;
  const [month, setMonth] = useState(()=>new Date((latest || new Date().toISOString().slice(0,10)).slice(0,7)+'-01T12:00:00Z'));
  useEffect(()=>{if(latest) setMonth(new Date(latest.slice(0,7)+'-01T12:00:00Z'));},[latest]);
  const year = month.getUTCFullYear(), mon = month.getUTCMonth();
  const days = new Date(Date.UTC(year,mon+1,0)).getUTCDate();
  const offset = (new Date(Date.UTC(year,mon,1)).getUTCDay()+6)%7;
  const dateScenes = scenes.filter(s=>s.date===selected?.date);
  function move(amount:number) {setMonth(new Date(Date.UTC(year,mon+amount,1,12)));}
  return <div className="date-calendar">
    <div className="calendar-label"><span>{label}</span><strong>{displayDate(selected?.date || null)}</strong></div>
    <div className="calendar-nav"><button aria-label={`Previous month for ${label}`} onClick={()=>move(-1)}><ChevronLeft size={16}/></button><strong>{month.toLocaleDateString('en-GB',{month:'long',year:'numeric',timeZone:'UTC'})}</strong><button aria-label={`Next month for ${label}`} onClick={()=>move(1)}><ChevronRight size={16}/></button></div>
    <div className="calendar-grid">{['M','T','W','T','F','S','S'].map((d,i)=><span key={`h${i}`} className="weekday">{d}</span>)}{Array.from({length:offset},(_,i)=><span key={`e${i}`}/>)}{Array.from({length:days},(_,i)=>{
      const date = `${year}-${String(mon+1).padStart(2,'0')}-${String(i+1).padStart(2,'0')}`;
      const matches = scenes.filter(s=>s.date===date);
      const statuses = matches.map(s=>candidateStatus(s,baseline));
      const status = statuses.includes('candidate')?'candidate':statuses.includes('available')?'available':statuses.includes('unknown')?'unknown':'incompatible';
      return <button key={date} disabled={!matches.length} title={matches.length ? `${displayDate(date)}: ${matches.length} scene(s) · ${status === 'candidate'?'metadata candidate, overlap not screened':status}` : `${date}: no scenes in loaded results`} aria-label={`${date}, ${matches.length?`${matches.length} scene(s), ${status}`:'no scenes in loaded results'}`} aria-pressed={selected?.date===date} className={`${matches.length?status:''} ${selected?.date===date?'selected':''}`} onClick={()=>onSelect(matches.find(s=>candidateStatus(s,baseline)==='candidate')||matches[0])}>{i+1}{matches.length>0&&<i/>}</button>;
    })}</div>
    {selected&&<label className="scene-picker">Acquisition (UTC)<select value={selected.id} onChange={e=>{const scene=scenes.find(s=>s.id===e.target.value);if(scene)onSelect(scene);}}>{dateScenes.map(s=><option key={s.id} value={s.id}>{s.start_time?.slice(11,19)} · Track {s.track||'?'} / frame {s.frame||'?'} · {s.id}</option>)}</select></label>}
  </div>;
}
