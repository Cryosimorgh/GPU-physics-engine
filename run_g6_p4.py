"""One bounded serialized GPU batch: P3 handoff versus deferred consumption."""
import os,json,csv,subprocess,time,math
from pathlib import Path
from dev_test import ROOT,Workflow,digest,dependencies
from build_consumer import build
OUT=ROOT/'evidence/g6-p4'
def main():
 OUT.mkdir(parents=True,exist_ok=True);w=Workflow(OUT);tests=[];failures=[];renders=[];actions=[]
 lock=w.cache/'running.lock';fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(fd,str(os.getpid()).encode());os.close(fd)
 summary={'status':'FAIL','G5':'DEFERRED / NOT QUALIFIED','G6':'NOT QUALIFIED','physical_device_loss':'UNVERIFIED','control':'P3 blocking handoff with common metrics/harness; G6_P3_BLOCKING_CONTROL=1'}
 def run(name,cmd):
  reuse=json.loads((OUT/'reusable-tests.json').read_text()) if (OUT/'reusable-tests.json').exists() else {}
  prior=reuse.get(name)
  if prior and prior['test']['command']==list(map(str,cmd)) and prior['binary_sha256']==digest(cmd[0]):
   tests.append({**prior['test'],'reused_unchanged_binary':True,'binary_sha256':prior['binary_sha256']});return None
  item={'name':name,'command':list(map(str,cmd))};start=time.perf_counter();payload=None
  try:
   target=Path(cmd[list(cmd).index('--out')+1]) if '--out' in cmd else None
   if target:target.unlink(missing_ok=True)
   with (OUT/(name+'.log')).open('w') as f:
    f.write(json.dumps(item)+'\n');f.flush();p=subprocess.run(item['command'],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=60)
   raw=(OUT/(name+'.log')).read_text(errors='replace');ok=p.returncode==0
   if target:payload=json.loads(target.read_text());ok=ok and payload['status']=='PASS'
   else:ok=ok and 'PASS' in raw
   item.update(status='PASS' if ok else 'FAIL',returncode=p.returncode)
  except Exception as error:item.update(status='FAIL',error=str(error))
  item['wall_s']=time.perf_counter()-start;tests.append(item)
  if item['status']!='PASS':failures.append(name)
  return payload
 try:
  candidate,cw=build(OUT);control,bw=build(OUT,blocking=True);physics=w.gpu('physics');pool=w.gpu('pool_tests');actions=cw.actions+bw.actions+w.actions
  summary.update(driver_sha256=digest(__file__),source_sha256={n:digest(ROOT/n) for n in dependencies(['viewer_runtime.c','render_consumer_main.zig','physics.c','physics_tests.c','spatial.c'])},candidate_binary=digest(candidate),control_binary=digest(control))
  summary['nonblocking']=run('nonblocking',[candidate,'--profile','9','--samples','0','--out',OUT/'nonblocking.json'])
  summary['consumer_lifecycle']=run('consumer-lifecycle',[candidate,'--profile','13','--samples','0','--out',OUT/'consumer-lifecycle.json'])
  for flag,name in [('--publication-tests','publication'),('--ownership-tests','ownership')]:run(name,[physics,'--n','32',flag,'--debug','--out',OUT/(name+'.json')])
  for case in ['idle','collisions','energy']:run('pool-'+case,[pool,'--case',case,'--quick'])
  if not failures:
   for repeat,order in enumerate([['control','candidate'],['candidate','control']]):
    for arm in order:
     data=run(f'render-{repeat}-{arm}',[control if arm=='control' else candidate,'--nonblocking','1','--profile','9','--samples','16','--out',OUT/f'render-{repeat}-{arm}.json'])
     if data:renders.append({'arm':arm,'repeat':repeat,**data})
  rows=[]
  for arm in ['control','candidate']:
   cases=[r for r in renders if r['arm']==arm]
   if len(cases)!=2:continue
   for key in ['acceptance_wait_us','cpu_record_submit_us','cpu_handoff_us','gpu_tick_us','gpu_render_us','snapshot_age_ticks','retirement_blocking_us']:
    values=sorted(x for c in cases for x in c[key]);rows.append({'arm':arm,'metric':key,'samples':len(values),'p50':values[math.ceil(len(values)*.5)-1],'p95':values[math.ceil(len(values)*.95)-1],'max':max(values)})
  summary.update(status='PASS' if not failures and len(renders)==4 else 'FAIL',comparison=rows,render_trials=renders)
  if len(renders)==4:
   summary['memory']={arm:{key:next(r[key] for r in renders if r['arm']==arm) for key in ['committed','allocations','managed_buffer_allocations','native_target_allocations']} for arm in ['control','candidate']}
 except Exception as error:failures.append(str(error));summary['error']=str(error)
 finally:
  if failures:summary['status']='FAIL'
  summary.update(tests=tests,failures=failures,build_actions=actions)
  (OUT/'results.json').write_text(json.dumps(summary,indent=2))
  if summary.get('comparison'):
   with (OUT/'results.csv').open('w',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(summary['comparison'][0]));writer.writeheader();writer.writerows(summary['comparison'])
  lock.unlink();print(summary['status'],len(tests),'process runs; failures:',failures)
  for row in summary.get('comparison',[]):print(row)
  print('Memory:',summary.get('memory'));print('G5 deferred; G6 unqualified; physical device loss not tested.')
 return summary['status']!='PASS'
if __name__=='__main__':raise SystemExit(main())
