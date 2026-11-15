import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { resolveApiBase } from './src/apiBase';
export default defineConfig(({mode})=>{
  const env=loadEnv(mode,process.cwd(),'VITE_');
  resolveApiBase(env.VITE_API_BASE_URL,mode==='production',process.env.VERCEL==='1');
  return {plugins:[react(),tailwindcss()],build:{outDir:'dist'},server:{proxy:{'/api':'http://127.0.0.1:8000'}}};
});
