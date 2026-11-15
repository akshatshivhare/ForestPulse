import {TriangleAlert} from 'lucide-react';
import {BACKEND_UNAVAILABLE_MESSAGE,BACKEND_UNAVAILABLE_TITLE} from '../api';

export default function BackendUnavailable(){
  return <div className="error-notice" role="status"><TriangleAlert size={20}/><div><strong>{BACKEND_UNAVAILABLE_TITLE}</strong><p>{BACKEND_UNAVAILABLE_MESSAGE}</p></div></div>;
}
