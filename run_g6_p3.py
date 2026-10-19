"""One bounded, serialized headless batch for the real application consumer."""
import os,json,csv,time,subprocess,math
from pathlib import Path
from dev_test import ROOT,Workflow,digest,dependencies
from build_consumer import build
OUT=ROOT/'evidence/g6-p3'
def quantile(a,p):return sorted(a)[math.ceil(len(a)*p)-1]
def main():
 OUT.mkdir(parents=True,exist_ok=True);w=Workflow(OUT);tests=[];failures=[];renders=[];actions=[]
 lock=w.cache/'running.lock';fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(fd,str(os.getpid()).encode());os.close(fd)
 summary={'status':'FAIL','qualification':False,'g5':'DEFERRED / NOT QUALIFIED','g6':'NOT QUALIFIED','device_loss':'UNVERIFIED: no physical removal/recreation performed'}
 def run(name,cmd,cwd=ROOT):
  log=OUT/(name+'.log');item={'name':name,'command':list(map(str,cmd)),'cwd':str(cwd)};start=time.perf_counter()
  target=Path(cmd[list(cmd).index('--out')+1]) if '--out' in cmd else None
  if target:target.unlink(missing_ok=True)
  try:
   with log.open('w') as stream:
    stream.write(json.dumps(item)+'\n');stream.flush();p=subprocess.run(item['command'],cwd=cwd,stdout=stream,stderr=subprocess.STDOUT,timeout=90)
   raw=log.read_text(errors='replace');ok=p.returncode==0
   if target:
    payload=json.loads(target.read_text());ok=ok and payload['status']=='PASS'
   else:payload=None;ok=ok and 'PASS' in raw
   item.update(returncode=p.returncode,status='PASS' if ok else 'FAIL')
  except Exception as error:payload=None;ok=False;item.update(status='FAIL',error=str(error))
  item.update(wall_s=time.perf_counter()-start,log=log.name);tests.append(item)
  if not ok:failures.append(name)
  return payload
 try:
  candidate,cw=build(OUT);actions+=cw.actions;control,bw=build(OUT,True);actions+=bw.actions
  physics=w.gpu('physics');pool=w.gpu('pool_tests');actions+=w.actions
  summary.update(driver_sha256=digest(__file__),source_sha256={n:digest(ROOT/n) for n in dependencies(['viewer_runtime.c','render_consumer_main.zig','physics.c','physics_tests.c','spatial.c'])},candidate_binary=digest(candidate),control_binary=digest(control),control_root=str(control.parent))
  # Actual renderer/PSO/DrawInstanced/query proof first, not a mocked task test.
  functional=run('real-consumer',[candidate,'--profile','13','--samples','0','--out',OUT/'real-consumer.json'])
  for flag,name in [('--publication-tests','publication'),('--ownership-tests','ownership')]:run(name,[physics,'--n','32',flag,'--debug','--out',OUT/(name+'.json')])
  for case in ['idle','collisions','energy','discovery','ownership']:run('pool-'+case,[pool,'--case',case,'--quick'])
  if functional and not failures:
   for repeat,order in enumerate([['control','candidate'],['candidate','control']]):
    for arm in order:
     exe=control if arm=='control' else candidate
     payload=run(f'render-{repeat}-{arm}',[exe,'--profile','9','--samples','16','--out',OUT/f'render-{repeat}-{arm}.json'],cwd=exe.parent)
     if payload:renders.append({'arm':arm,'repeat':repeat,**payload})
   for arm,exe in [('control',OUT/'physics-control/physics.exe'),('candidate',physics)]:
    run('memory-'+arm,[exe,'--n','32','--fixture','1','--contacts','256','--pairs','256','--steps','8','--warmup','2','--verify-every-tick','--out',OUT/f'memory-{arm}.json'])
  rows=[]
  for arm in ['control','candidate']:
   cases=[r for r in renders if r['arm']==arm]
   if len(cases)!=2:continue
   for key in ['gpu_tick_us','gpu_render_us','cpu_record_submit_us','acceptance_wait_us']:
    values=[x for c in cases for x in c[key]];rows.append({'arm':arm,'metric':key,'samples':len(values),'p50':quantile(values,.5),'p95':quantile(values,.95)})
  summary.update(render_trials=renders,comparison=rows,functional=functional,status='PASS' if not failures and len(renders)==4 else 'FAIL')
  summary['render_memory']={arm:{'committed':next(r['committed'] for r in renders if r['arm']==arm),'allocations':next(r['allocations'] for r in renders if r['arm']==arm)} for arm in ['control','candidate']} if len(renders)==4 else {}
 except Exception as error:failures.append(str(error));summary['error']=str(error)
 finally:
  summary.update(tests=tests,failures=failures,build_actions=actions)
  if failures:summary['status']='FAIL'
  (OUT/'results.json').write_text(json.dumps(summary,indent=2))
  if summary.get('comparison'):
   with (OUT/'results.csv').open('w',newline='') as f:writer=csv.DictWriter(f,fieldnames=list(summary['comparison'][0]));writer.writeheader();writer.writerows(summary['comparison'])
  lock.unlink();print(summary['status'],len(tests),'process runs; failures:',failures)
  for row in summary.get('comparison',[]):print(row)
  print('Render memory:',summary.get('render_memory'));print('No GUI/Present/image readback. G5 deferred; formal G6 pending.')
 return summary['status']!='PASS'
if __name__=='__main__':raise SystemExit(main())
