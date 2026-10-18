"""One matched, serialized quick batch using the recovered G5 fixtures/audits."""
import argparse
import csv
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import statistics
import sys
import zipfile

from dev_test import ROOT, Workflow, sdk, dependencies
from sweep_g5 import execute, fixture, percentile, require

POLICIES = {0:'PGS',1:'SOR1.995',2:'Policy2',3:'Policy3',4:'Adaptive'}

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def dxil_counts(text):
    return dict(buffer_loads=len(re.findall(r'call .*@dx.op.bufferLoad.i32\(',text)),
                make_double=len(re.findall(r'call .*@dx.op.makeDouble.f64\(',text)),
                barriers=len(re.findall(r'call .*@dx.op.barrier\(',text)),
                f64_arithmetic=len(re.findall(r'= f(?:add|sub|mul|div) double ',text)))

def aggregate(rows, policy4=False):
    rows = [r for r in rows if (not policy4 or r['policy']==4) and r['control_converged']==r['samples']]
    valid = bool(rows) and all(r['candidate_converged']==r['samples'] for r in rows)
    if not valid:return dict(retain=False, reason='missing or failed accepted matches')
    geo = math.exp(statistics.mean(math.log(r['candidate_gpu_p50_us']/r['control_gpu_p50_us']) for r in rows))
    total = sum(r['candidate_gpu_p50_us'] for r in rows)/sum(r['control_gpu_p50_us'] for r in rows)
    return dict(retain=geo<1 and total<1,configurations=len(rows),geometric_mean_ratio=geo,sum_p50_ratio=total)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',nargs='?',choices=['quick'],default='quick')
    parser.parse_args()
    out=ROOT/'dev-test-results'/('g5-measure-snapshot-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True)
    workflow=Workflow(out)
    lock=workflow.cache/'running.lock'
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(fd,str(os.getpid()).encode());os.close(fd)
    sources={n:digest(ROOT/n) for n in dependencies(['physics.hlsl','physics_main.zig','physics.c','physics_verify.c','physics_tests.c','spatial.c','runtime.c'])}
    runs=[]
    try:
        workflow.run('unit-tests',[sys.executable,'-m','unittest','test_dev_workflow','test_sweep_g5','test_global_profile','-q'],timeout=60)
        archive=ROOT.parent/'g5-recovery-kit/original/G5-Global-Solver-Cost-Handoff-20261018T090324676154Z.zip'
        with zipfile.ZipFile(archive) as z:original=json.loads(z.read('evidence/results.json'))
        assets=workflow.cache/'g5-sweep/PGS'
        fresh_cli=ROOT/'dev-test-results/solver-cost-inspection/fresh-control/physics.exe'
        require(fresh_cli.is_file(),'fresh unchanged same-toolchain CLI missing')
        builds={}; static={}
        for arm,enabled in [('control',0),('candidate',1)]:
            ready=out/f'{arm}-ph_ready.dxil'
            workflow.build('measure-ready-'+arm,['physics.hlsl'],[ready.relative_to(ROOT).as_posix()],
                [sdk()[1],'-T','cs_6_0','-Gis','-D',f'G5_REUSE_MEASURE_BODIES={enabled}','-D','G5_BODY_CACHE=0',
                 '-E','ph_ready','-Fo',ready,ROOT/'physics.hlsl'])
            for policy,name in POLICIES.items():
                directory=out/f'{arm}-policy-{policy}';directory.mkdir()
                for filename,expected in original['builds']['PGS']['sha256'].items():
                    if filename in ('physics.exe','ph_solve.dxil','ph_ready.dxil'):continue
                    require(digest(assets/filename)==expected,'unmatched common shader '+filename)
                    shutil.copy2(assets/filename,directory/filename)
                shutil.copy2(fresh_cli,directory/'physics.exe')
                shutil.copy2(ready,directory/'ph_ready.dxil')
                binary=directory/'ph_solve.dxil'
                command=[sdk()[1],'-T','cs_6_0','-Gis','-D',f'G5_RELAXATION_POLICY={policy}',
                    '-D','G5_BODY_CACHE=0','-D',f'G5_REUSE_MEASURE_BODIES={enabled}',
                    '-E','ph_solve','-Fo',binary,ROOT/'physics.hlsl']
                workflow.build(f'measure-{arm}-{policy}',['physics.hlsl'],[binary.relative_to(ROOT).as_posix()],command)
                if arm=='control' and name in original['builds']:
                    require(digest(binary)==original['builds'][name]['sha256']['ph_solve.dxil'],'control DXIL differs from archived '+name)
                    require(digest(ready)==original['builds'][name]['sha256']['ph_ready.dxil'],'control ready DXIL differs')
                _,text=workflow.run(f'dxil-{arm}-{policy}',[sdk()[1],'-dumpbin',binary])
                static[f'{arm}-{policy}']=dxil_counts(text)
                builds[f'{arm}-{policy}']=dict(exe=str(directory/'physics.exe'),sha256={p.name:digest(p) for p in directory.iterdir()})
        for policy in POLICIES:
            a,b=static[f'control-{policy}'],static[f'candidate-{policy}']
            require(b['barriers']==a['barriers'],'barrier count changed')
            require(b['buffer_loads']<a['buffer_loads'],'no compiled load reduction')
        # Rule declared before the first GPU case. Expected rejected attempts
        # remain explicit and cannot inflate the accepted-tick aggregate.
        rule='Retain only if all matched convergence/rejection and independent audits pass, and BOTH policy-4 and all accepted-policy aggregates improve in geometric mean and summed complete-tick p50.'
        (out/'prepared.json').write_text(json.dumps(dict(rule=rule,builds=builds,static=static,source_sha256=sources),indent=2))
        fixtures=[]
        for topology in ('chain','branching','dense','oblique'):
            for n in ([16,64,256,1024] if topology=='chain' else [64,256]):
                path=out/f'{topology}-{n}.bin';description,expected=fixture(topology,n,path);fixtures.append(description)
                for sample in range(2):
                    for policy,name in POLICIES.items():
                        for arm in (('control','candidate') if sample==0 else ('candidate','control')):
                            arm_out=out/arm;arm_out.mkdir(exist_ok=True)
                            row=execute(builds[f'{arm}-{policy}']['exe'],arm_out,topology,n,name,sample,path,expected,20)
                            row.update(arm=arm,policy=policy);runs.append(row)
                            (out/'progress.json').write_text(json.dumps(runs,indent=2))
                            require(row['status']!='TIMEOUT','GPU timeout: no further work submitted')
        rows=[]; correctness=True
        for topology,n,policy in dict.fromkeys((r['topology'],r['n'],r['policy']) for r in runs):
            groups={arm:[r for r in runs if (r['topology'],r['n'],r['policy'],r['arm'])==(topology,n,policy,arm)] for arm in ('control','candidate')}
            row=dict(topology=topology,n=n,policy=policy,samples=2)
            for arm,items in groups.items():
                row[arm+'_statuses']=[r['status'] for r in items]
                valid=all(r['status'] in ('CONVERGED','REJECTED') for r in items)
                correctness &= valid
                if not valid:continue
                correctness &= all(r['proof']['accepted_invariants_verified'] if r['status']=='CONVERGED' else r['proof']['rollback_verified'] for r in items)
                row[arm+'_converged']=sum(r['status']=='CONVERGED' for r in items)
                row[arm+'_gpu_p50_us']=statistics.median(r['gpu_stage_us']['total'] for r in items)
                row[arm+'_gpu_p95_us']=percentile([r['gpu_stage_us']['total'] for r in items],.95)
                row[arm+'_solver_us']=statistics.median(r['gpu_stage_us']['solver'] for r in items)
                row[arm+'_cpu_us']=statistics.median(r['cpu_submit_us'] for r in items)
                row[arm+'_iterations']=[r['proof']['solver_iterations'] for r in items]
                row[arm+'_colors']=[r['proof']['colors'] for r in items]
                row[arm+'_max_kkt']=max(r['proof']['kkt_ratio'] for r in items)
            correctness &= row.get('control_statuses')==row.get('candidate_statuses')
            rows.append(row)
        require(sources=={n:digest(ROOT/n) for n in sources},'source mutated during batch')
        p4=aggregate(rows,True) if correctness else dict(retain=False)
        all_policies=aggregate(rows) if correctness else dict(retain=False)
        retain=bool(correctness and p4['retain'] and all_policies['retain'])
        result=dict(decision='RETAIN' if retain else 'REJECT',qualification=False,correctness=correctness,
            rule=rule,policy4_balance=p4,all_policy_balance=all_policies,source_sha256=sources,
            static_dxil=static,builds=builds,build_actions=workflow.actions,fixtures=fixtures,runs=runs,summary=rows,
            caveats=['Two cold samples per configuration: p95 is max, not a sustained-tail or statistical claim.',
                     'Color ordering can vary. Iteration/color counts are recorded for both arms.',
                     'Static DXIL instruction sites are not physical memory transactions or stall counters.'])
        (out/'results.json').write_text(json.dumps(result,indent=2))
        with (out/'results.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        print('Policy 4: topology N GPU p50/p95 ms control -> candidate; solver ms; CPU ms; iterations')
        for r in rows:
            if r['policy']!=4:continue
            print(f"{r['topology']:9} {r['n']:4} {r['control_gpu_p50_us']/1000:.2f}/{r['control_gpu_p95_us']/1000:.2f} -> "
                  f"{r['candidate_gpu_p50_us']/1000:.2f}/{r['candidate_gpu_p95_us']/1000:.2f}; "
                  f"{r['control_solver_us']/1000:.2f}->{r['candidate_solver_us']/1000:.2f}; "
                  f"{r['control_cpu_us']/1000:.3f}->{r['candidate_cpu_us']/1000:.3f}; "
                  f"{r['control_iterations']}->{r['candidate_iterations']}")
        print('Correctness:',correctness,'Policy4:',p4,'All policies:',all_policies,'Decision:',result['decision'])
        print('DXIL policy4:',static['control-4'],'->',static['candidate-4'])
        print('Evidence:',out)
        return int(not retain)
    except Exception as error:
        (out/'failure.json').write_text(json.dumps(dict(error=str(error),runs=runs),indent=2))
        raise
    finally:lock.unlink()

if __name__=='__main__':raise SystemExit(main())
