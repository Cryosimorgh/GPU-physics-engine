"""One serialized, fail-fast headless batch. Detailed evidence stays on disk."""
from pathlib import Path
import csv,json,subprocess,time,hashlib,shutil,statistics
from dev_test import Workflow,digest,dependencies
R=Path(__file__).resolve().parent;E=R/'evidence/g6-p8b'
def rows(p):return [json.loads(x) for x in p.read_text().splitlines()]
def main():
    E.mkdir(parents=True,exist_ok=True)
    if (E/'results.json').exists():raise SystemExit('Preserve existing evidence: use a fresh isolated checkout')
    out=E/'candidate-build';out.mkdir(exist_ok=True);w=Workflow(out)
    summary={'G5':'DEFERRED','G6':'BLOCKED / NOT QUALIFIED','tests':[],'sustained':[]}
    def run(name,cmd,timeout=90):
        start=time.monotonic()
        with (E/(name+'.log')).open('wb') as f:
            try:p=subprocess.run([str(x) for x in cmd],cwd=R,stdout=f,stderr=subprocess.STDOUT,timeout=timeout);rc=p.returncode
            except subprocess.TimeoutExpired:rc='TIMEOUT'
        result=dict(name=name,command=[str(x) for x in cmd],exit=rc,wall_s=time.monotonic()-start)
        summary['tests'].append(result)
        (E/'results.json').write_text(json.dumps(summary,indent=2))
        return rc
    try:
        exe=w.gpu('physics');tests=w.gpu('pool_tests');cpu=w.cpu()
        summary['provenance']={'source_sha256':{n:digest(R/n) for n in dependencies(['physics_main.zig','pool_tests.zig','runtime.c','spatial.c','physics.c','physics_verify.c','physics_tests.c','physics.hlsl'])},'binary_sha256':{p.name:digest(p) for p in [exe,tests,cpu]},'shaders':{p.name:digest(p) for p in R.glob('*.dxil')},'tools':w.tool_hashes,'builds':w.actions,'reused':w.reused}
        for name,cmd in [('cpu',[cpu]),('rails',[tests,'--quick','--debug','--case','rails']),*[(case,[tests,'--quick','--case',case]) for case in ['idle','collisions','energy','regression','discovery','ownership']]]:
            if run(name,cmd)!=0:summary['first_failure']=name;return
        for i in range(3):
            name=f'sustained-{i}';path=E/(name+'.json')
            cmd=[exe,'--n','16','--fixture','13','--flags','7','--contacts','256','--pairs','256','--cell-mode','1','--seconds','30','--out',path]
            rc=run(name,cmd,45)
            ticks=[x for x in rows(Path(str(path)+'.jsonl')) if x['type']=='TICK']
            last=ticks[-1];cleanup=json.loads(path.read_text())
            result={'name':name,'completed_ticks':sum(x['accepted'] for x in ticks),'last':last,'cleanup':cleanup,'shots':[x['tick'] for x in ticks if x['shot']],'gpu_us_p50':statistics.median(x['gpu_us'][39] for x in ticks),'peak_committed':max(x['memory']['committed'] for x in ticks)}
            summary['sustained'].append(result)
            if rc or not cleanup['cleanup_ok'] or not all(x['valid'] for x in ticks):summary['first_failure']=name;return
        streams=[[x for x in rows(E/f'sustained-{i}.json.jsonl') if x['type']=='TICK'] for i in range(3)]
        common=min(map(len,streams));summary['determinism']={'common_ticks':common,'all_hashes_identical':all(len({stream[i]['state_hash'] for stream in streams})==1 for i in range(common))}
        if not summary['determinism']['all_hashes_identical']:summary['first_failure']='determinism';return
        summary['target_status']='PASS'
    except Exception as ex:summary['first_failure']=str(ex)
    finally:
        summary.setdefault('target_status','FAIL')
        (E/'results.json').write_text(json.dumps(summary,indent=2))
        with (E/'comparison.csv').open('w',newline='') as f:
            writer=csv.writer(f);writer.writerow(['test','exit','wall_s']);writer.writerows((x['name'],x['exit'],x['wall_s']) for x in summary['tests'])
        print(json.dumps({'status':summary['target_status'],'tests':[(x['name'],x['exit']) for x in summary['tests']],'first_failure':summary.get('first_failure'),'sustained_ticks':[x['completed_ticks'] for x in summary['sustained']]},indent=2))
if __name__=='__main__':
    main()
    raise SystemExit(json.loads((E/'results.json').read_text())['target_status']!='PASS')
