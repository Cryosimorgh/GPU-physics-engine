"""One serialized headless qualification batch. No viewer or solver changes."""
from pathlib import Path
import csv,hashlib,json,os,subprocess,sys,time
from dev_test import Workflow,dependencies,digest
from analyze_g6_p8 import summarize,stages
R=Path(__file__).resolve().parent;E=R/'evidence/g6-p8'
def main():
    E.mkdir(parents=True,exist_ok=True)
    if (E/'results.json').exists():raise RuntimeError('Preserve previous batch evidence; use a fresh isolated revision')
    w=Workflow(E/'batch-build')
    # Workflow output directory must exist; builds are verified/cached, not timestamp-based.
    (E/'batch-build').mkdir(exist_ok=True);lock=w.cache/'running.lock';fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(fd,str(os.getpid()).encode());os.close(fd)
    results={'G5':'DEFERRED','G6':'NOT QUALIFIED','GPU-02':'UNVERIFIED','scenarios':[],'regressions':[],'semantics':'30 wall-clock seconds per scenario, fixed dt 1/128; verification-inclusive serial throughput, no extrapolation'}
    try:
        physics=w.gpu('physics');pool=w.gpu('pool_tests')
        manifest={'binary_sha256':{p.name:digest(p) for p in [physics,pool]},'shader_sha256':{p.name:digest(p) for p in R.glob('*.dxil')},'source_sha256':{n:digest(R/n) for n in dependencies(['physics_main.zig','sustained_physics.zig','pool_tests.zig','runtime.c','spatial.c','physics.c','physics_verify.c','physics_tests.c'])},'tools':w.tool_hashes,'cache':{k:v for k,v in w.state.items() if k in ['physics','pool_tests']},'build_actions':w.actions,'reused':w.reused}
        (E/'build-manifest.json').write_text(json.dumps(manifest,indent=2))
        for name,cmd in [('unit',[sys.executable,'-m','unittest','test_g6_p8','-v']),('collisions',[str(pool),'--case','collisions','--quick']),('energy',[str(pool),'--case','energy','--quick'])]:
            with (E/(name+'.log')).open('wb') as log:p=subprocess.run(cmd,cwd=R,stdout=log,stderr=subprocess.STDOUT,timeout=30)
            results['regressions'].append({'name':name,'exit':p.returncode});assert p.returncode==0,name+' regression failed'
        for name,n,fixture in [('small-pool',16,13),('medium-islands',1024,10),('large-distributed',8192,10)]:
            path=E/(name+'.json');cmd=[str(physics),'--n',str(n),'--fixture',str(fixture),'--contacts',str(256 if fixture==13 else n*12),'--pairs',str(256 if fixture==13 else n*8),'--flags','7' if fixture==13 else '4','--cell-mode','1','--seconds','30','--out',str(path)]
            before=time.monotonic()
            with (E/(name+'.log')).open('wb') as log:
                try:p=subprocess.run(cmd,cwd=R,stdout=log,stderr=subprocess.STDOUT,timeout=45);code=p.returncode
                except subprocess.TimeoutExpired:code=-1
            rows=[];raw=path.with_suffix('.json.jsonl')
            if raw.exists():
                for line in raw.read_text().splitlines():
                    try:rows.append(json.loads(line))
                    except json.JSONDecodeError:break
            cleanup=json.loads(path.read_text()) if path.exists() else {'status':'FAIL','reason':'timeout or crash before checked cleanup'}
            summary=summarize(rows,cleanup,code);summary.update(name=name,command=cmd,process_wall_s=time.monotonic()-before)
            results['scenarios'].append(summary)
            # Failed process returns immediately; it is never retried or allowed to run out the session.
            with (E/(name+'.csv')).open('w',newline='') as f:
                writer=csv.writer(f);writer.writerow(['tick','elapsed_s','accepted','valid','contacts','islands','largest','active','solved_bodies','gpu_tick_us','cpu_record_us','cpu_submit_us','blocking_us','verification_us','wall_tick_us','energy','kkt_ratio','committed','allocations','dxgi_usage','error_flags'])
                for r in rows:
                    if r['type']=='TICK':writer.writerow([r['tick'],r['elapsed_s'],r['accepted'],r['valid'],r['contacts'],r['islands'],r['largest'],r['active'],r['solved_bodies'],r['gpu_us'][39],r['cpu_record_us'],r['cpu_submit_us'],r['blocking_us'],r['verification_us'],r['wall_tick_us'],r['energy'],r['independent']['residual_ratio'] if fixture!=13 else None,r['memory']['committed'],r['memory']['allocations'],r['memory']['usage'],r['error_flags']])
        good=[s for s in results['scenarios'] if s['status']=='PASS'];results['maximum_reliable_tested_n']=max((s['n'] for s in good),default=None);results['status']='PASS' if len(good)==3 else 'LIMITED / FAILURES RECORDED'
    except Exception as e:results['status']='FAIL';results['error']=repr(e)
    finally:
        lock.unlink();(E/'results.json').write_text(json.dumps(results,indent=2))
    print('scenario result N accepted/rejected contactTicks maxContacts islands/Lmax ticks/s GPU-p50/p95/p99-ms')
    for s in results['scenarios']:print(s['name'],s['status'],s['n'],f"{s['accepted_ticks']}/{s['rejected_ticks']}",s['contact_ticks'],s['max_contacts'],f"{s['max_islands']}/{s['largest_island']}",round(s['accepted_ticks_per_s'] or 0,2),[round((s['gpu_tick_us'][k] or 0)/1000,4) for k in ['p50','p95','p99']])
    print(results['status'],'maximum reliable tested N',results.get('maximum_reliable_tested_n'),'; G6 NOT QUALIFIED; evidence',E)
    return 0 if results['status']=='PASS' else 1
if __name__=='__main__':sys.exit(main())
