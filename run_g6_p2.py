"""Bounded serialized G6-P2 batch using the existing verified CLI builds."""
import json,csv,subprocess,time,os,math,statistics
from pathlib import Path
from dev_test import Workflow,ROOT,digest,dependencies
OUT=ROOT/'evidence/g6-p2'
def q(values,p):return sorted(values)[math.ceil(p*len(values))-1]
def main():
 OUT.mkdir(parents=True,exist_ok=True);w=Workflow(OUT);tests=[];timings=[];failures=[]
 lock=w.cache/'running.lock';fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(fd,str(os.getpid()).encode());os.close(fd)
 summary=dict(status='FAIL',qualification=False,g5='DEFERRED / NOT QUALIFIED',g6='NOT QUALIFIED')
 def run(name,cmd):
  log=OUT/(name+'.log');start=time.perf_counter();item={'name':name,'command':list(map(str,cmd))}
  if '--out' in item['command']:
   target=Path(item['command'][item['command'].index('--out')+1]);target.unlink(missing_ok=True)
  try:
   with log.open('w') as stream:
    stream.write(json.dumps(item['command'])+'\n');stream.flush();p=subprocess.run(item['command'],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=90)
   raw=log.read_text(errors='replace');ok=p.returncode==0
   if '--out' in item['command']:
    payload=json.loads(target.read_text());ok=ok and payload['status']=='PASS' and payload['validation_errors']==0
   else:ok=ok and 'PASS' in raw
   item.update(returncode=p.returncode,status='PASS' if ok else 'FAIL')
  except Exception as error:raw=log.read_text(errors='replace');item.update(status='FAIL',error=str(error));ok=False
  item.update(wall_s=time.perf_counter()-start,log=log.name);tests.append(item)
  if not ok:failures.append(name)
  return raw
 try:
  control=json.loads((OUT/'control-build.json').read_text())
  for n,h in control['hashes'].items():assert digest(OUT/'control'/n)==h
  # Build once per target before submitting any GPU tests.
  physics=w.gpu('physics');pool=w.gpu('pool_tests')
  source_hashes={n:digest(ROOT/n) for n in dependencies(['physics_main.zig','pool_tests.zig','runtime.c','physics.c','physics_tests.c','spatial.c'])}
  for name,flag in [('ownership','--ownership-tests'),('publication','--publication-tests'),('device','--device-tests')]:
   run(name,[physics,'--n','32',flag,'--debug','--out',OUT/(name+'.json')])
  for case in ['idle','collisions','energy','discovery','ownership']:run('pool-'+case,[pool,'--case',case,'--quick'])
  for arm,exe in [('control',OUT/'control/physics.exe'),('candidate',physics)]:
   run('memory-'+arm,[exe,'--n','32','--fixture','1','--contacts','256','--pairs','256','--steps','8','--warmup','2','--verify-every-tick','--out',OUT/('memory-'+arm+'.json')])
  # AB/BA, fixed 32-tick existing workloads. Break is correctness/audit only.
  for workload in ['idle','moving','break']:
   for repeat,order in enumerate([['control','candidate'],['candidate','control']]):
    for arm in order:
     exe=pool if arm=='candidate' else OUT/'control/pool_tests.exe'
     raw=run(f'{workload}-{repeat}-{arm}',[exe,'--case','overhead','--workload',workload,'--quick'])
     samples=[json.loads(l[7:]) for l in raw.splitlines() if l.startswith('SAMPLE ')]
     metrics=[json.loads(l[7:]) for l in raw.splitlines() if l.startswith('METRIC ')]
     contacts=[json.loads(l[15:]) for l in raw.splitlines() if l.startswith('CONTACT_SAMPLE ')]
     states=[json.loads(l[9:]) for l in raw.splitlines() if l.startswith('WORKLOAD ')]
     if len(samples)!=32 or not metrics or not states:failures.append(f'{workload}-{arm}-missing');continue
     gpu=[s['gpu_cumulative_us'][39] for s in samples]
     assert metrics[0]['gpu_us_p50']==q(gpu,.5) and metrics[0]['gpu_us_p95']==q(gpu,.95)
     # Query indices are not chronological: contacts use indices 30..38.
     order_q=[0,1]
     for r in range(9):
      order_q.extend([2+3*r,30+r]);order_q.extend([3+3*r,4+3*r] if r<8 else [27])
     order_q.extend([28,29,39]);assert len(set(order_q))==40
     for s in samples:
      a=s['gpu_cumulative_us'];assert all(a[y]>=a[x] for x,y in zip(order_q,order_q[1:]))
      assert abs(sum(a[y]-a[x] for x,y in zip(order_q,order_q[1:]))-a[39])<1e-6
     timings.append(dict(workload=workload,arm=arm,repeat=repeat,samples=samples,contacts=contacts,state=states[0],timestamp_audit='PASS',performance_eligible=workload!='break'))
  for workload in ['idle','moving','break']:
   selected=[x for x in timings if x['workload']==workload]
   assert len(selected)==4 and len({x['state']['state_sha256'] for x in selected})==1
   assert len({json.dumps(x['contacts'],sort_keys=True) for x in selected})==1
  rows=[]
  for workload in ['idle','moving','break']:
   for arm in ['control','candidate']:
    samples=[s for t in timings if t['workload']==workload and t['arm']==arm for s in t['samples']]
    rows.append(dict(workload=workload,arm=arm,performance_eligible=workload!='break',gpu_p50_us=q([s['gpu_cumulative_us'][39] for s in samples],.5),gpu_p95_us=q([s['gpu_cumulative_us'][39] for s in samples],.95),cpu_record_submit_p50_us=q([s['cpu_record_submit_us'] for s in samples],.5)))
  memory={arm:json.loads((OUT/('memory-'+arm+'.json')).read_text()) for arm in ['control','candidate']}
  assert memory['control']['state_sha256']==memory['candidate']['state_sha256']
  summary.update(status='PASS' if not failures else 'FAIL',comparison=rows,memory={arm:payload['memory'] for arm,payload in memory.items()},source_hashes=source_hashes,binary_hashes={p.name:digest(p) for p in [physics,pool]},driver_hash=digest(__file__),break_policy='EXCLUDED from performance claims: archived summary/raw agreement proven; execution-time mode shift remains unexplained.',device_loss='UNVERIFIED; no physical removal/recovery tested')
 except Exception as error:failures.append(str(error));summary['error']=str(error)
 finally:
  summary.update(failures=failures,tests=tests,timings=timings,build_actions=w.actions,reused=w.reused)
  if failures:summary['status']='FAIL'
  (OUT/'results.json').write_text(json.dumps(summary,indent=2))
  if summary.get('comparison'):
   with (OUT/'results.csv').open('w',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(summary['comparison'][0]));writer.writeheader();writer.writerows(summary['comparison'])
  lock.unlink();print(summary['status'],len(tests),'process runs; failures:',failures)
  for row in summary.get('comparison',[]):print(row)
  print('Memory:',summary.get('memory'));print('Break excluded from performance attribution. G5 deferred; G6 not qualified.')
 return summary['status']!='PASS'
if __name__=='__main__':raise SystemExit(main())
