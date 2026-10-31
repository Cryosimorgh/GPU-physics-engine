"""Offline evidence aggregation after fail-fast P9; does not execute GPU work."""
from pathlib import Path
import collections,csv,hashlib,json,struct,subprocess
from run_g6_p9 import compare,read_rows
from analyze_g6_p8 import distribution,stages
from isolate_g6_p9 import extract
from profile_islands import member_offset
R=Path(__file__).resolve().parent;E=R/'evidence/g6-p9'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    d=json.loads((E/'results.json').read_text());diag=json.loads((E/'isolation/result.json').read_text())
    assert d['functional']=='FAIL / INCOMPLETE' and d['first_failure']=='medium: state repeatability failure at tick 32'
    assert diag['status']=='LOCALIZED' and diag['same_input'] and diag['same_contact_set']
    a=extract(E/'isolation/trace-0.json');b=extract(E/'isolation/trace-1.json');changes=[];fields=collections.Counter();max_delta=0
    changed_roots={r for r in a['roots'] if a['roots'][r]['passes']!=b['roots'][r]['passes']}
    payload=a['payload'];meta=Path(str(E/'isolation/trace-0.json')+'-meta-33.bin').read_bytes()
    for i in range(1024):
        for f in range(16):
            at=64*i+4*f;xb=a['state'][at:at+4];yb=b['state'][at:at+4]
            if xb!=yb:
                x=struct.unpack('<f',xb)[0];y=struct.unpack('<f',yb)[0]
                root=struct.unpack_from('<I',meta,member_offset('PARENT',payload['capacity'],i))[0]
                assert root in changed_roots
                fields[f]+=1;max_delta=max(max_delta,abs(x-y));changes.append(dict(body=i,field=f,root=root,A=x,B=y))
    assert len(changes)==48 and set(fields)=={2}
    result={'gate':'G6-P9','verdict':'BLOCKED: production bitwise state repeatability not established','G5':'DEFERRED','G6':'NOT QUALIFIED','GPU-02':'UNVERIFIED','main_base':'e843a42','P8b':'CORRECTED / MERGED PR #5','physics_source_changed':False,'failure':d['first_failure'],'diagnosis':{'same_physical_input':True,'same_exact_contact_set':True,'color_order_changed_islands':len(changed_roots),'changed_physical_fields':dict(fields),'maximum_velocity_difference_m_s':max_delta,'all_different_fields_belong_to_changed_color_islands':True,'differences':changes,'cause':'InterlockedAdd contact scatter orders per-root contact lists nondeterministically; greedy coloring changes arithmetic order and tolerance-bounded stopping. Native PGS is not bitwise reproducible on coupled pair/rail contacts.','not_a_KKT_acceptance_failure':True,'independent_residual_ratio_at_first_difference':0.7272727272727273,'source_citations':['physics.hlsl:121-127 contact scatter, including atomic cursor at125','physics.hlsl:130 greedy per-root contact coloring','projected_solver.hlsl:177 FP64-to-FP32 state storage','physics.hlsl:205 immutable accepted-state publication'],'existing_canonical_tool_boundary':'measurement-schedule.hlsl allows only its bounded single-island fixture0 flags0/2 envelope; not used or expanded for fixture10 multi-island rail workloads'},'scenarios':d['scenarios'],'fresh_regressions':[x['name'] for x in d['tests'] if not x['name'].startswith(('pool-0','pool-1','medium-0','medium-1'))],'not_run':['8192-body P9 sessions, both repeats','P9 native device cases0..7','P9 blocking/nonblocking GPU consumer integration cases','P9 pending-generation, publication and work-ownership CLI suites','P9 final non-pool CLI regression','GUI/display/ETW; physical hardware-loss recovery; full formal G6 qualification'],'archive_comparisons':{},'timing_comparisons':{},'ownership_scope':'Fresh pool ownership fence test, all four sustained rollback/cleanup probes and allocation tracking passed. Full P1-P6 suites remain archived evidence only in P9.','functional_boundary':'All four executed 30-second sessions passed their physics validation, energy, state integrity, rollback and cleanup. P9 overall fails the requested bitwise repeatability criterion and stops before 8K.','performance_boundary':'GPU and physics-API budgets and verification-inclusive intervals are counted separately at dt=1/128, 7812.5us. Verification-inclusive cadence is not production-only throughput or hard-real-time qualification.','maximum_fresh_functionally_tested_n':1024,'maximum_fresh_bitwise_repeatable_n':16,'prior_tested_n_not_rerun':8192,'next_P10':'Resolve the scoped multi-island reproducibility contract without relaxing KKT, changing solver equations or resuming G5 optimization; then rerun the paused P9 8K/lifecycle checks. Release approval is not next.'}
    baseline_build=json.loads((E/'reference/evidence/g6-p8b/results.json').read_text())['provenance']
    assert d['build']['shaders']==baseline_build['shaders']
    result['all_85_default_shaders_identical_to_P8b']=True
    result['binary_identical_to_P8b']=d['build']['binaries']['physics.exe']==baseline_build['binary_sha256']['physics.exe']
    for scene in ['pool','medium']:
        ref=E/'reference'/('evidence/g6-p8b/sustained-0.json.jsonl' if scene=='pool' else 'evidence/g6-p8/medium-islands.json.jsonl')
        old=read_rows(ref);new=read_rows(E/(scene+'-0.json.jsonl'))
        result['archive_comparisons'][scene]=compare(old,new)
        aa=[r for r in old if r['type']=='TICK'];bb=[r for r in new if r['type']=='TICK'];common=min(len(aa),len(bb));aa=aa[:common];bb=bb[:common]
        result['timing_comparisons'][scene]={'matched_tick_count':common,'state_prefix_equal':result['archive_comparisons'][scene]['bitwise_equal'],'reference':'P8b' if scene=='pool' else 'P8','reference_gpu_us':distribution([r['gpu_us'][39] for r in aa]),'P9_gpu_us':distribution([r['gpu_us'][39] for r in bb]),'interpretation':'Same tick indices; medium state/order differs, so not a deterministic arithmetic A/B performance test. No code-change speedup claim.'}
    result['bottleneck_measurements']=[]
    for scenario in d['scenarios']:
        ts=[r for r in read_rows(E/(scenario['name']+'.json.jsonl')) if r['type']=='TICK']
        stage={name:distribution([stages(r['gpu_us'])[name] for r in ts]) for name in ['prepare','discovery','contacts','graph','solver','validation','publication']}
        item={'name':scenario['name'],'dominant_gpu_stage_p50':max(stage,key=lambda k:stage[k]['p50']),'stages':stage,'CPU_fence_blocking_us':distribution([r['blocking_us'] for r in ts]),'verification_us':distribution([r['verification_us'] for r in ts]),'oracle':scenario['kkt_scope'],'fixed_step_gpu_misses':scenario['deadline_misses']['gpu_tick'],'fixed_step_verification_inclusive_misses':scenario['deadline_misses']['verification_inclusive_interval']}
        result['bottleneck_measurements'].append(item)
    result['synchronization_scope']={'physics_wait':'physics.c:108 blocking_us measures s_wait before timestamp decode','post_tick_verification':'sustained_physics.zig:state plus physics_verify.c:75-76 five snapshots and physics_verify.c:130 spatial diagnostics. ph_read and ph_spatial_diagnostics submit/read back/wait (physics.c:110,138). verification_us aggregates CPU work and extra waits; no isolated hardware barrier counter.','GPU_tick':'physics.c:93-94 stamp39 follows state_record_copy; publication copy included'}
    original=json.loads((E/'original-workspace.json').read_text());root=Path(original['root'])
    assert subprocess.check_output(['git','status','--porcelain'],cwd=root).decode().splitlines()==original['status']
    assert all(digest(root/n)==h for n,h in original['hashes'].items())
    result['original_worktree_preserved']=True
    (E/'decision.json').write_text(json.dumps(result,indent=2))
    with (E/'summary.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['case','functional','ticks','GPU_p50_us','GPU_p95_us','GPU_p99_us','CPU_record_p50_us','CPU_submit_p50_us','CPU_fence_p50_us','verification_p50_us','GPU_misses','API_misses','interval_misses','committed_bytes'])
        for s in d['scenarios']:w.writerow([s['name'],s['status'],s['accepted_ticks'],*[s['gpu_tick_us'][q] for q in ['p50','p95','p99']],s['cpu_record_us']['p50'],s['cpu_submit_us']['p50'],s['blocking_us']['p50'],s['verification_us']['p50'],*[s['deadline_misses'][k] for k in ['gpu_tick','physics_api','verification_inclusive_interval']],s['memory']['committed']['max']])
    print(json.dumps({'verdict':result['verdict'],'largest_fresh_functional_n':1024,'largest_repeatable_n':16,'changed_islands':len(changed_roots),'max_velocity_delta':max_delta,'shaders_identical':True,'original_preserved':True}))
if __name__=='__main__':main()
