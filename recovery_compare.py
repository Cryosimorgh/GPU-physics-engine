"""Compare the completed recovery batch with archived evidence; no GPU work."""
from collections import Counter
import json
import math
from pathlib import Path, PureWindowsPath
import statistics
import zipfile

from dev_test import ROOT

out = max((ROOT/'dev-test-results').glob('g5-sweep-*/results.json'), key=lambda p:p.stat().st_mtime).parent
current = json.loads((out/'results.json').read_text())
with zipfile.ZipFile(ROOT.parent/'g5-recovery-kit/original/G5-Global-Solver-Cost-Handoff-20261018T090324676154Z.zip') as archive:
    old = json.loads(archive.read('evidence/results.json'))
inputs = {PureWindowsPath(n).name:h for n,h in old['input_sha256'].items()}
fixture_checks = {f"{f['topology']}-{f['n']}":inputs[f"{f['topology']}-{f['n']}.bin"]==f['input_sha256'] for f in current['fixtures']}
key = lambda r:(r['topology'],r['n'],r['solver'],r['sample'])
archived = {key(r):r for r in old['runs']}
discrepancies = []
color_differences = []
proof_fields = ['actual_bodies','actual_contacts','actual_islands','solver_iterations',
                'kkt_ratio','energy_before','attempted_energy_after',
                'attempted_momentum_error','rollback_verified',
                'accepted_invariants_verified','rejected','error_flags']
for row in current['runs']:
    reference = archived[key(row)]
    if row['proof']['colors'] != reference['proof']['colors']:
        color_differences.append(dict(case=key(row),old=reference['proof']['colors'],new=row['proof']['colors']))
    if row['status'] != reference['status']:
        discrepancies.append(dict(case=key(row), field='status',old=reference['status'],new=row['status']))
    for field in proof_fields:
        a,b = reference.get('proof',{}).get(field),row.get('proof',{}).get(field)
        if a!=b:
            discrepancies.append(dict(case=key(row),field=field,old=a,new=b))
previous = {(r['topology'],r['n']):r for r in old['summary'] if r['solver']=='Adaptive'}
comparison = []
for row in current['summary']:
    if row['solver']!='Adaptive':continue
    a = previous[row['topology'],row['n']]
    comparison.append(dict(topology=row['topology'], n=row['n'], iterations=row['iterations'],
        archived_gpu_p50_us=a['gpu_p50_us'],gpu_p50_us=row['gpu_p50_us'],gpu_p95_us=row['gpu_p95_us'],
        archived_solver_us=a['gpu_stage_p50_us']['solver'],solver_us=row['gpu_stage_p50_us']['solver'],
        archived_cpu_us=a['cpu_p50_us'],cpu_us=row['cpu_p50_us']))
accepted = [r for r in current['runs'] if r['status']=='CONVERGED']
rejected = [r for r in current['runs'] if r['status']=='REJECTED']
structural = {'status','actual_bodies','actual_contacts','actual_islands',
              'rollback_verified','accepted_invariants_verified','rejected','error_flags'}
structural_differences = [d for d in discrepancies if d['field'] in structural]
source_match = current['source_sha256']==old['source_sha256']
physics_pass = all(r['proof']['accepted_invariants_verified'] for r in accepted)
rollback_pass = all(r['proof']['rollback_verified'] for r in rejected)
verified = source_match and all(fixture_checks.values()) and not structural_differences and physics_pass and rollback_pass
result = dict(decision='VERIFIED_HEADLESS_SOURCE_AND_BEHAVIOR' if verified else 'MISMATCH',
    qualification=False,source_hashes_match=current['source_sha256']==old['source_sha256'],
    fixture_checks=fixture_checks,proof_fields=proof_fields,proof_discrepancies=discrepancies,
    structural_differences=structural_differences,
    color_count_differences=color_differences,
    comparison_criteria='Use unchanged sweep KKT, momentum, energy and rollback criteria. Record exact numerical differences; do not require identical trajectories or iteration counts.',
    max_iteration_difference=max((abs(d['old']-d['new']) for d in discrepancies if d['field']=='solver_iterations'),default=0),
    statuses=dict(Counter(r['status'] for r in current['runs'])),
    policy4_statuses=dict(Counter(r['status'] for r in current['runs'] if r['solver']=='Adaptive')),
    accepted_invariants=all(r['proof']['accepted_invariants_verified'] for r in accepted),
    rollback_checks=all(r['proof']['rollback_verified'] for r in rejected),
    policy4_timing=comparison,
    policy4_geomean_gpu_ratio=math.exp(statistics.mean(math.log(r['gpu_p50_us']/r['archived_gpu_p50_us']) for r in comparison)),
    binary_identity='All shader hashes match; rebuilt CLI SHA-256 differs, cause unverified. No archived executable bytes supplied.',
    sampling='Two cold samples per case; p95 is maximum of two. No performance significance claim.',
    sweep_exit_note='Exit 1 is expected because six unchanged PGS chain trials reject at 4096 iterations.',
    evidence=str(out))
(out/'recovery-comparison.json').write_text(json.dumps(result,indent=2))
print(json.dumps({k:v for k,v in result.items() if k not in ['proof_discrepancies','policy4_timing','proof_fields','color_count_differences']},indent=2))
print('Numerical differences recorded:',len(discrepancies))
print('Policy 4: fixture N old/new GPU p50 ms; solver ms; CPU ms; iterations')
for r in comparison:
    print(f"{r['topology']:9} {r['n']:4} {r['archived_gpu_p50_us']/1000:.2f}/{r['gpu_p50_us']/1000:.2f}; "
          f"{r['archived_solver_us']/1000:.2f}/{r['solver_us']/1000:.2f}; "
          f"{r['archived_cpu_us']/1000:.3f}/{r['cpu_us']/1000:.3f}; {r['iterations']}")
