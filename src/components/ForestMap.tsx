import { useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import type { GeoJSONSource, StyleSpecification } from 'maplibre-gl';
import { Crosshair, Layers, MapPin, AlertTriangle } from 'lucide-react';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { Scene } from '../types';
import { PILOT } from '../types';

export default function ForestMap({ bbox, scenes, selected, large = false }: { bbox: number[]; scenes: Scene[]; selected?: Scene; large?: boolean }) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  const [satellite, setSatellite] = useState(true);
  const [showFootprints, setShowFootprints] = useState(false);
  const customAOI = bbox.some((v,i)=>v!==PILOT[i]);
  useEffect(() => {
    if (!container.current) return;
    const style: StyleSpecification = { version: 8, sources: {
      satellite: {type:'raster', tiles:['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'], tileSize:256, attribution:'Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community'},
      osm: {type:'raster', tiles:['https://tile.openstreetmap.org/{z}/{x}/{y}.png'], tileSize:256, maxzoom:19, attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'}
    }, layers:[{id:'satellite',type:'raster',source:'satellite',paint:{'raster-saturation':-.25,'raster-brightness-max':.8}},{id:'osm',type:'raster',source:'osm',layout:{visibility:'none'}}] };
    let instance: maplibregl.Map;
    try {
      instance = new maplibregl.Map({container:container.current,style,center:[88.75,21.92],zoom:9.2,attributionControl:{compact:true}});
      map.current = instance;
      instance.addControl(new maplibregl.NavigationControl({showCompass:true}), 'top-right');
      instance.addControl(new maplibregl.ScaleControl({maxWidth:100,unit:'metric'}), 'bottom-left');
      instance.on('error', () => setError('Some map tiles could not load. Try the street basemap or check your connection.'));
      instance.on('load', () => {
        instance.addSource('aoi', {type:'geojson',data:{type:'FeatureCollection',features:[]}});
        instance.addLayer({id:'aoi-fill',type:'fill',source:'aoi',paint:{'fill-color':'#a5f3c5','fill-opacity':.08}});
        instance.addLayer({id:'aoi-border',type:'line',source:'aoi',paint:{'line-color':'#d8ef9b','line-width':2,'line-dasharray':[3,2]}});
        instance.addSource('scenes', {type:'geojson',data:{type:'FeatureCollection',features:[]}});
        instance.addLayer({id:'scene-fill',type:'fill',source:'scenes',paint:{'fill-color':'#68d8c7','fill-opacity':.1}});
        instance.addLayer({id:'scene-border',type:'line',source:'scenes',paint:{'line-color':'#68d8c7','line-width':1.5}});
        setReady(true);
      });
    } catch { setError('WebGL could not initialize. The AOI bounds and scene metadata remain available below.'); }
    const observer = new ResizeObserver(() => map.current?.resize());
    observer.observe(container.current);
    return () => {observer.disconnect(); instance?.remove(); map.current = null; setReady(false);};
  }, []);
  useEffect(() => {
    if (!ready || !map.current) return;
    const [w,s,e,n] = bbox;
    (map.current.getSource('aoi') as GeoJSONSource).setData({type:'Feature',properties:{},geometry:{type:'Polygon',coordinates:[[[w,s],[e,s],[e,n],[w,n],[w,s]]]}});
    map.current.fitBounds([[w,s],[e,n]], {padding:65,duration:900});
  }, [bbox, ready]);
  useEffect(() => {
    if (!ready || !map.current) return;
    const shown = selected ? [selected] : showFootprints ? scenes : [];
    (map.current.getSource('scenes') as GeoJSONSource).setData({type:'FeatureCollection',features:shown.filter(s=>s.geometry).map(s=>({type:'Feature',properties:{id:s.id},geometry:s.geometry!}))});
  }, [scenes, selected, showFootprints, ready]);
  function changeBasemap() {
    if (!ready || !map.current) return;
    map.current.setLayoutProperty('satellite','visibility',satellite?'none':'visible');
    map.current.setLayoutProperty('osm','visibility',satellite?'visible':'none');
    setSatellite(!satellite); setError('');
  }
  return <div className={`forest-map ${large?'large':''}`}>
    <div ref={container} className="map-canvas" aria-label="Interactive Sundarbans map with a provisional pilot bounding box" />
    <div className="map-location"><MapPin size={14}/><span>{customAOI?'CUSTOM PILOT':'SUNDARBANS PILOT'}</span><i/>Provisional AOI</div>
    {!customAOI&&<div className="map-watermark"><span>INDIA</span><strong>Sundarbans</strong><small>Ganges–Brahmaputra Delta</small></div>}
    <div className="map-actions"><button onClick={changeBasemap} disabled={!ready}><Layers size={15}/>{satellite?'Satellite':'Street'}</button><button onClick={()=>setShowFootprints(!showFootprints)} disabled={!ready} className={showFootprints?'active':''}>Scene footprints {showFootprints?'on':'off'}</button><button aria-label="Recenter on pilot AOI" title="Recenter on pilot AOI" onClick={()=>map.current?.fitBounds([[bbox[0],bbox[1]],[bbox[2],bbox[3]]],{padding:65})}><Crosshair size={17}/></button></div>
    <div className="map-legend"><span><i className="pilot-key"/>Pilot AOI</span><span><i className="scene-key"/>CMR footprint</span><small>Basemap imagery ≠ NISAR observations</small></div>
    {!ready&&!error&&<div className="map-status">Loading interactive map…</div>}
    {error&&<div className="map-error" role="status"><AlertTriangle size={14}/>{error}</div>}
  </div>;
}
