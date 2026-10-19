"""Read-only reconciliation; does not execute or remove a GPU device."""
import json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def verify(root=ROOT):
 e=root/'evidence/g6-p6';r=json.loads((e/'results.json').read_text())
 assert r['status']=='PASS' and len(r['tests'])==16 and not r['failures']
 assert len(r['device_cases'])==8 and not r['physical_hardware_loss_tested']
 assert sorted(c['case'] for c in r['device_cases'])==list(range(8))
 for c in r['device_cases']:
  d=c['device'];n=c['case'];assert c['status']==d['status']=='PASS'
  assert c['old_identity']!=c['new_identity'] and c['old_buffer_rejected']
  assert c['explicit_recreation'] and c['fresh_gpu_render_modes']==2 and c['device_close_repeated']
  assert d['owners_after']==d['claims_after']==0 and d['repeated_teardown'] and d['stale_handles_rejected']
  assert not d['physical_hardware_loss'] and not c['physical_hardware_removal_tested']
  assert d['failure_injected']==(n in [1,2,4,6])
  assert d['api_device_removal_executed']==(n in [5,7])
  assert d['terminal_state']==(3 if n in [5,7] else 2 if n else 1)
  if n:assert d['first_error']!=0 and d['new_publications_blocked']
  if n in [2,3,4,6]:assert d['blocked_cleanup_us']>0
  if n in [5,7]:assert d['removed_reason']!=0
 return {'status':'PASS','process_runs':16,'device_cases':8,'api_removal_cases':2,'injected_API_cases':4,'held_consumer_real_timeout_cases':1,'normal_pending_shutdown_cases':1,'fresh_context_gpu_render_modes_verified':16,'physical_hardware_recovery':'UNVERIFIED','checkpoint_recovery':'UNVERIFIED','verifier_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
if __name__=='__main__':print(json.dumps(verify(),indent=2))
