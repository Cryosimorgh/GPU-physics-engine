"""Bounded evidence completion after the three sustained repeats; no rerun of them."""
from pathlib import Path
import json,subprocess,sys,time
from dev_test import Workflow,digest
R=Path(__file__).resolve().parent;E=R/'evidence/g6-p8b'
def main():
    prior=json.loads((E/'results.json').read_text());assert prior['target_status']=='PASS'
    out=E/'completion-build';out.mkdir(exist_ok=True);w=Workflow(out);records=[]
    resume='--resume-suite' in sys.argv
    if (E/'completion.json').exists() and not resume:raise SystemExit('Preserve existing completion evidence: use a fresh isolated checkout')
    if resume:
        saved=json.loads((E/'completion.json').read_text())
        assert saved['first_failure']=='broader-g6' and all(x['exit']==0 for x in saved['tests'][:-1])
        assert saved['pool_tests_sha256']==digest(R/'zig-out/bin/pool_tests.exe') and saved['pool_tests_source_sha256']==digest(R/'pool_tests.zig')
        records.extend(dict(x,reused_completed_evidence=True) for x in saved['tests'][:-1])
    def run(name,cmd,timeout=90):
        start=time.monotonic()
        with (E/(name+'.log')).open('wb') as f:p=subprocess.run(list(map(str,cmd)),cwd=R,stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
        records.append(dict(name=name,command=list(map(str,cmd)),exit=p.returncode,wall_s=time.monotonic()-start))
        if p.returncode:raise RuntimeError(name)
    result={'status':'FAIL','tests':records,'G6':'BLOCKED / NOT QUALIFIED'}
    try:
        pool=w.gpu('pool_tests');physics=w.gpu('physics')
        result['pool_tests_sha256']=digest(pool);result['pool_tests_source_sha256']=digest(R/'pool_tests.zig')
        result['physics_sha256']=digest(physics)
        if not resume:
            run('rail-numerical',[pool,'--quick','--debug','--case','rails'])
            run('rail-units',[sys.executable,'-m','unittest','test_pool_rail_gap.py','-v'])
            for fixture,flags in [(1,0),(9,4)]:
                name=f'default-fixture-{fixture}'
                run(name,[physics,'--n','32','--fixture',fixture,'--flags',flags,'--steps','4','--contacts','256','--pairs','256','--verify-every-tick','--out',E/(name+'.json')])
                data=json.loads((E/(name+'.json')).read_text());assert data['status']=='PASS' and data['validation_errors']==0
        # Reuse P6 unchanged cases. Make its existing failure collection fail-fast
        # to obey P8b's stop-on-first-failure policy; retain the executed script.
        source=(R/'run_g6_p6.py').read_text()
        needle="if item['status']!='PASS':failures.append(name)"
        assert needle in source
        source=source.replace(needle,"if item['status']!='PASS':\n   failures.append(name);raise RuntimeError('P8b stop after first G6 failure: '+name)")
        source=source.replace("OUT=ROOT/'evidence/g6-p6'","OUT=ROOT/'evidence/g6-p8b/broader-g6'")
        source='import sys\nsys.path.insert(0,'+repr(str(R))+')\n'+source
        script=E/'bounded-g6-script.py';script.write_text(source)
        result['existing_suite_source_sha256']=digest(R/'run_g6_p6.py');result['executed_suite_sha256']=digest(script)
        run('broader-g6',[sys.executable,script],300)
        result['status']='PASS'
    except Exception as ex:result['first_failure']=str(ex)
    finally:
        result['builds']=w.actions;result['reused']=w.reused
        (E/'completion.json').write_text(json.dumps(result,indent=2))
        print(json.dumps({'status':result['status'],'tests':[(r['name'],r['exit']) for r in records],'first_failure':result.get('first_failure')},indent=2))
    return result['status']!='PASS'
if __name__=='__main__':raise SystemExit(main())
