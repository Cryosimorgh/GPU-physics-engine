"""Bounded component diagnostics for sweep_g5.py --profile-global; no new solver."""
import csv
import datetime
import json
import math
import os
from pathlib import Path
import re
import shutil
import statistics
import sys

import struct
from dev_test import ROOT, Workflow, sdk, dependencies
from profile_islands import digest
from sweep_g5 import build_variants, execute, fixture, require, summarize, SOLVERS


def linear_fit(points):
    x = statistics.mean(p[0] for p in points)
    y = statistics.mean(p[1] for p in points)
    variance = sum((a-x)**2 for a, _ in points)
    require(variance > 0, 'iteration fit needs distinct budgets')
    slope = sum((a-x)*(b-y) for a, b in points)/variance
    return dict(us_per_iteration=slope, intercept_us=y-slope*x,
                note='empirical complete-solver slope/intercept; not an additive decomposition')


def read_counts(row):
    payload = json.loads(Path(row['raw_json']).read_text())
    arena = Path(row['raw_json']+'-contacts-1.bin').read_bytes()
    record = struct.unpack_from('<14I', arena, 80*(payload['contact_capacity']-1))
    require(record[:2] == (0x4735434e, 1), 'missing logical-access counters')
    mode,n,gets,puts,rebuilds,restarts,it,policy,cache,synthetic,colors,count = record[2:]
    require(n==payload['n'] and it==payload['total_iterations'] and count==row['proof']['actual_contacts'],
            'counter/physics telemetry mismatch')
    distribution = {}
    for k in range(count):
        color = struct.unpack_from('<I', arena, 80*k+52)[0]
        distribution[color] = distribution.get(color, 0)+1
    batches = sum((v+127)//128 for v in distribution.values())
    # These are logical full-Body source accesses. The compiler may eliminate
    # fields; coalescing, cache hits, DRAM transactions and stalls are UNVERIFIED.
    logical_global_velocity_bytes = 24*(n + (gets+puts if mode==0 else n))
    return dict(mode=mode, n=n, body_gets=gets, body_puts=puts, rebuilds=rebuilds,
                restarts=restarts, iterations=it, policy=policy, cache=cache,
                logical_full_body_global_velocity_bytes=logical_global_velocity_bytes,
                free_velocity_read_bytes=12*n*(rebuilds+restarts),
                color_batches=batches, colors=colors,
                device_barriers=batches*(it+rebuilds)+it+2*rebuilds+2*restarts+2,
                group_barriers=8*(it+rebuilds)+2,
                counter_instrumentation_excluded_from_barrier_model=True,
                hardware_transactions_and_stall_time='UNVERIFIED')


def shared_bytes(disassembly):
    """Read compiler-emitted simple scalar/vector LLVM shared arrays/scalars."""
    total = 0
    for line in disassembly.splitlines():
        if 'addrspace(3) global' not in line:
            continue
        match = re.search(r'addrspace\(3\) global\s+(.*?)(?:,\s*align|\s+(?:undef|zeroinitializer|0)(?:,|$))', line)
        require(match is not None, 'unrecognized DXIL shared declaration')
        type_text = match[1]
        base = 8 if 'double' in type_text or 'i64' in type_text else 4
        factors = [int(n) for n in re.findall(r'[\[<](\d+) x', type_text)]
        total += base*math.prod(factors)
    require(total > 0, 'DXIL shared memory declarations missing')
    return total


def cache_balance(summary):
    base = {(r['topology'],r['n']):r for r in summary if r['solver']=='Adaptive'}
    candidate = {(r['topology'],r['n']):r for r in summary if r['solver']=='CachedP4'}
    valid = base.keys()==candidate.keys() and len(base)==10 and all(
        base[k]['converged']==candidate[k]['converged']==base[k]['samples']==candidate[k]['samples'] for k in base)
    if not valid:
        return dict(retain=False, reason='lost/absent matched convergence')
    ratios = {f'{k[0]}-{k[1]}':candidate[k]['gpu_p50_us']/base[k]['gpu_p50_us'] for k in base}
    geometric = math.exp(statistics.mean(math.log(r) for r in ratios.values()))
    total = sum(r['gpu_p50_us'] for r in candidate.values())/sum(r['gpu_p50_us'] for r in base.values())
    return dict(retain=geometric<=1 and total<=1 and ratios['chain-1024']<1,
                geometric_mean_ratio=geometric, sum_p50_ratio=total, per_fixture_ratios=ratios)


def run(mode, resume=None):
    samples, timeout = (2,20) if mode=='quick' else (5,45)
    out = resume.resolve() if resume else ROOT/'dev-test-results'/('g5-global-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True,exist_ok=bool(resume))
    if resume:
        failure = json.loads((out/'failure.json').read_text())
        require(not failure['runs'] and not failure['probes'] and not (out/'results.json').exists(),
                'setup-only resume cannot repeat completed GPU cases')
        shutil.copy2(out/'failure.json',out/'setup-failure.json')
        shutil.copy2(out/'unit-tests.log',out/'setup-unit-tests.log')
    workflow = Workflow(out)
    lock = workflow.cache/'running.lock'
    fd = os.open(lock, os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    os.write(fd,str(os.getpid()).encode());os.close(fd)
    source_hashes = {n:digest(ROOT/n) for n in dependencies(['physics.hlsl','physics_main.zig','physics.c','physics_verify.c','runtime.c'])}
    runs, probes = [],[]
    try:
        workflow.run('unit-tests',[sys.executable,'-m','unittest','test_sweep_g5','test_global_profile','-q'],timeout=30)
        variants = build_variants(workflow)
        def specialize(name, policy, cache=0, sync=0, counts=0):
            binary = workflow.cache/'g5-sweep'/f'global-{name}.dxil'
            command = [sdk()[1],'-T','cs_6_0','-Gis','-E','ph_solve',
                       '-D',f'G5_RELAXATION_POLICY={policy}','-D',f'G5_BODY_CACHE={cache}',
                       '-D',f'G5_SYNC_PROBE={sync}','-D',f'G5_PROFILE_COUNTS={counts}',
                       '-Fo',binary,ROOT/'physics.hlsl']
            workflow.build('g5-global-'+name,['physics.hlsl'],[binary.relative_to(ROOT).as_posix()],command)
            directory = workflow.cache/'g5-sweep'/name
            directory.mkdir(exist_ok=True)
            for asset in variants['PGS']['sha256']:
                source = binary if asset=='ph_solve.dxil' else Path(variants['PGS']['exe']).parent/asset
                destination = directory/asset
                if not destination.exists() or digest(source)!=digest(destination):shutil.copy2(source,destination)
            variants[name] = dict(exe=str(directory/'physics.exe'),sha256={p.name:digest(p) for p in directory.iterdir() if p.is_file()})
        specialize('CachedP4',4,cache=1)
        specialize('SyncFloor',0,sync=1)
        specialize('GlobalCounts',4,counts=1)
        specialize('CachedCounts',4,cache=1,counts=1)
        specialize('GlobalPolicy2',2)
        for policy in (0,1,2,3):specialize(f'CachedPolicy{policy}',policy,cache=1)
        # All compilation completes before any GPU workload. Capture compiler
        # evidence without running a GUI/profiler application.
        for name in ('Adaptive','CachedP4','SyncFloor'):
            workflow.run('dxil-'+name,[sdk()[1],'-dumpbin',str(Path(variants[name]['exe']).parent/'ph_solve.dxil')])
        shared = shared_bytes((out/'dxil-CachedP4.log').read_text())
        require(shared<=32768, 'D3D12 shared-memory API bound exceeded')
        for filename in ('g5-nsys-help.txt','g5-nsys-metrics-help.txt'):
            path = workflow.cache/filename
            if path.exists():shutil.copy2(path,out/filename)
        shutil.copy2(ROOT/'projected_solver.hlsl',out/'tested-projected_solver.hlsl')
        prepared = []
        for topology in ('chain','branching','dense','oblique'):
            for n in ([16,64,256,1024] if topology=='chain' else [64,256]):
                path = out/f'{topology}-{n}.bin'
                description, expected = fixture(topology,n,path)
                prepared.append((topology,n,path,expected,description))
        chain = next(r for r in prepared if r[:2]==('chain',1024))
        def probe(name, exe, budget, sample=0, n=1024, path=None, expected=None, idle=False):
            row = execute(exe,out,'chain',n,name,sample,path or chain[2],
                          chain[3] if expected is None else expected,timeout,iterations=budget,idle=idle)
            row['diagnostic_iteration_budget']=budget
            probes.append(row)
            (out/'profile-progress.json').write_text(json.dumps(probes,indent=2))
            require(row['status']!='TIMEOUT','GPU diagnostic timeout; no further GPU work admitted')
            return row
        for budget in (1,128,512,1024):
            for sample in range(samples):probe('FullPGS'+str(budget),variants['PGS']['exe'],budget,sample)
        for budget in (128,512):
            for sample in range(samples):probe('SyncFloor'+str(budget),variants['SyncFloor']['exe'],budget,sample)
        idle_path = out/'idle-1024.bin'
        idle_data = bytearray(chain[2].read_bytes())
        for i in range(1024):
            struct.pack_into('<f',idle_data,64*i,2*struct.unpack_from('<f',idle_data,64*i)[0])
            for field in (2,3,5,10):struct.pack_into('<f',idle_data,64*i+4*field,0)
        idle_path.write_bytes(idle_data)
        for sample in range(samples):probe('EmptyQueue',variants['PGS']['exe'],1,sample,path=idle_path,expected=set(),idle=True)
        # Profile failures are explicit; they do not become successful physics.
        require(all(r['status']=='REJECTED' if r['solver']!='EmptyQueue' else r['status']=='CONVERGED' for r in probes),
                'unexpected component diagnostic status; see saved logs')
        slope = linear_fit([(r['proof']['solver_iterations'],r['gpu_stage_us']['solver']) for r in probes if r['solver'].startswith('FullPGS')])
        solvers = (*SOLVERS,'CachedP4')
        for topology,n,path,expected,_ in prepared:
            for sample in range(samples):
                for solver in (solvers if sample%2==0 else solvers[::-1]):
                    row = execute(variants[solver]['exe'],out,topology,n,solver,sample,path,expected,timeout)
                    runs.append(row)
                    (out/'progress.json').write_text(json.dumps(runs,indent=2))
                    require(row['status']!='TIMEOUT','GPU benchmark timeout; no further work admitted')
        counts = {}
        for name in ('GlobalCounts','CachedCounts'):
            row = probe(name,variants[name]['exe'],4096)
            require(row['status']=='CONVERGED','instrumented physics failed')
            counts[name] = read_counts(row)
        old = probe('GlobalPolicy2',variants['GlobalPolicy2']['exe'],4096)
        policy_checks = []
        for policy in (0,1,2,3):
            row = probe(f'CachedPolicy{policy}',variants[f'CachedPolicy{policy}']['exe'],4096)
            expected_status = 'REJECTED' if policy in (0,2) else 'CONVERGED'
            policy_checks.append(dict(policy=policy,status=row['status'],expected=expected_status,pass_check=row['status']==expected_status))
        boundary = out/'chain-1025.bin'
        _,boundary_pairs = fixture('chain',1025,boundary)
        row = probe('CacheBoundary1025',variants['CachedCounts']['exe'],1,n=1025,path=boundary,expected=boundary_pairs)
        boundary_counts = read_counts(row)
        require(boundary_counts['mode']==0 and row['status']=='REJECTED' and row['proof']['rollback_verified'],
                'oversized island did not use safe global fallback')
        summary,regressions = summarize(runs)
        balance = cache_balance(summary)
        correct = all(r['pass_check'] for r in policy_checks) and old['status']=='REJECTED' and all(
            r['status']=='CONVERGED' for r in runs if r['solver']=='CachedP4')
        decision = 'RETAIN_OPT_IN' if correct and balance['retain'] else 'REJECT'
        require(source_hashes=={n:digest(ROOT/n) for n in source_hashes},'source mutated during batch')
        sync = {str(b):statistics.median(r['gpu_stage_us']['solver'] for r in probes if r['solver']==f'SyncFloor{b}') for b in (128,512)}
        dispatch = statistics.median(r['gpu_stage_us']['solver'] for r in probes if r['solver']=='EmptyQueue')
        result = dict(mode=mode,qualification=False,production_policy=1,body_cache_default=0,decision=decision,
                      source_sha256=source_hashes,builds=variants,build_actions=workflow.actions,
                      samples=samples,iterations_limit=4096,probes=probes,runs=runs,summary=summary,
                      policy_checks=policy_checks,cache_balance=balance,shared_bytes_from_dxil=shared,
                      iteration_fit=slope,synchronization_reduction_floor_us=sync,empty_queue_solver_interval_us=dispatch,
                      logical_counts=counts,boundary_counts=boundary_counts,
                      hardware_counters='UNVERIFIED: Nsight Systems GPU metrics denied by GPU counter permissions; CLI log preserved',
                      caveats=['Synchronization probe is a synthetic lower-cost counterfactual, not an accepted solve or additive wall-time share.',
                               'Logical bytes count full Body source accesses; compiler dead loads, cache hits, physical transactions and memory-stall time are not measured.',
                               'PGS diagnostic budget exhaustion and synthetic sync probes must reject and roll back.',
                               'Two samples per case; p95 is the maximum, not a tail claim.'],regressions=regressions)
        (out/'results.json').write_text(json.dumps(result,indent=2))
        for filename,rows in [('results.csv',[{k:v for k,v in r.items() if k!='gpu_stage_p50_us'} for r in summary]),
                              ('profile.csv',[dict(name=r['solver'],budget=r['diagnostic_iteration_budget'],sample=r['sample'],status=r['status'],
                                                   solver_us=r.get('gpu_stage_us',{}).get('solver'),total_us=r.get('gpu_stage_us',{}).get('total'),
                                                   cpu_submit_us=r.get('cpu_submit_us')) for r in probes])]:
            with (out/filename).open('w',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        print('Fixture       N  P4 GPU p50/p95 ms  Cached GPU p50/p95 ms  iterations P4/cache  CPU submit p50 us P4/cache')
        for topology,n in [(r[0],r[1]) for r in prepared]:
            a=next(r for r in summary if (r['topology'],r['n'],r['solver'])==(topology,n,'Adaptive'))
            b=next(r for r in summary if (r['topology'],r['n'],r['solver'])==(topology,n,'CachedP4'))
            print(f"{topology:10} {n:4} {a['gpu_p50_us']/1000:.2f}/{a['gpu_p95_us']/1000:.2f}           {b['gpu_p50_us']/1000:.2f}/{b['gpu_p95_us']/1000:.2f}            {a['iterations']}/{b['iterations']}                 {a['cpu_p50_us']:.0f}/{b['cpu_p50_us']:.0f}")
        print('Iteration slope/intercept:',json.dumps(slope))
        print('Synchronization/reduction floor:',sync,'Empty-queue solver interval us:',dispatch)
        print('Logical body traffic and barrier counts:',json.dumps(counts))
        print('Shared bytes:',shared,'Policy checks:',policy_checks,'Decision:',decision,'Balance:',balance)
        print('Evidence:',out)
        return 0 if decision=='RETAIN_OPT_IN' else 1
    except Exception as error:
        (out/'failure.json').write_text(json.dumps(dict(error=str(error),runs=runs,probes=probes),indent=2))
        raise
    finally:
        lock.unlink()
