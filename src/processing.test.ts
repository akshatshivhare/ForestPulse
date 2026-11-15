import {describe,expect,it} from 'vitest';
import {isProcessingActive,liveBlockReason} from './processing';
import type {ProcessingSetup} from './processing';
const setup={authentication_configured:false,real_processing_enabled:false} as ProcessingSetup;
describe('processing gates',()=>{
  it('always blocks public deployment even if credential flags are inconsistent',()=>expect(liveBlockReason({...setup,public_deployment:true,authentication_configured:true,real_processing_enabled:true})).toContain('disabled on the public deployment'));
  it('requires credentials even when live processing is enabled',()=>expect(liveBlockReason({...setup,real_processing_enabled:true})).toContain('authentication required'));
  it('requires explicit real processing opt-in',()=>expect(liveBlockReason({...setup,authentication_configured:true})).toContain('disabled'));
  it('permits explicit live requests only after both server gates',()=>expect(liveBlockReason({...setup,authentication_configured:true,real_processing_enabled:true})).toBe(''));
  it('polls validation, not dry runs or uncertain submissions',()=>{
    expect(isProcessingActive('dry_run')).toBe(false);expect(isProcessingActive('validating')).toBe(true);
    expect(isProcessingActive('verified')).toBe(false);expect(isProcessingActive('submission_unknown')).toBe(false);
  });
});
