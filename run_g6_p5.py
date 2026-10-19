"""One bounded integrated-main comparison. Never launches a window or viewer."""
import os,json,csv,subprocess,time,math
from pathlib import Path
from dev_test import ROOT,Workflow,digest,dependencies
from build_consumer import build
from windows_sdk import compiler
OUT=ROOT/'evidence/g6-p5'
METRICS=['acceptance_wait_us','cpu_record_submit_us','cpu_queue_submit_us','cpu_handoff_us','gpu_tick_us','gpu_render_us','snapshot_age_ticks','frame_complete_us']
def main():
 OUT.mkdir(parents=True,exist_ok=True);w=Workflow(OUT);tests=[];failures=[];trials=[];actions=[]
 lock=w.cache/'running.lock';fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(fd,str(os.getpid()).encode());os.close(fd)
 summary={'status':'FAIL','G5':'DEFERRED / NOT QUALIFIED','G6':'NOT QUALIFIED','default_mode':'blocking','physical_device_loss':'UNVERIFIED','measurement':'offscreen complete-to-complete serial frames including CPU verification; not displayed FPS'}
 def run(name,cmd,expected_rejection=False):
  prior_path=OUT/'fixture-command-failure/reusable-tests.json'
  prior=json.loads(prior_path.read_text()).get(name) if prior_path.exists() else None
  if prior and prior['test']['command']==list(map(str,cmd)) and prior['binary_sha256']==digest(cmd[0]) and (not name.startswith('syntax-') or prior['input_sha256']==digest(ROOT/cmd[2])):
   tests.append({**prior['test'],'reused_unchanged_inputs':True,'binary_sha256':prior['binary_sha256']});return None
  item={'name':name,'command':list(map(str,cmd))};start=time.perf_counter();payload=None
  try:
   target=Path(cmd[list(cmd).index('--out')+1]) if '--out' in cmd else None
   if target:target.unlink(missing_ok=True)
   with (OUT/(name+'.log')).open('w') as f:
    f.write(json.dumps(item)+'\n');f.flush();p=subprocess.run(item['command'],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=75)
   raw=(OUT/(name+'.log')).read_text(errors='replace')
   if expected_rejection:ok=p.returncode!=0 and 'error: Config' in raw
   elif target:payload=json.loads(target.read_text());ok=p.returncode==0 and payload['status']=='PASS'
   else:ok=p.returncode==0 and ('PASS' in raw or name.startswith('syntax-'))
   item.update(status='PASS' if ok else 'FAIL',returncode=p.returncode,expected_rejection=expected_rejection)
  except Exception as error:item.update(status='FAIL',error=str(error))
  item['wall_s']=time.perf_counter()-start;tests.append(item)
  if item['status']!='PASS':failures.append(name)
  return payload
 try:
  candidate,cw=build(OUT);control,bw=build(OUT,blocking=True);physics=w.gpu('physics');pool=w.gpu('pool_tests');actions=cw.actions+bw.actions+w.actions
  sources=dependencies(['viewer_runtime.c','render_consumer_main.zig','physics.c','physics_tests.c','spatial.c','viewer_main.zig','bench_main.zig','playground_main.zig'])
  summary.update(driver_sha256=digest(__file__),source_sha256={n:digest(ROOT/n) for n in sources},candidate_binary=digest(candidate),control_binary=digest(control),physics_binary=digest(physics),pool_binary=digest(pool))
  for name in ['viewer_main.zig','bench_main.zig','playground_main.zig']:run('syntax-'+name,[compiler(),'ast-check',name])
  run('invalid-mode',[candidate,'--nonblocking','2'],True)
  summary['default_consumer']=run('default-consumer',[candidate,'--profile','13','--samples','0','--out',OUT/'default-consumer.json'])
  summary['nonblocking_consumer']=run('nonblocking-consumer',[candidate,'--profile','13','--samples','0','--nonblocking','1','--out',OUT/'nonblocking-consumer.json'])
  summary['pending_generation']=run('pending-generation',[candidate,'--profile','9','--samples','0','--nonblocking','1','--out',OUT/'pending-generation.json'])
  for flag,name in [('--publication-tests','publication'),('--ownership-tests','ownership')]:run(name,[physics,'--n','32',flag,'--debug','--out',OUT/(name+'.json')])
  for case in ['idle','collisions','energy']:run('pool-'+case,[pool,'--case',case,'--quick'])
  if not failures:
   for workload,profile in [('idle',9),('pool-motion-commands',13)]:
    for repeat,order in enumerate([['blocking','nonblocking'],['nonblocking','blocking']]):
     for arm in order:
      exe=control if arm=='blocking' else candidate;name=f'{workload}-{repeat}-{arm}'
      data=run(name,[exe,'--profile',str(profile),'--samples','16','--nonblocking',str(int(arm=='nonblocking')),'--out',OUT/(name+'.json')])
      if data:trials.append({'workload':workload,'arm':arm,'repeat':repeat,**data})
  rows=[];throughput=[]
  for workload in ['idle','pool-motion-commands']:
   cases=[t for t in trials if t['workload']==workload]
   if len(cases)!=4:continue
   if len({t['final_state_fnv64'] for t in cases})!=1:failures.append(workload+': final state mismatch')
   if len({tuple(t['command_frames']) for t in cases})!=1:failures.append(workload+': command work mismatch')
   for arm in ['blocking','nonblocking']:
    group=[t for t in cases if t['arm']==arm]
    for key in METRICS:
     values=sorted(x for t in group for x in t[key]);rows.append({'workload':workload,'arm':arm,'metric':key,'samples':len(values),'p50':values[math.ceil(len(values)*.5)-1],'p95':values[math.ceil(len(values)*.95)-1]})
    elapsed=sum(x for t in group for x in t['frame_complete_us']);frames=sum(len(t['frame_complete_us']) for t in group)
    throughput.append({'workload':workload,'arm':arm,'completed_frames':frames,'elapsed_us':elapsed,'frames_per_second':1e6*frames/elapsed,'committed':group[0]['committed'],'allocations':group[0]['allocations'],'state_fnv64':group[0]['final_state_fnv64'],'measured_command_frames':sum(sum(t['command_frames']) for t in group),'contacts':sum(sum(t['contacts']) for t in group)})
  summary.update(status='PASS' if not failures and len(trials)==8 else 'FAIL',comparison=rows,throughput=throughput,trials=trials)
 except Exception as error:failures.append(str(error));summary['error']=str(error)
 finally:
  if failures:summary['status']='FAIL'
  summary.update(tests=tests,failures=failures,build_actions=actions)
  (OUT/'results.json').write_text(json.dumps(summary,indent=2))
  for name,rows in [('results',summary.get('comparison',[])),('throughput',summary.get('throughput',[]))]:
   if rows:
    with (OUT/(name+'.csv')).open('w',newline='') as f:
     writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
  lock.unlink();print(summary['status'],len(tests),'process runs; failures:',failures)
  for workload in ['idle','pool-motion-commands']:
   print(workload,'metric | blocking p50/p95 | nonblocking p50/p95')
   for key in METRICS:
    values=[next((r for r in summary.get('comparison',[]) if r['workload']==workload and r['arm']==arm and r['metric']==key),None) for arm in ['blocking','nonblocking']]
    if all(values):print(key,*[(round(r['p50'],3),round(r['p95'],3)) for r in values])
  print('Complete throughput/memory:',summary.get('throughput'));print('Blocking default; nonblocking selectable. G5 deferred; G6 not qualified.')
 return summary['status']!='PASS'
if __name__=='__main__':raise SystemExit(main())
