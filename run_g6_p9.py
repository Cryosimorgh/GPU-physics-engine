"""One bounded serialized CLI qualification of merged main. No physics changes."""
from pathlib import Path
import csv,json,math,os,subprocess,sys,time
from dev_test import Workflow,dependencies,digest
from build_consumer import build as consumer_build
from analyze_g6_p8 import summarize,distribution
R=Path(__file__).resolve().parent;E=R/'evidence/g6-p9'
def read_rows(path):
    with path.open() as f:return [json.loads(line) for line in f]
def extended(rows,cleanup,code):
    s=summarize(rows,cleanup,code);ts=[r for r in rows if r['type']=='TICK'];start=next((r for r in rows if r['type']=='START'),{})
    dt=start.get('dt');budget=dt*1e6 if dt else None
    s['deadline_us']=budget;s['deadline_scope']='fixed dt, not a new performance target'
    if not ts or not budget:return s
    intervals=[(r['elapsed_s']-(ts[i-1]['elapsed_s'] if i else 0))*1e6 for i,r in enumerate(ts)]
    s['deadline_misses']={k:sum(v>budget for v in values) for k,values in {'gpu_tick':[r['gpu_us'][39] for r in ts],'physics_api':[r['api_us'] for r in ts],'verification_inclusive_interval':intervals}.items()}
    s['verification_inclusive_interval_us']=distribution(intervals)
    s['real_time']='NOT QUALIFIED' if any(s['deadline_misses'].values()) else 'NO OBSERVED MISSES; NOT HARD REAL-TIME QUALIFICATION'
    s['state_hash_scope']='full allocated SoA, padding and guard; pool also includes retained rolling state'
    s['independent_kkt_ratio']=distribution([r['independent']['residual_ratio'] for r in ts]) if start.get('fixture')!=13 else None
    s['memory_bounded']=all(s['memory'][k]['min']==s['memory'][k]['max'] for k in ['committed','allocations','releases'])
    s['GPU_timestamp_scope']='physics.c stamp39 follows state_record_copy, before submit; includes immutable publication copy'
    s['GPU_synchronization_counter_scope']='No hardware barrier counter; CPU fence blocking measured separately, not additive to GPU time'
    return s
def compare(a,b):
    a=[r for r in a if r['type']=='TICK'];b=[r for r in b if r['type']=='TICK'];common=min(len(a),len(b))
    first=next((i for i in range(common) if a[i]['state_hash']!=b[i]['state_hash']),None)
    return {'common_ticks':common,'bitwise_equal':common>0 and first is None,'first_difference':first,
            'first_difference_values':None if first is None else [{k:r[k] for k in ['tick','state_hash','contacts','islands','largest','iterations','energy','independent']} for r in [a[first],b[first]]]}
