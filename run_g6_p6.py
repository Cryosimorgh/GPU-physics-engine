"""Bounded serialized Windows device lifecycle batch. No viewer/GUI is opened."""
import os,json,subprocess,time,csv
from pathlib import Path
from dev_test import ROOT,Workflow,digest,dependencies
from build_consumer import build
OUT=ROOT/'evidence/g6-p6'
def main():
 OUT.mkdir(parents=True,exist_ok=True);w=Workflow(OUT);tests=[];failures=[];cases=[];actions=[]
 lock=w.cache/'running.lock';fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(fd,str(os.getpid()).encode());os.close(fd)
 result={'status':'FAIL','G5':'DEFERRED / NOT QUALIFIED','G6':'NOT QUALIFIED','physical_hardware_loss_tested':False}
 def run(name,command):
  item={'name':name,'command':list(map(str,command))};start=time.perf_counter();payload=None
  target=Path(command[list(command).index('--out')+1]) if '--out' in command else None
  if target:target.unlink(missing_ok=True)
  try:
   with (OUT/(name+'.log')).open('w') as f:
    f.write(json.dumps(item)+'\n');f.flush();p=subprocess.run(item['command'],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=90)
   raw=(OUT/(name+'.log')).read_text(errors='replace');ok=p.returncode==0
   if target:payload=json.loads(target.read_text());ok=ok and payload['status']=='PASS'
   else:ok=ok and 'PASS' in raw
   item.update(status='PASS' if ok else 'FAIL',returncode=p.returncode)
  except Exception as error:item.update(status='FAIL',error=str(error))
  item['wall_s']=time.perf_counter()-start;tests.append(item)
  if item['status']!='PASS':failures.append(name)
  return payload
 try:
  exe,cw=build(OUT);physics=w.gpu('physics');pool=w.gpu('pool_tests');actions=cw.actions+w.actions
  result.update(driver_sha256=digest(__file__),source_sha256={n:digest(ROOT/n) for n in dependencies(['viewer_runtime.c','render_consumer_main.zig','physics.c','physics_tests.c','spatial.c'])},binaries={p.name:digest(p) for p in [exe,physics,pool]})
  for test in range(8):
   payload=run(f'device-{test}',[exe,'--device-case',str(test),'--out',OUT/f'device-{test}.json'])
   if payload:cases.append(payload)
  for mode in [0,1]:run('consumer-mode-'+str(mode),[exe,'--profile','13','--samples','0','--nonblocking',str(mode),'--out',OUT/f'consumer-mode-{mode}.json'])
  run('pending-generation',[exe,'--profile','9','--samples','0','--nonblocking','1','--out',OUT/'pending-generation.json'])
  for flag,name in [('--publication-tests','publication'),('--ownership-tests','ownership')]:run(name,[physics,'--n','32',flag,'--debug','--out',OUT/(name+'.json')])
  for case in ['idle','collisions','energy']:run('pool-'+case,[pool,'--case',case,'--quick'])
  result.update(status='PASS' if not failures and len(cases)==8 else 'FAIL',device_cases=cases)
 except Exception as error:failures.append(str(error));result['error']=str(error)
 finally:
  if failures:result['status']='FAIL'
  result.update(tests=tests,failures=failures,build_actions=actions)
  (OUT/'results.json').write_text(json.dumps(result,indent=2))
  rows=[{'case':c['case'],'trigger':c['device']['trigger'],'injected':c['device']['failure_injected'],'api_removal':c['device']['api_device_removal_executed'],'physical_loss':False,'cleanup_us':c['device']['cleanup_us'],'blocked_cleanup_us':c['device']['blocked_cleanup_us'],'recreated_gpu_modes':c['fresh_gpu_render_modes'],'state':c['device']['terminal_state'],'owners':c['device']['owners_after'],'claims':c['device']['claims_after']} for c in cases]
  if rows:
   with (OUT/'results.csv').open('w',newline='') as f:writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
  lock.unlink();print(result['status'],len(tests),'process runs; failures:',failures)
  for row in rows:print(row)
  print('G5 deferred; G6 unqualified. API-triggered removal is distinct from physical hardware failure.')
 return result['status']!='PASS'
if __name__=='__main__':raise SystemExit(main())
