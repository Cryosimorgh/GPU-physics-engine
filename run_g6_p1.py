"""One bounded, serialized headless publication batch. No gate qualification."""
from pathlib import Path
import json,csv,subprocess,time,os,re,hashlib
from dev_test import ROOT,Workflow,digest
from prepare_g6_control import prepare
OUT=ROOT/'evidence/g6-p1'
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 w=Workflow(OUT);results=[];timings=[];failures=[]
 lock=w.cache/'running.lock';fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(fd,str(os.getpid()).encode());os.close(fd)
 def run(name,command):
  start=time.perf_counter();log=OUT/(name+'.log')
  try:
   with log.open('w') as f:
    f.write(json.dumps([str(x) for x in command])+'\n');f.flush()
    p=subprocess.run(list(map(str,command)),cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=90)
   raw=log.read_text(errors='replace');ok=p.returncode==0
  except subprocess.TimeoutExpired:raw='';ok=False
  item=dict(name=name,status='PASS' if ok else 'FAIL',wall_s=time.perf_counter()-start,log=log.name)
  results.append(item)
  if not ok:failures.append(name)
  return raw,item
 try:
  # Complete both verified incremental builds before any GPU test starts.
  prepare();physics=w.gpu('physics');pool=w.gpu('pool_tests')
  raw,_=run('publication',[physics,'--n','32','--publication-tests','--debug','--out',OUT/'publication.json'])
  # Investigate no individual successful cases; one consolidated evidence file.
  for case in ['idle','collisions','energy','discovery','ownership']:
   run('regression-'+case,[pool,'--case',case,'--quick'])
  run('device',[physics,'--n','32','--device-tests','--debug','--out',OUT/'device.json'])
  for mode in ['recycle','delete-one']:
   run(mode,[physics,'--n','32','--fixture','1','--contacts','256','--pairs','256','--steps','3','--'+mode,'--verify-every-tick','--out',OUT/(mode+'.json')])
  # Two AB/BA pairs per workload; each existing case collects 32 warm GPU ticks.
  for workload in ['idle','break','moving']:
   for repeat,order in enumerate([['control','candidate'],['candidate','control']]):
    for build in order:
     exe=OUT/'control/pool_tests.exe' if build=='control' else pool
     raw,item=run(f'time-{workload}-{repeat}-{build}',[exe,'--case','overhead','--workload',workload,'--quick'])
     metrics=[json.loads(line[7:]) for line in raw.splitlines() if line.startswith('METRIC ')]
     samples=[json.loads(line[7:]) for line in raw.splitlines() if line.startswith('SAMPLE ')]
     states=[json.loads(line[9:]) for line in raw.splitlines() if line.startswith('WORKLOAD ')]
     if not metrics or len(samples)!=32:failures.append(item['name']+'-missing-evidence');continue
     timings.append(dict(workload=workload,repeat=repeat,build=build,**metrics[0],**metrics[1],state=states[0],raw_samples=samples))
  for workload in ['idle','break','moving']:
   selected=[x for x in timings if x['workload']==workload]
   if len({x['state']['state_sha256'] for x in selected})!=1:failures.append(workload+'-state-mismatch')
  summary=dict(status='PASS' if not failures else 'FAIL',qualification=False,g5='DEFERRED / NOT QUALIFIED',g6='NOT QUALIFIED',failures=failures,tests=results,timings=timings,build_actions=w.actions,reused_targets=w.reused,device_loss='UNVERIFIED: real device removal/recovery is not supported by the fail-stop runtime',hashes={n:digest(ROOT/n) for n in ['physics.c','physics.h','runtime.c','runtime.h','projected_solver.hlsl','physics.hlsl','zig-out/bin/physics.exe','zig-out/bin/pool_tests.exe']})
  (OUT/'results.json').write_text(json.dumps(summary,indent=2))
  keys=['workload','repeat','build','gpu_us_p50','gpu_us_p95','cpu_record_us_p50','queue_submit_us_p50','cpu_record_submit_us_p50']
  with (OUT/'results.csv').open('w',newline='') as f:
   writer=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');writer.writeheader();writer.writerows(timings)
  print(summary['status'],'tests',len(results),'failures',failures)
  print('workload build GPU-p50/p95-us CPU-record+submit-p50-us')
  for x in timings:print(x['workload'],x['build'],round(x['gpu_us_p50'],2),round(x['gpu_us_p95'],2),round(x['cpu_record_submit_us_p50'],2))
  print('Device removal/recovery UNVERIFIED; G5 DEFERRED; G6 NOT QUALIFIED.')
  return bool(failures)
 finally:lock.unlink()
if __name__=='__main__':raise SystemExit(main())