def main():
    E.mkdir(parents=True,exist_ok=True)
    if (E/'results.json').exists():raise SystemExit('Preserve previous evidence: use a fresh isolated checkout')
    out=E/'build';out.mkdir(exist_ok=True);w=Workflow(out)
    lock=w.cache/'running.lock';fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(fd,str(os.getpid()).encode());os.close(fd)
    begun=time.monotonic();result={'functional':'INCOMPLETE','G5':'DEFERRED','G6':'NOT QUALIFIED','GPU-02':'UNVERIFIED','base':'e843a42','batch_limit_s':600,'tests':[],'scenarios':[],'determinism':{},'archive_comparisons':{}}
    def save():(E/'results.json').write_text(json.dumps(result,indent=2))
    def run(name,command,timeout=90,payload=None):
        remaining=600-(time.monotonic()-begun)
        if remaining<=0:raise RuntimeError('Batch deadline reached before '+name)
        t=time.monotonic();record={'name':name,'command':list(map(str,command))}
        with (E/(name+'.log')).open('w',encoding='utf-8') as f:
            f.write(json.dumps(record)+'\n');f.flush()
            try:p=subprocess.run(record['command'],cwd=R,stdout=f,stderr=subprocess.STDOUT,timeout=min(timeout,remaining));code=p.returncode
            except subprocess.TimeoutExpired:code='TIMEOUT'
        record.update(exit=code,wall_s=time.monotonic()-t);result['tests'].append(record);save()
        if code!=0:raise RuntimeError(name+': '+str(code))
        if payload:
            data=json.loads(payload.read_text());record['payload_status']=data.get('status');save()
            if data.get('status')!='PASS':raise RuntimeError(name+': payload '+str(data.get('status')))
        return code
    try:
        physics=w.gpu('physics');pool=w.gpu('pool_tests');cpu=w.cpu();consumer,cw=consumer_build(out)
        result['build']={'binaries':{p.name:digest(p) for p in [physics,pool,cpu,consumer]},'sources':{n:digest(R/n) for n in dependencies(['physics_main.zig','sustained_physics.zig','pool_tests.zig','runtime.c','spatial.c','physics.c','physics_verify.c','physics_tests.c','viewer_runtime.c','render_consumer_main.zig','physics.hlsl'])},'shaders':{p.name:digest(p) for p in R.glob('*.dxil')},'tools':w.tool_hashes,'build_actions':w.actions+cw.actions,'verified_reuses':w.reused+cw.reused}
        run('units',[sys.executable,'-m','unittest','test_dev_workflow','test_pool_rail_gap','test_g6_p9','-v'],30)
        run('cpu',[cpu],30)
        for case in ['rails','idle','collisions','energy','regression','discovery','ownership']:
            run('pool-'+case,[pool,'--case',case,'--quick',*(['--debug'] if case=='rails' else [])])
        for name,n,fixture in [('pool',16,13),('medium',1024,10),('large',8192,10)]:
            pair=[]
            for repeat in range(2):
                label=f'{name}-{repeat}';path=E/(label+'.json')
                cmd=[physics,'--n',n,'--fixture',fixture,'--contacts',256 if n==16 else n*12,'--pairs',256 if n==16 else n*8,'--flags',7 if n==16 else 4,'--cell-mode',1,'--seconds',30,'--out',path]
                code=run(label,cmd,45)
                rows=read_rows(Path(str(path)+'.jsonl'));cleanup=json.loads(path.read_text());s=extended(rows,cleanup,code);s.update(name=label,repeat=repeat)
                result['scenarios'].append(s);save()
                if s['status']!='PASS' or not s['memory_bounded']:raise RuntimeError(label+': functional/state/memory validation failed')
                pair.append(rows)
                with (E/(label+'.csv')).open('w',newline='') as f:
                    writer=csv.writer(f);writer.writerow(['tick','gpu_us','cpu_record_us','cpu_submit_us','blocking_us','api_us','verification_us','contacts','islands','largest','energy','independent_kkt_ratio','state_hash','committed','allocations'])
                    for r in rows:
                        if r['type']=='TICK':writer.writerow([r['tick'],r['gpu_us'][39],r['cpu_record_us'],r['cpu_submit_us'],r['blocking_us'],r['api_us'],r['verification_us'],r['contacts'],r['islands'],r['largest'],r['energy'],r['independent']['residual_ratio'] if n!=16 else None,r['state_hash'],r['memory']['committed'],r['memory']['allocations']])
            d=compare(*pair);result['determinism'][name]=d;save()
            if not d['bitwise_equal']:raise RuntimeError(name+': state repeatability failure at tick '+str(d['first_difference']))
            reference=E/'reference'/('evidence/g6-p8b/sustained-0.json.jsonl' if n==16 else 'evidence/g6-p8/'+('medium-islands' if n==1024 else 'large-distributed')+'.json.jsonl')
            result['archive_comparisons'][name]=compare(read_rows(reference),pair[0]);save()
        # Existing P6 native CLI cases, once each; pool regressions already ran.
        for case in range(8):
            path=E/f'device-{case}.json';run(f'device-{case}',[consumer,'--device-case',case,'--out',path],90,path)
        for mode in [0,1]:
            path=E/f'consumer-{mode}.json';run(f'consumer-{mode}',[consumer,'--profile',13,'--samples',0,'--nonblocking',mode,'--out',path],90,path)
        path=E/'pending-generation.json';run('pending-generation',[consumer,'--profile',9,'--samples',0,'--nonblocking',1,'--out',path],90,path)
        for flag,name in [('--publication-tests','publication'),('--ownership-tests','ownership')]:
            path=E/(name+'.json');run(name,[physics,'--n',32,flag,'--debug','--out',path],90,path)
        path=E/'nonpool.json';run('nonpool',[physics,'--n',32,'--fixture',1,'--steps',4,'--contacts',256,'--pairs',256,'--verify-every-tick','--out',path],30,path)
        result['functional']='PASS IN TESTED ENVELOPE'
    except Exception as error:result['functional']='FAIL / INCOMPLETE';result['first_failure']=str(error)
    finally:
        result['batch_wall_s']=time.monotonic()-begun;save();lock.unlink()
    print('case functional ticks GPU-p50/p95/p99-ms GPU/API/interval-deadline-misses')
    for s in result['scenarios']:print(s['name'],s['status'],s['accepted_ticks'],[round(s['gpu_tick_us'][p]/1000,4) for p in ['p50','p95','p99']],s.get('deadline_misses'))
    print(result['functional'],'first_failure=',result.get('first_failure'),'; G6 NOT QUALIFIED; evidence',E)
    return result['functional']!='PASS IN TESTED ENVELOPE'
if __name__=='__main__':raise SystemExit(main())
