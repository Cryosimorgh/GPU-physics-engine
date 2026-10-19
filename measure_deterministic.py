"""One bounded deterministic-scheduling A/A batch using existing GPU CLI/audits."""
from collections import defaultdict, Counter
import argparse
import csv
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import struct
import subprocess
import sys

from dev_test import ROOT, Workflow, sdk, compiler, headers, dependencies
from measure_repeatability import BASELINE_SHADER, extract, stats, digest
from sweep_g5 import execute, fixture, require

ENTRIES=('ph_admit_round','ph_members','ph_contact_scatter','ph_color_ranges')
POLICIES={0:'PGS',1:'SOR1.995',2:'Policy2',3:'Policy3',4:'Adaptive'}

def timing(row):
    raw=json.loads(Path(row['raw_json']).read_text())
    q=raw['gpu_cumulative_us'][0]
    values={name:q[41+2*i]-q[40+2*i] for i,name in enumerate(ENTRIES)}
    require(all(v>=0 for v in values.values()),'invalid schedule timestamps')
    values['total_us']=sum(values.values())
    return values

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume-setup',type=Path,help='reuse prepared build after a zero-GPU-case setup failure')
    args=parser.parse_args()
    out=args.resume_setup.resolve() if args.resume_setup else ROOT/'dev-test-results'/('g5-deterministic-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    if args.resume_setup:
        failure=json.loads((out/'failure.json').read_text())
        require(not failure['runs'] and not failure['rejections'] and not (out/'results.json').exists(),'setup resume cannot repeat completed GPU work')
        archived_failure=out/('setup-failure-'+str(len(list(out.glob('setup-failure*.json')))+1)+'.json')
        shutil.copy2(out/'failure.json',archived_failure)
    else:out.mkdir(parents=True)
    w=Workflow(out)
    lock=w.cache/'running.lock';fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(fd,str(os.getpid()).encode());os.close(fd)
    runs=[];rejections=[]
    try:
        require(digest(ROOT/'projected_solver.hlsl')==BASELINE_SHADER,'solver baseline changed')
        if not args.resume_setup:
            w.run('unit-tests',[sys.executable,'-m','unittest','test_dev_workflow','test_sweep_g5','test_global_profile','test_repeatability','test_deterministic_measure','-q'],timeout=60)
        else:
            w.run('setup-fix-unit-tests',[sys.executable,'-m','unittest','test_deterministic_measure','-q'],timeout=60)
        previous_path=max((ROOT/'dev-test-results').glob('g5-early-restart-*/results.json'),key=lambda p:p.stat().st_mtime)
        previous=json.loads(previous_path.read_text())
        # One required CLI rebuild: extra eight timestamps inside the existing
        # 64-query allocation. Same CLI bytes execute native and canonical arms.
        cli=out/'fixed-cli';cli.mkdir(exist_ok=bool(args.resume_setup))
        inputs=['physics_main.zig','runtime.c','spatial.c','physics.c','physics_verify.c','physics_tests.c']
        command=[compiler(),'build-exe',inputs[0],'-cflags','-O2','-DG5_MEASURE_TIMESTAMPS=1','--',*inputs[1:],
            '-I.',*headers(),'-ld3d12','-ldxgi','-ldxguid','-lkernel32','-lc','-O','ReleaseSafe',
            '-target','x86_64-windows-gnu','-mcpu=baseline','-femit-bin='+str(cli/'physics.exe')]
        w.build('det-measurement-cli',inputs,[(cli/'physics.exe').relative_to(ROOT).as_posix()],command)
        # Prove default-off C preprocessing preserves original production tokens.
        baseline_c=out/'baseline-physics.c';baseline_c.write_bytes(subprocess.check_output(['git','show','HEAD:physics.c']))
        preprocess=[]
        for label,path in [('baseline',baseline_c),('default',ROOT/'physics.c')]:
            _,text=w.run('preprocess-'+label,[compiler(),'cc','-E','-P','-I.',*headers(),path])
            # Workflow logs prepend a JSON command line; it is provenance, not
            # preprocessor output, and the two input filenames must differ.
            preprocess.append(''.join(text.split('\n',1)[1].split()))
        require(preprocess[0]==preprocess[1],'default production C token stream changed')
        (out/'default-c-token-proof.json').write_text(json.dumps({'identical':True,'sha256':hashlib.sha256(preprocess[0].encode()).hexdigest()},indent=2))
        builds={};compiled={}
        for mode,enabled in [('native',0),('deterministic',1)]:
            compiled[mode]={}
            for entry in ENTRIES:
                path=out/f'{mode}-{entry}.dxil'
                w.build('det-'+mode+'-'+entry,['physics.hlsl'],[path.relative_to(ROOT).as_posix()],
                    [sdk()[1],'-T','cs_6_0','-Gis','-D',f'G5_DETERMINISTIC_MEASURE={enabled}','-E',entry,'-Fo',path,ROOT/'physics.hlsl'])
                compiled[mode][entry+'.dxil']=path
                if not enabled:require(digest(path)==previous['builds']['control-4']['sha256'][entry+'.dxil'],'default shader changed '+entry)
            for policy in POLICIES:
                directory=out/f'{mode}-policy-{policy}';directory.mkdir(exist_ok=bool(args.resume_setup))
                reference=previous['builds'][f'control-{policy}']['sha256']
                old=previous_path.parent/f'control-policy-{policy}'
                for filename,expected in reference.items():
                    actual=cli/'physics.exe' if filename=='physics.exe' else compiled[mode].get(filename,old/filename)
                    if filename!='physics.exe' and filename not in compiled[mode]:require(digest(actual)==expected,'cached shader mismatch')
                    shutil.copy2(actual,directory/filename)
                builds[f'{mode}-{policy}']=dict(exe=str(directory/'physics.exe'),sha256={p.name:digest(p) for p in directory.iterdir()})
        script_names=['measure_deterministic.py','measure_repeatability.py','sweep_g5.py','test_deterministic_measure.py']
        source_names=sorted(set(dependencies(inputs+['physics.hlsl']))|set(script_names))
        sources={n:digest(ROOT/n) for n in source_names}
        (out/'prepared.json').write_text(json.dumps(dict(source_sha256=sources,builds=builds,
            scope='measurement-only, fixture 0 flags 0/2, <=1024 bodies, <=2048 contacts, one connected collision island, only first discovery graph per tick',
            no_production_default_change=True,solver_sha256=BASELINE_SHADER,
            fixed_cli_sha256=digest(cli/'physics.exe'),timing_queries='40..47 bracket admission/canonicalization, members, scatter, color ranges; included in complete tick'),indent=2))
        cases=[]
        for topology in ('chain','branching','dense','oblique'):
            for n in ([16,64,256,1024] if topology=='chain' else [64,256]):
                path=out/f'{topology}-{n}.bin';description,expected=fixture(topology,n,path)
                cases.append((topology,n,path,description,expected))
        device=None
        # Deterministic P4: four A/A pairs; all remaining policies: one pair.
        # Native P4 has one pair solely for inclusive scheduling-stage reference.
        for sample in range(8):
            for topology,n,path,description,expected in cases:
                tasks=[('deterministic',4)]
                if sample<2:tasks += [('native',4)]+[('deterministic',p) for p in (0,1,2,3)]
                for mode,policy in (tasks if sample%2==0 else tasks[::-1]):
                    require(digest(path)==description['input_sha256'],'fixture changed')
                    destination=out/'runs'/mode;destination.mkdir(parents=True,exist_ok=True)
                    row=execute(builds[f'{mode}-{policy}']['exe'],destination,topology,n,POLICIES[policy],sample,path,expected,30)
                    row.update(mode=mode,policy=policy,label='A' if sample%2==0 else 'B',sample=sample)
                    runs.append(row)
                    require(row['status'] in ('CONVERGED','REJECTED'),'execution failure: stop further GPU work')
                    row['signatures'],actual=extract(row)
                    if device is None:device=actual
                    require(actual==device,'device/driver changed')
                    row['scheduling_us']=timing(row)
                    (out/'progress.json').write_text(json.dumps(runs,indent=2))
        # Deliberately unsupported measurement shapes must reject without
        # publication. These are safety checks, not accepted simulation cases.
        for label,n in [('body-bound',1025),('two-islands',16)]:
            path=out/f'reject-{label}.bin';fixture('chain',n,path)
            if label=='two-islands':
                data=bytearray(path.read_bytes())
                for i in range(8,n):struct.pack_into('<f',data,64*i,struct.unpack_from('<f',data,64*i)[0]+4)
                path.write_bytes(data)
            dest=out/f'reject-{label}.json'
            command=[builds['deterministic-4']['exe'],'--n',str(n),'--fixture','0','--flags','0','--input',path,
                '--contacts',str(8*n),'--pairs',str(n*(n-1)//2),'--iterations','4096','--max-bodies','4096',
                '--max-work','8388608','--steps','1','--warmup','0','--trace-last','--out',dest]
            w.run('reject-'+label,command,timeout=30);raw=json.loads(dest.read_text())
            state=Path(str(dest)+'-state-1.bin').read_bytes()
            require(raw['error_flags']==64 and raw['actual_published']==0 and raw['rollback_verified'] and state==path.read_bytes() and raw['validation_errors']==0,'unsafe measurement rejection')
            rejections.append(dict(case=label,status='EXPECTED_REJECTION',error_flags=64,rollback=True,source_state_sha256=digest(path)))
        require(sources=={n:digest(ROOT/n) for n in sources},'source/measurement script changed during batch')
        require(all(b['sha256']=={n:digest(Path(b['exe']).parent/n) for n in b['sha256']} for b in builds.values()),'binary changed during batch')
        summary=[];alerts=[]
        for topology,n,_,_,_ in cases:
            selected=[r for r in runs if (r['topology'],r['n'],r['mode'],r['policy'])==(topology,n,'deterministic',4)]
            native=[r for r in runs if (r['topology'],r['n'],r['mode'],r['policy'])==(topology,n,'native',4)]
            counts={k:len({r['signatures'][k] for r in selected}) for k in
                ['contact_set','contact_order','root_order','color_assignment','color_passes','colored_stream','local_mapping','free_state','exact_dispatch_schedule','work_state_sha256','published_state_sha256']}
            require(all(v==1 for v in counts.values()),'nonrepeatable deterministic P4 input/output')
            summary.append(dict(topology=topology,n=n,samples=len(selected),signatures=counts,
                iterations=stats(r['proof']['solver_iterations'] for r in selected),gpu_us=stats(r['gpu_stage_us']['total'] for r in selected),
                solver_us=stats(r['gpu_stage_us']['solver'] for r in selected),cpu_us=stats(r['cpu_submit_us'] for r in selected),
                scheduling_us={key:stats(r['scheduling_us'][key] for r in selected) for key in selected[0]['scheduling_us']},
                native_scheduling_us=stats(r['scheduling_us']['total_us'] for r in native),
                native_gpu_us=stats(r['gpu_stage_us']['total'] for r in native)))
        for topology,n,policy in dict.fromkeys((r['topology'],r['n'],r['policy']) for r in runs if r['mode']=='deterministic'):
            selected=[r for r in runs if (r['topology'],r['n'],r['policy'],r['mode'])==(topology,n,policy,'deterministic')]
            require(len({r['status'] for r in selected})==1,'policy convergence changed on repeat')
            require(len({r['proof']['solver_iterations'] for r in selected})==1,'policy iterations changed on repeat')
            for key in ['contact_set','color_assignment','color_passes','exact_dispatch_schedule','work_state_sha256','published_state_sha256']:
                require(len({r['signatures'][key] for r in selected})==1,'policy schedule/result changed on repeat')
        result=dict(status='DETERMINISTIC_MEASUREMENT_VERIFIED_BOUNDED',qualification=False,optimization=False,source_sha256=sources,
            builds=builds,build_actions=w.actions,device=device,runs=runs,summary=summary,rejections=rejections,
            default_c_preprocessor_tokens_identical=True,production_default_shader_hashes_identical=True,
            caveats=['Canonical bounded scheduling is serial/O(C^2) and NOT a scalable production implementation.',
                'Only first-round single-connected-island fixtures in the declared envelope are accepted.',
                'Eight cold repeats per policy-4 fixture; other policies have two. No confidence/p99 or thermal-stability claim.',
                'Scheduling brackets include dispatch/UAV barriers and base bookkeeping; native delta is not pure sorting instruction time.',
                'Complete tick includes all scheduling overhead and timestamp instrumentation; no speedup claim against random native schedules.'])
        (out/'results.json').write_text(json.dumps(result,indent=2))
        with (out/'summary.csv').open('w',newline='') as f:
            flat=[dict(topology=s['topology'],n=s['n'],samples=s['samples'],iterations=s['iterations']['median'],
                gpu_min_us=s['gpu_us']['minimum'],gpu_p50_us=s['gpu_us']['median'],gpu_max_us=s['gpu_us']['maximum'],gpu_cv_pct=s['gpu_us']['cv_pct'],
                scheduling_p50_us=s['scheduling_us']['total_us']['median'],native_scheduling_p50_us=s['native_scheduling_us']['median'],
                cpu_p50_us=s['cpu_us']['median']) for s in summary]
            writer=csv.DictWriter(f,fieldnames=list(flat[0]));writer.writeheader();writer.writerows(flat)
        print('Fixture N schedules/results iterations GPU ms [min,max] CV% scheduling/native ms CPU ms')
        for s in summary:
            q=s['gpu_us'];print(f"{s['topology']:9} {s['n']:4} 1/1 {s['iterations']['median']:4.0f} {q['median']/1000:.2f}[{q['minimum']/1000:.2f},{q['maximum']/1000:.2f}] {q['cv_pct']:.2f} {s['scheduling_us']['total_us']['median']/1000:.3f}/{s['native_scheduling_us']['median']/1000:.3f} {s['cpu_us']['median']/1000:.3f}")
        print('Statuses:',dict(Counter((r['mode'],r['status']) for r in runs)),'Safety rejections:',rejections)
        print('Evidence:',out);return 0
    except Exception as error:
        (out/'failure.json').write_text(json.dumps(dict(error=str(error),runs=runs,rejections=rejections),indent=2));raise
    finally:lock.unlink()

if __name__=='__main__':raise SystemExit(main())
