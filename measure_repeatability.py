"""Bounded A/A headless repeatability batch; existing CLI, fixtures and audits."""
from collections import Counter, defaultdict
import argparse
import csv
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import struct
import sys

from dev_test import ROOT, Workflow, dependencies
from profile_islands import member_offset
from sweep_g5 import execute, fixture, require

BASELINE_SHADER = '10c5ee6541c7799119a9578b304c51f8d3de3938e2221613894bc7fae75d5c24'

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def signature(value):
    return hashlib.sha256(json.dumps(value,separators=(',',':')).encode()).hexdigest()

def ordering_signatures(contacts, root_order, groups, local, free):
    count=len(contacts)
    flat=[k for group in groups for k in group]
    require(sorted(root_order)==list(range(count)), 'root list coverage')
    require(sorted(flat)==list(range(count)), 'colored list coverage')
    assignment=[]
    for color,group in enumerate(groups):
        touched=set()
        for k in group:
            a,b=contacts[k][:2]
            require(a not in touched and b not in touched, 'same-color body conflict')
            touched.update((a,b));assignment.append((contacts[k],color))
    passes=[[contacts[k] for k in sorted(group,key=lambda k:contacts[k])] for group in groups]
    work=[[contacts[k] for k in group] for group in groups]
    return dict(contact_set=signature(sorted(contacts)),contact_order=signature(contacts),
        root_order=signature([contacts[k] for k in root_order]),
        color_assignment=signature(sorted(assignment)),color_passes=signature(passes),
        colored_stream=signature(work),local_mapping=signature(local),free_state=signature(free),
        arithmetic_schedule=signature([passes,free]),
        exact_dispatch_schedule=signature([contacts,root_order,work,local,free]),
        color_sizes=[len(g) for g in groups],color_batches=sum((len(g)+127)//128 for g in groups))

def extract(row):
    path=Path(row['raw_json']);payload=json.loads(path.read_text())
    require(payload['solver_dispatches']==1,'signature scope requires one actual solve')
    arena=Path(str(path)+'-contacts-1.bin').read_bytes()
    meta=Path(str(path)+'-meta-1.bin').read_bytes()
    cap,pairs=payload['capacity'],payload['contact_capacity']
    u32=lambda at:struct.unpack_from('<I',meta,at)[0]
    u64=lambda at:struct.unpack_from('<Q',meta,at)[0]
    count=u32(8)
    require(count==row['proof']['actual_contacts'],'contact telemetry disagreement')
    contacts=[];colors=[]
    for k in range(count):
        rec=struct.unpack_from('<20I',arena,80*k)
        # Exclude mutable iteration/color/local-index words and impulses. Keep
        # exact geometry bits, stable identities/generations, and signed gap.
        contacts.append(tuple(rec[:2]+rec[3:10]+(rec[12],)+rec[16:20]))
        colors.append(rec[13])
    def ct(name):
        pattern=rf'^#define G3_{name}\(p,i\) \(0u\+(\d+)u\*\(p\)\+(\d+)u\*\(i\)\)$'
        match=re.search(pattern,(ROOT/'physics-layout.h').read_text(),re.M)
        require(match is not None,'unknown generated arena ABI '+name)
        stride,width=map(int,match.groups())
        require(width==4,'unexpected index width')
        return stride*pairs
    at=u64(member_offset('CONTACT_START',cap))
    length=u32(member_offset('CONTACT_COUNT',cap))
    require(length==count,'root contact count disagreement')
    root_order=list(struct.unpack_from(f'<{count}I',arena,ct('ROOT_CONTACTS')+4*at))
    base=u64(member_offset('COLOR_BASE',cap));ncolors=u32(member_offset('COLORS',cap))
    require(0<ncolors<=128 and base+ncolors+1<=2*pairs,'color range bound')
    starts=list(struct.unpack_from(f'<{ncolors+1}I',arena,ct('COLOR_START')+4*base))
    require(starts[0]==at and starts[-1]==at+count and starts==sorted(starts),'color prefix coverage')
    groups=[]
    for col,(first,end) in enumerate(zip(starts,starts[1:])):
        group=list(struct.unpack_from(f'<{end-first}I',arena,ct('COLORED')+4*first))
        require(all(k<count and colors[k]==col for k in group),'color assignment disagreement')
        groups.append(group)
    local=[u32(member_offset('LOCAL',cap,i)) for i in range(payload['n'])]
    free=[[u32(member_offset('FREE_'+axis,cap,i)) for axis in ('VX','VY','OMEGA','SLEEP')] for i in range(payload['n'])]
    result=ordering_signatures(contacts,root_order,groups,local,free)
    work=b''.join(meta[member_offset('WORK_'+axis,cap,i):member_offset('WORK_'+axis,cap,i)+8]
                  for i in range(payload['n']) for axis in ('VX','VY','OMEGA'))
    result.update(work_state_sha256=hashlib.sha256(work).hexdigest(),
                  published_state_sha256=digest(Path(str(path)+'-state-1.bin')))
    return result,dict(adapter=payload['adapter'],driver=payload['driver'])

def stats(values):
    values=list(values)
    center=statistics.median(values)
    return dict(n=len(values),minimum=min(values),median=center,maximum=max(values),
        range_pct=100*(max(values)-min(values))/center if center else 0,
        cv_pct=100*statistics.pstdev(values)/statistics.mean(values) if statistics.mean(values) else 0)

def conditional(rows,key,field):
    groups=defaultdict(list)
    for r in rows:groups[key(r)].append(r)
    eligible=[g for g in groups.values() if len(g)>1]
    normalized=[r[field]/statistics.mean(x[field] for x in g) for g in eligible for r in g]
    return dict(groups=len(groups),repeated_groups=len(eligible),samples=sum(map(len,eligible)),
                pooled_within_group_cv_pct=100*statistics.pstdev(normalized) if normalized else None,
                max_within_group_range_pct=max((stats(r[field] for r in g)['range_pct'] for g in eligible),default=None))

def analyze(rows):
    summaries=[];alerts=[]
    for topology,n in dict.fromkeys((r['topology'],r['n']) for r in rows):
        selected=[r for r in rows if (r['topology'],r['n'])==(topology,n)]
        groups=defaultdict(list)
        for r in selected:groups[r['signatures']['arithmetic_schedule']].append(r)
        for sig,g in groups.items():
            if len({r['proof']['solver_iterations'] for r in g})>1 or len({r['signatures']['work_state_sha256'] for r in g})>1:
                alerts.append(dict(kind='SAME_ARITHMETIC_SCHEDULE_DIFFERENT_RESULT',topology=topology,n=n,
                    signature=sig,run_ids=[r['run_id'] for r in g]))
        row=dict(topology=topology,n=n,samples=len(selected),
            signatures={k:len({r['signatures'][k] for r in selected}) for k in
                ('contact_set','contact_order','root_order','color_assignment','color_passes','colored_stream','local_mapping','free_state','arithmetic_schedule','exact_dispatch_schedule')},
            iterations=stats(r['iterations'] for r in selected),gpu_us=stats(r['gpu_us'] for r in selected),
            solver_us=stats(r['solver_us'] for r in selected),cpu_us=stats(r['cpu_us'] for r in selected),
            colors=sorted({r['proof']['colors'] for r in selected}),batches=sorted({r['signatures']['color_batches'] for r in selected}),
            solver_us_per_iteration=stats(r['solver_us']/r['iterations'] for r in selected),
            same_arithmetic_gpu=conditional(selected,lambda r:r['signatures']['arithmetic_schedule'],'gpu_us'),
            same_exact_dispatch_gpu=conditional(selected,lambda r:r['signatures']['exact_dispatch_schedule'],'gpu_us'),
            same_iteration_batches_solver=conditional(selected,lambda r:(r['iterations'],r['signatures']['color_batches']),'solver_us'),
            aa_median_ratio=statistics.median(r['gpu_us'] for r in selected if r['label']=='B')/
                            statistics.median(r['gpu_us'] for r in selected if r['label']=='A'))
        summaries.append(row)
    return summaries,alerts

def archived_restart_evidence():
    """Compare existing traced controls offline; never submit another GPU case."""
    first=max((ROOT/'dev-test-results').glob('g5-skip-residual-*/results.json'),key=lambda p:p.stat().st_mtime)
    second=max((ROOT/'dev-test-results').glob('g5-early-restart-*/results.json'),key=lambda p:p.stat().st_mtime)
    a,b=json.loads(first.read_text()),json.loads(second.read_text())
    require(a['builds']['candidate-trace']['sha256']==b['builds']['control-trace-policy-4']['sha256'],
            'archived trace binaries differ; cannot compare as identical controls')
    evidence=[]
    for n in (64,256,1024):
        x=next(r for r in a['traces'] if r['n']==n and r['arm']=='candidate')
        y=next(r for r in b['traces'] if r['topology']=='chain' and r['n']==n and r['policy']==4 and r['arm']=='control')
        sx,_=extract(x);sy,_=extract(y)
        evidence.append(dict(n=n,binary_and_shader_hashes_identical=True,
            previous_restart=[t['iteration'] for t in x['trace'] if t['event']==8],
            later_restart=[t['iteration'] for t in y['trace'] if t['event']==8],
            previous_iterations=x['proof']['solver_iterations'],later_iterations=y['proof']['solver_iterations'],
            previous_colors=x['proof']['colors'],later_colors=y['proof']['colors'],
            same_contact_geometry=sx['contact_set']==sy['contact_set'],same_free_state=sx['free_state']==sy['free_state'],
            same_color_passes=sx['color_passes']==sy['color_passes'],
            previous_signatures=sx,later_signatures=sy,previous_raw=x['raw_json'],later_raw=y['raw_json']))
    return evidence

def write_run_csv(rows,path):
    with path.open('w',newline='') as f:
        flat=[dict(topology=r['topology'],n=r['n'],label=r['label'],pair=r['pair'],iterations=r['iterations'],
            gpu_us=r['gpu_us'],solver_us=r['solver_us'],cpu_us=r['cpu_us'],**{k:v for k,v in r['signatures'].items() if not isinstance(v,list)}) for r in rows]
        writer=csv.DictWriter(f,fieldnames=list(flat[0]));writer.writeheader();writer.writerows(flat)

def reanalyze(path):
    """Repair signatures from complete exports without repeating any GPU work."""
    raw=path.read_bytes();result=json.loads(raw)
    backup=path.with_name('results-before-dispatch-signature-fix.json')
    require(not backup.exists(),'signature repair already recorded')
    backup.write_bytes(raw)
    csv_path=path.with_name('runs.csv')
    if csv_path.exists():csv_path.rename(path.with_name('runs-before-dispatch-signature-fix.csv'))
    for row in result['runs']:
        row['signatures'],device=extract(row)
        require(device==result['device'],'saved device identity differs')
    result['summary'],result['alerts']=analyze(result['runs'])
    result['status']='INVESTIGATE_SIGNATURE_ALERT' if result['alerts'] else 'MEASURED_NO_SAME_SCHEDULE_DEFECT'
    result['archived_restart_comparison']=archived_restart_evidence()
    result['analysis_correction']='Exact-dispatch signature now includes contact-record placement and root indices. All 80 saved exports reprocessed; zero additional GPU runs. Prior analysis preserved.'
    path.write_text(json.dumps(result,indent=2))
    write_run_csv(result['runs'],csv_path)
    print('Reanalyzed',len(result['runs']),'saved exports; alerts:',result['alerts'],'GPU runs: 0')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analyze-only',type=Path,help='correct signatures from a completed results.json; no GPU execution')
    args=parser.parse_args()
    if args.analyze_only:
        reanalyze(args.analyze_only);return 0
    out=ROOT/'dev-test-results'/('g5-repeatability-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True);workflow=Workflow(out)
    lock=workflow.cache/'running.lock'
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(fd,str(os.getpid()).encode());os.close(fd)
    rows=[]
    try:
        require(digest(ROOT/'projected_solver.hlsl')==BASELINE_SHADER,'retained shader baseline differs; no experiment permitted')
        workflow.run('unit-tests',[sys.executable,'-m','unittest','test_dev_workflow','test_sweep_g5','test_global_profile','test_repeatability','-q'],timeout=60)
        reference=max((ROOT/'dev-test-results').glob('g5-early-restart-*/results.json'),key=lambda p:p.stat().st_mtime)
        old=json.loads(reference.read_text())
        directory=reference.parent/'control-policy-4';exe=directory/'physics.exe'
        assets={n:digest(directory/n) for n in old['builds']['control-4']['sha256']}
        require(assets==old['builds']['control-4']['sha256'],'cached baseline artifact mismatch')
        source={n:digest(ROOT/n) for n in dependencies(['physics.hlsl','physics_main.zig','physics.c','physics_verify.c','physics_tests.c','spatial.c','runtime.c'])}
        plan=dict(policy=4,solver_source_sha256=BASELINE_SHADER,source_sha256=source,assets=assets,
            executable=str(exe),builds=0,samples_per_fixture=8,labels='A/B are the SAME executable and shader files; not an optimization',
            scope='four paired A/A controls per fixture, AB/BA alternation, cold independent one-tick processes; no tail-latency or confidence claim')
        (out/'prepared.json').write_text(json.dumps(plan,indent=2))
        cases=[]
        for topology in ('chain','branching','dense','oblique'):
            for n in ([16,64,256,1024] if topology=='chain' else [64,256]):
                path=out/f'{topology}-{n}.bin';description,expected=fixture(topology,n,path)
                cases.append((topology,n,path,expected,description))
        device=None
        for pair in range(4):
            for topology,n,path,expected,description in cases:
                for label in (('A','B') if pair%2==0 else ('B','A')):
                    require(digest(path)==description['input_sha256'],'fixture changed before control run')
                    destination=out/label;destination.mkdir(exist_ok=True)
                    row=execute(exe,destination,topology,n,'Adaptive',pair,path,expected,20)
                    row.update(label=label,pair=pair,run_id=len(rows))
                    rows.append(row)
                    require(row['status']=='CONVERGED','unexpected repeatability rejection/error/timeout: stop further GPU work')
                    row['signatures'],actual=extract(row)
                    if device is None:device=actual
                    require(actual==device,'device/driver changed during controls')
                    row.update(fixture_sha256=description['input_sha256'],iterations=row['proof']['solver_iterations'],
                        gpu_us=row['gpu_stage_us']['total'],solver_us=row['gpu_stage_us']['solver'],cpu_us=row['cpu_submit_us'])
                    (out/'progress.json').write_text(json.dumps(rows,indent=2))
        require(source=={n:digest(ROOT/n) for n in source},'source changed during batch')
        require(assets=={n:digest(directory/n) for n in assets},'binary/shader changed during batch')
        require(all(digest(path)==description['input_sha256'] for _,_,path,_,description in cases),'fixture changed during batch')
        summary,alerts=analyze(rows)
        require(all(s['signatures']['contact_set']==s['signatures']['free_state']==1 for s in summary),'fixture geometry/free-state changed')
        result=dict(status='INVESTIGATE_SIGNATURE_ALERT' if alerts else 'MEASURED_NO_SAME_SCHEDULE_DEFECT',
            qualification=False,optimization=False,plan=plan,device=device,runs=rows,summary=summary,alerts=alerts,
            archived_restart_comparison=archived_restart_evidence(),
            limitations=['Eight cold samples per fixture, descriptive variation only, no significance or p99 claim.',
                'Same-arithmetic cohorts ignore harmless within-color order after verifying disjoint bodies.',
                'Exact-dispatch cohorts additionally match contact-record placement, root indices, colored stream, and local map; total tick can still include upstream spatial/runtime variation.',
                'Same-iteration/batch cohorts do not isolate hardware time when contact/color ordering differs.',
                'Current timing runs are uninstrumented: per-run restart counts are not measured; unchanged-restart comparisons use existing matched trace artifacts.',
                'No exact-schedule repeats means conditional execution-time uncertainty is UNVERIFIED, not zero.'])
        (out/'results.json').write_text(json.dumps(result,indent=2))
        write_run_csv(rows,out/'runs.csv')
        print('Fixture       N  contact/root/color signatures  iterations min-max  GPU median[min,max] ms  GPU CV%  B/A identical-control ratio')
        for s in summary:
            sig=s['signatures'];it=s['iterations'];gpu=s['gpu_us']
            print(f"{s['topology']:10} {s['n']:4} {sig['contact_order']:2}/{sig['root_order']:2}/{sig['color_passes']:2} "
                  f"{it['minimum']:4}-{it['maximum']:<4} {gpu['median']/1000:.2f}[{gpu['minimum']/1000:.2f},{gpu['maximum']/1000:.2f}] "
                  f"{gpu['cv_pct']:.2f} {s['aa_median_ratio']:.4f}")
        print('Status:',result['status'],'Alerts:',alerts,'GPU runs:',len(rows),'Builds: 0')
        print('Evidence:',out)
        return int(bool(alerts))
    except Exception as error:
        (out/'failure.json').write_text(json.dumps(dict(error=str(error),runs=rows),indent=2));raise
    finally:lock.unlink()

if __name__=='__main__':raise SystemExit(main())
