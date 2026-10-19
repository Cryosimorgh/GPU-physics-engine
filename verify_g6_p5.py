"""Read-only reconciliation of the integrated Windows headless evidence."""
import json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def verify(root=ROOT):
 e=root/'evidence/g6-p5';r=json.loads((e/'results.json').read_text())
 assert r['status']=='PASS' and len(r['tests'])==20 and not r['failures']
 assert r['default_consumer']['nonblocking_requested']==0
 assert r['nonblocking_consumer']['nonblocking_requested']==1
 assert r['default_consumer']['blocking_build']==0
 assert r['pending_generation']['producer_gated_draws']==2
 assert r['pending_generation']['rejected_generation_withheld']
 assert r['pending_generation']['stale_handles_rejected']
 assert r['pending_generation']['lease_exhaustion']==64
 assert len(r['trials'])==8
 for t in r['trials']:
  assert len(t['frame_complete_us'])==16 and t['actual_vertex_invocations']==1980
  assert t['coverage_per_frame']==16 and t['no_window'] and t['no_present'] and not t['pixel_readback']
  assert abs(t['complete_frames_per_second']-1e6*16/sum(t['frame_complete_us']))<0.001
  assert len(t['command_frames'])==len(t['snapshot_age_ticks'])==16
  for command,age in zip(t['command_frames'],t['snapshot_age_ticks']):
   assert age==(0 if command or t['arm']=='blocking' else 1)
 for workload in ['idle','pool-motion-commands']:
  cases=[t for t in r['trials'] if t['workload']==workload]
  assert len({t['final_state_fnv64'] for t in cases})==1
  assert len({(t['committed'],t['allocations']) for t in cases})==1
  assert len({tuple(t['command_frames']) for t in cases})==1
  for arm in ['blocking','nonblocking']:
   group=[t for t in cases if t['arm']==arm]
   for row in (x for x in r['comparison'] if x['workload']==workload and x['arm']==arm):
    v=sorted(y for t in group for y in t[row['metric']]);assert len(v)==32
    assert row['p50']==v[15] and row['p95']==v[30]
   throughput=next(x for x in r['throughput'] if x['workload']==workload and x['arm']==arm)
   assert abs(throughput['frames_per_second']-32e6/sum(sum(t['frame_complete_us']) for t in group))<1e-7
 receipt={'status':'PASS','full_coverage_frames':160,'timed_frames':128,'state_signatures_match':True,'matching_tick_command_frames':True,'ordinary_nonblocking_age':1,'memory_equal_per_workload':True,'reused_checks':sum(bool(t.get('reused_unchanged_inputs')) for t in r['tests']),'timing_rows_reconciled':len(r['comparison']),'throughput_groups_reconciled':4,'verifier_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
 return receipt
if __name__=='__main__':print(json.dumps(verify(),indent=2))
