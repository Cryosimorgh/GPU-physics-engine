"""Serialized, bounded G5 robustness sweep. Usage: python sweep_g5.py [quick|full]."""
import argparse
import contextlib
import csv
import datetime
import io
import json
import math
import os
from pathlib import Path
import shutil
import statistics
import struct
import subprocess
import sys
import time

from dev_test import ROOT, Workflow, dependencies, shader_jobs, sdk
from profile_islands import digest, fixture as chain_fixture, member_offset, stages, verify_attempt

SOLVERS = ('PGS', 'SOR1.995', 'Policy3', 'Adaptive')
OMEGA_MAX = struct.unpack('<f', struct.pack('<f', 1.995))[0]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def bodies(data):
    require(len(data) % 64 == 0, 'invalid canonical state length')
    return [struct.unpack_from('<12f4I', data, i) for i in range(0, len(data), 64)]


def fixture(topology, n, path):
    if topology == 'chain':
        description = chain_fixture(n, path)
    else:
        side = math.isqrt(n)
        require(side * side == n and n in (64, 256), 'bounded new topology size')
        if topology == 'branching':
            width = 2 * side
            points = [(x, 0) for x in range(width)]
            points += [(x, y) for x in range(0, width, 2)
                       for y in range(1, (n-width)//(width//2)+1)]
        else:
            points = [(x, y) for y in range(side) for x in range(side)]
        cx = sum(x for x, _ in points)/n
        cy = sum(y for _, y in points)/n
        radius = 5/128 if topology == 'oblique' else 1/16
        data = []
        for i, (x, y) in enumerate(points):
            vx, vy = -(x-cx)/(4*side), -(y-cy)/(4*side)
            if topology == 'oblique':
                px, py = (3*x-4*y)/64, (4*x+3*y)/64
                vx, vy = .6*vx-.8*vy, .8*vx+.6*vy
                # Nonzero slip/spin, with compression maintained on every edge.
                vx += (1 if i % 2 else -1)/256
                omega = (1 if i % 2 else -1)/16
            else:
                px, py, omega = x/8, y/8, 0
            data.append(struct.pack('<12f4I', px, py, vx, vy, 0, omega,
                                    1, 2/(radius*radius), radius, 0,
                                    vx*vx+vy*vy, 0, 0, 0, 1, i))
        path.write_bytes(b''.join(data))
        description = dict(n=n, radius_m=radius, input_sha256=digest(path))
    initial = bodies(path.read_bytes())
    pairs = set()
    parent = list(range(n))
    def root(i):
        while parent[i] != i:
            i = parent[i]
        return i
    for a in range(n):
        require(all(math.isfinite(x) for x in initial[a][:12]), 'nonfinite fixture')
        for b in range(a+1, n):
            aa, bb = initial[a], initial[b]
            distance = math.hypot(aa[0]-bb[0], aa[1]-bb[1])
            require(distance >= aa[8]+bb[8], 'fixture initial overlap')
            if distance == aa[8]+bb[8]:
                pairs.add((a, b))
                ra, rb = root(a), root(b)
                parent[max(ra, rb)] = min(ra, rb)
    require({root(i) for i in range(n)} == {0}, 'fixture is not one connected island')
    expected = n-1 if topology in ('chain', 'branching') else 2*n-2*math.isqrt(n)
    require(len(pairs) == expected, 'fixture topology contact count')
    description.update(topology=topology, initial_contacts=len(pairs), initial_overlaps=0,
                       flags=2 if topology == 'oblique' else 0,
                       velocity_range=[min(x[2] for x in initial), max(x[2] for x in initial),
                                       min(x[3] for x in initial), max(x[3] for x in initial)])
    return description, pairs


def build_variants(workflow, diagnose=False, trace_restarts=False):
    """One verified build phase; specialize only ph_solve for the controls."""
    exe = workflow.gpu('physics')
    controls = {}
    (workflow.cache/'g5-sweep').mkdir(exist_ok=True)
    jobs = [('PGS', 0, 0), ('SOR1.995', 1, 0), ('Policy3', 3, 0), ('Adaptive', 4, 0)]
    if diagnose:
        jobs += [('AdaptiveTrace', 2, 1), ('CandidateTrace', 3, 1)]
    if trace_restarts:
        jobs += [('RestartTrace', 4, 1)]
    for name, policy, trace in jobs:
        binary = workflow.cache/'g5-sweep'/f'policy-{policy}-trace-{trace}-ph_solve.dxil'
        command = [sdk()[1], '-T', 'cs_6_0', '-Gis', '-D', f'G5_RELAXATION_POLICY={policy}',
                   '-D', f'G5_TRACE={trace}',
                   '-E', 'ph_solve', '-Fo', binary, ROOT/'physics.hlsl']
        workflow.build(f'g5-sweep-policy-{policy}-trace-{trace}', ['physics.hlsl'],
                       [binary.relative_to(ROOT).as_posix()], command)
        controls[name] = binary
    variants = {}
    for name in controls:
        directory = workflow.cache/'g5-sweep'/name
        directory.mkdir(parents=True, exist_ok=True)
        assets = [exe] + [ROOT/(entry+'.dxil') for _, entry, _ in shader_jobs()]
        hashes = {}
        for asset in assets:
            actual = controls[name] if name in controls and asset.name == 'ph_solve.dxil' else asset
            destination = directory/asset.name
            if not destination.exists() or digest(destination) != digest(actual):
                shutil.copy2(actual, destination)
            hashes[asset.name] = digest(destination)
        variants[name] = dict(exe=str(directory/exe.name), sha256=hashes)
    for solver in list(variants)[1:]:
        differences = [name for name in variants['PGS']['sha256']
                       if variants['PGS']['sha256'][name] != variants[solver]['sha256'][name]]
        require(differences == ['ph_solve.dxil'], f'unmatched PGS/{solver} binaries')
    return variants


def read_solver_trace(payload, path):
    """Read bounded test-only ABI v1; require every expected window, not samples."""
    require(payload['islands'] == 1 and payload['solver_dispatches'] == 1,
            'diagnostics require one actual solve; trace slots may otherwise be overwritten')
    meta = Path(str(path)+'-meta-1.bin').read_bytes()
    arena = Path(str(path)+'-contacts-1.bin').read_bytes()
    count = struct.unpack_from('<I', meta, 8)[0]
    require(count+66 <= payload['contact_capacity'], 'insufficient diagnostic arena reserve')
    records = []
    for slot in range(66):
        at = 80*(count+slot)
        magic, version, root, iteration = struct.unpack_from('<4I', arena, at)
        if magic != 0x47355452:
            continue
        require(version == 1 and root == 0, 'trace ABI/root mismatch')
        values = struct.unpack_from('<6d', arena, at+16)
        event, policy, reserved, ratio = struct.unpack_from('<3If', arena, at+64)
        require(all(math.isfinite(x) for x in (*values, ratio)), 'nonfinite trace')
        require(policy in (2, 3, 4) and reserved == 0 and 1 <= values[4] <= OMEGA_MAX and
                1 <= values[5] <= OMEGA_MAX, 'invalid relaxation trace')
        records.append(dict(slot=slot, iteration=iteration, raw_residual=values[0],
                            window_minimum=values[1], previous_minimum=values[2],
                            contraction=values[3], omega_before=values[4], omega_after=values[5],
                            event=event, policy=policy, kkt_ratio=ratio))
    final = [r for r in records if r['slot'] == 64]
    require(len(final) == 1 and final[0]['event'] == 16 and
            final[0]['iteration'] == payload['total_iterations'], 'missing final trace')
    it = final[0]['iteration']
    windows = [r for r in records if r['slot'] < 64]
    expected = (it-1)//64 if payload['status'] == 'PASS' else it//64
    require([r['slot'] for r in windows] == list(range(expected)), 'missing residual windows')
    require(all(r['iteration'] == 64*(r['slot']+1) for r in windows), 'incorrect trace iteration')
    restarts = [r for r in records if r['slot'] == 65]
    restart_required = final[0]['policy'] == 3 and it > 512
    if final[0]['policy'] == 4 and it > 512:
        checkpoint = next((r for r in windows if r['iteration'] == 512), None)
        require(checkpoint is not None, 'missing restart-decision residual window')
        restart_required = checkpoint['contraction'] >= .8
    if restart_required:
        require(len(restarts) == 1 and restarts[0]['event'] == 8 and
                restarts[0]['iteration'] == 512 and restarts[0]['omega_after'] in (1.995, OMEGA_MAX),
                'missing/bad budgeted restart')
    else:
        require(not restarts, 'unexpected restart')
    return sorted(records, key=lambda r:(r['iteration'], r['slot']))


def audit(payload, path, input_path, expected):
    """Exhaustive emitted graph/identity, rounded KKT and physical-state audit.

    Rejected attempted state is measured, never required to converge or preserve
    energy. Its published source must be byte-identical to the original input.
    Accepted cases additionally retain the CLI's unchanged exhaustive verifier.
    """
    n, cap, capacity = payload['n'], payload['capacity'], payload['contact_capacity']
    initial = bodies(input_path.read_bytes())
    trial = bodies(Path(str(path)+'-trial-1.bin').read_bytes())
    state = Path(str(path)+'-state-1.bin').read_bytes()
    meta = Path(str(path)+'-meta-1.bin').read_bytes()
    arena = Path(str(path)+'-contacts-1.bin').read_bytes()
    word = lambda at: struct.unpack_from('<I', meta, at)[0]
    count = word(8)
    require(count <= capacity, 'contact overflow')
    work = [[struct.unpack_from('<d', meta, member_offset('WORK_'+axis, cap, i))[0]
             for axis in ('VX', 'VY', 'OMEGA')] for i in range(n)]
    pairs = set()
    parent = list(range(n))
    ratio = 0.
    changes = [[0., 0., 0.] for _ in range(n)]
    absolute = [[0., 0., 0.] for _ in range(n)]
    degree = [0]*n
    max_impulse = 0.
    def root(i):
        while parent[i] != i:
            i = parent[i]
        return i
    for k in range(count):
        rec = struct.unpack_from('<20I', arena, 80*k)
        fields = struct.unpack_from('<20f', arena, 80*k)
        a, b = rec[:2]
        require(0 <= a < b < n and (a, b) not in pairs, 'invalid/duplicate contact')
        require(rec[16:20] == (a, 1, b, 1), 'contact identity/generation mismatch')
        pairs.add((a, b))
        ra, rb = root(a), root(b)
        parent[max(ra, rb)] = min(ra, rb)
        nx, ny, target, aa, ab, kn, kt = fields[3:10]
        ln = struct.unpack_from('<d', arena, 108*capacity+8*k)[0]
        lt = struct.unpack_from('<d', arena, 116*capacity+8*k)[0]
        require(math.isfinite(ln) and math.isfinite(lt) and ln >= 0, 'invalid normal impulse')
        require(abs(lt) <= .25*ln+2*2**-23*max(ln, 1e-20), 'friction cone violation')
        max_impulse = max(max_impulse, ln)
        va, vb = trial[a], trial[b]
        q = (va[2]-vb[2])*nx+(va[3]-vb[3])*ny-target
        vt = (va[2]-vb[2])*(-ny)+(va[3]-vb[3])*nx-va[5]*aa-vb[5]*ab
        rn = min(q, ln*kn) if q >= 0 else -q
        rt = (min(vt, max(0, lt+.25*ln)*kt) if vt >= 0 else
              min(-vt, max(0, .25*ln-lt)*kt)) if kt > 0 else abs(lt)
        tol = 32*2**-23*max(.001, abs(target), *(abs(v) for i in (a, b) for v in work[i][:2]))
        ratio = max(ratio, rn/tol, rt/tol)
        ix, iy = nx*ln-ny*lt, ny*ln+nx*lt
        for i, sign, arm in ((a, 1, aa), (b, -1, ab)):
            degree[i] += 1
            delta = (sign*ix*initial[i][6], sign*iy*initial[i][6], -lt*arm*initial[i][7])
            for axis in range(3):
                changes[i][axis] += delta[axis]
                absolute[i][axis] += abs(delta[axis])
    require(pairs == expected, f'contact coverage mismatch missing={len(expected-pairs)} extra={len(pairs-expected)}')
    require({root(i) for i in range(n)} == {0}, 'actual graph disconnected')
    require(payload['largest'] == n and payload['islands'] == 1, 'actual island telemetry mismatch')
    require(all(word(member_offset('PARENT', cap, i)) == 0 for i in range(n)), 'GPU graph root mismatch')
    require(word(member_offset('SIZE', cap)) == n, 'GPU island size mismatch')
    gpu_ratio = struct.unpack_from('<f', meta, member_offset('RATIO', cap))[0]
    require(math.isfinite(ratio) and math.isclose(ratio, gpu_ratio, rel_tol=2e-6, abs_tol=1e-5),
            f'CPU/GPU KKT audit mismatch {ratio} vs {gpu_ratio}')
    rejected = payload['error_flags'] != 0
    if rejected:
        require(payload['actual_published'] == 0 and payload['rollback_verified'] is True,
                'rejection did not roll back')
        require(state == input_path.read_bytes(), 'rejection mutated published source')
    else:
        require(payload['status'] == 'PASS' and payload['actual_processed'] == n, 'incomplete accepted tick')
        independent = payload['independent']
        require(independent['objects'] == n and independent['contacts'] == count and
                independent['largest'] == n and independent['islands'] == 1 and
                independent['residual_ratio'] <= 1 and gpu_ratio <= 1, 'CLI exhaustive acceptance failure')
    require(payload['validation_errors'] == 0, 'D3D12 validation error')
    # Impulse reconstruction with the existing verifier's f32 roundoff bound.
    max_reconstruction = 0.
    for i in range(n):
        for axis, field in enumerate((2, 3, 5)):
            error = abs(trial[i][field]-initial[i][field]-changes[i][axis])
            ku = 32*max(1, degree[i])*2**-23
            bound = ku/(1-ku)*(abs(initial[i][field])+absolute[i][axis])+4*2**-23*max(1e-6, abs(trial[i][field]))
            require(error <= bound, f'impulse reconstruction {i}/{axis}: {error}>{bound}')
            max_reconstruction = max(max_reconstruction, error)
    def invariants(rows):
        energy = sum((b[2]**2+b[3]**2)/(2*b[6])+b[5]**2/(2*b[7]) for b in rows)
        px = sum(b[2]/b[6] for b in rows)
        py = sum(b[3]/b[6] for b in rows)
        angular = sum(((initial[i][0]-initial[0][0])*b[3]-(initial[i][1]-initial[0][1])*b[2])/b[6]+b[5]/b[7]
                      for i, b in enumerate(rows))
        return energy, (px, py, angular)
    e0, p0 = invariants(initial)
    e1, p1 = invariants(trial)
    # Accepted-state energy check also covers friction, which the existing CLI
    # omits. Use its unchanged gamma64(64*contacts) roundoff envelope.
    ku = 64*max(1, count)*2**-23
    energy_bound = ku/(1-ku)*max(1e-20, e0, e1)
    if not rejected:
        require(e1 <= e0+energy_bound, 'accepted energy creation')
    proof = dict(actual_bodies=n, actual_contacts=count, actual_islands=1,
                 solver_iterations=word(member_offset('ITERATIONS', cap)),
                 colors=word(member_offset('COLORS', cap)), kkt_ratio=ratio,
                 energy_before=e0, attempted_energy_after=e1,
                 attempted_momentum_error=[abs(a-b) for a, b in zip(p0, p1)],
                 energy_roundoff_bound=energy_bound, max_impulse=max_impulse,
                 impulse_reconstruction_error=max_reconstruction,
                 rollback_verified=True if rejected else None,
                 accepted_invariants_verified=not rejected,
                 rejected=rejected, error_flags=payload['error_flags'])
    if payload['flags'] == 0 and pairs == {(i, i+1) for i in range(n-1)}:
        proof['chain_oracle'] = verify_attempt(payload, path, input_path)
    return proof


def execute(exe, out, topology, n, solver, sample, input_path, expected, timeout, iterations=4096, idle=False):
    name = f'{topology}-{n}-{solver}-{sample}'
    path = out/(name+'.json')
    command = [exe, '--n', str(n), '--fixture', '0', '--flags', '2' if topology == 'oblique' else '0',
               '--input', input_path, '--contacts', str(8*n), '--pairs', str(n*(n-1)//2),
               '--iterations', str(iterations), '--max-bodies', '4096', '--max-work', '8388608',
               '--steps', '1', '--warmup', '0', '--trace-last', '--out', path]
    row = dict(topology=topology, n=n, solver=solver, sample=sample, status='ERROR',
               command=list(map(str, command)), raw_json=str(path))
    start = time.perf_counter()
    try:
        with (out/(name+'.log')).open('w') as log:
            log.write(json.dumps(row['command'])+'\n')
            log.flush()
            process = subprocess.run(row['command'], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
        row['returncode'] = process.returncode
        require(process.returncode == 0, f'CLI exit {process.returncode}; see {name}.log')
        payload = json.loads(path.read_text())
        row['cli_status'] = payload['status']
        if payload['status'] == 'ADMISSION_REJECTED':
            row.update(status='ADMISSION_REJECTED', error=payload.get('error_code'))
        else:
            row.update(gpu_stage_us=stages(payload['gpu_cumulative_us'][0][:40]),
                       cpu_submit_us=payload['cpu_submission_us'][0],
                       cpu_record_us=payload['cpu_recording_us'][0],
                       cpu_queue_submit_us=payload['cpu_queue_submission_us'][0],
                       memory=payload['memory'], error_flags=payload['error_flags'])
            if idle:
                require(payload['status']=='PASS' and payload['actual_processed']==n and
                        payload['independent']['objects']==n and payload['independent']['contacts']==0 and
                        payload['solver_dispatches']==0 and payload['total_iterations']==0 and
                        payload['validation_errors']==0, 'idle full-coverage/zero-solver verification')
                row['proof'] = dict(rejected=False, actual_bodies=n, actual_contacts=0, actual_islands=0,
                                    solver_iterations=0, kkt_ratio=0)
            else:
                row['proof'] = audit(payload, path, input_path, expected)
            if solver.endswith('Trace'):
                row['trace'] = read_solver_trace(payload, path)
            row['status'] = 'REJECTED' if row['proof']['rejected'] else 'CONVERGED'
    except subprocess.TimeoutExpired:
        row.update(status='TIMEOUT', error=f'process exceeded {timeout}s; terminated and waited')
    except Exception as error:
        row['error'] = str(error)
    row['wall_seconds'] = time.perf_counter()-start
    return row


def percentile(values, p):
    """Nearest-rank quantile; quick n=2 p95 is the maximum, not a tail claim."""
    return sorted(values)[max(0, math.ceil(p*len(values))-1)] if values else None


def summarize(runs):
    summary = []
    for topology, n in dict.fromkeys((r['topology'], r['n']) for r in runs):
        for solver in (*SOLVERS, 'CachedP4'):
            selected = [r for r in runs if (r['topology'], r['n'], r['solver']) == (topology, n, solver)]
            if not selected:
                continue
            gpu = [r['gpu_stage_us']['total'] for r in selected if 'gpu_stage_us' in r]
            cpu = [r['cpu_submit_us'] for r in selected if 'cpu_submit_us' in r]
            proofs = [r['proof'] for r in selected if 'proof' in r]
            row = dict(topology=topology, n=n, solver=solver, samples=len(selected),
                       converged=sum(r['status'] == 'CONVERGED' for r in selected),
                       rejected=sum(r['status'] == 'REJECTED' for r in selected),
                       timeouts=sum(r['status'] == 'TIMEOUT' for r in selected),
                       errors=sum(r['status'] == 'ERROR' for r in selected),
                       admission_rejected=sum(r['status'] == 'ADMISSION_REJECTED' for r in selected),
                       blocked=sum(r['status'] == 'BLOCKED_AFTER_TIMEOUT' for r in selected),
                       contacts=proofs[0]['actual_contacts'] if proofs else None,
                       iterations=max((p['solver_iterations'] for p in proofs), default=None),
                       max_kkt=max((p['kkt_ratio'] for p in proofs), default=None),
                       gpu_p50_us=statistics.median(gpu) if gpu else None,
                       gpu_p95_us=percentile(gpu, .95),
                       cpu_p50_us=statistics.median(cpu) if cpu else None,
                       gpu_stage_p50_us={k:statistics.median(r['gpu_stage_us'][k] for r in selected if 'gpu_stage_us' in r)
                                         for k in selected[0].get('gpu_stage_us', {})})
            summary.append(row)
    regressions = []
    performance = []
    for row in summary:
        if row['errors']:
            regressions.append(dict(kind='CORRECTNESS_OR_EXECUTION', configuration=row))
    for topology, n in dict.fromkeys((r['topology'], r['n']) for r in summary):
        group = {r['solver']:r for r in summary if (r['topology'], r['n']) == (topology, n)}
        for solver in SOLVERS[1:]:
            if 'PGS' not in group or solver not in group:
                continue
            base, other = group['PGS'], group[solver]
            if base['converged'] > other['converged']:
                regressions.append(dict(kind='CONVERGENCE', topology=topology, n=n, solver=solver))
            # Fixed SOR below 64 is an unchanged PGS negative control. Adaptive
            # has no size switch. Compare only accepted complete ticks.
            if (not (solver == 'SOR1.995' and n < 64) and
                    base['converged'] == base['samples'] and other['converged'] == other['samples'] and
                    base['gpu_p50_us'] and other['gpu_p50_us'] and other['gpu_p50_us'] > base['gpu_p50_us']):
                performance.append(dict(kind='OBSERVED_PERFORMANCE', topology=topology, n=n, solver=solver,
                                        ratio=other['gpu_p50_us']/base['gpu_p50_us'],
                                        caveat='fixed short cold accepted trials; exploratory, not a significance claim'))
        if 'SOR1.995' in group and 'Adaptive' in group and group['SOR1.995']['converged'] > group['Adaptive']['converged']:
            regressions.append(dict(kind='CONVERGENCE', topology=topology, n=n,
                                    solver='Adaptive', reference='SOR1.995'))
        if 'Policy3' in group and 'Adaptive' in group and group['Policy3']['converged'] > group['Adaptive']['converged']:
            regressions.append(dict(kind='CONVERGENCE', topology=topology, n=n,
                                    solver='Adaptive', reference='Policy3'))
    regressions.extend(performance)
    return summary, regressions


def performance_balance(summary):
    """Predeclared equal-fixture geometric mean and summed complete GPU ticks.

    Failed/absent/unmatched cases cannot improve the apparent performance mix.
    Individual timing ratios remain visible; two samples are exploratory only.
    """
    base = {(r['topology'],r['n']):r for r in summary if r['solver'] == 'Policy3'}
    candidate = {(r['topology'],r['n']):r for r in summary if r['solver'] == 'Adaptive'}
    complete = bool(base) and base.keys() == candidate.keys() and all(
        base[k]['converged'] == base[k]['samples'] > 0 and
        candidate[k]['converged'] == candidate[k]['samples'] == base[k]['samples'] and
        base[k]['gpu_p50_us'] and candidate[k]['gpu_p50_us'] for k in base)
    if not complete:
        return dict(retain=False, reason='missing or failed matched converging cases')
    ratios = {f'{key[0]}-{key[1]}':candidate[key]['gpu_p50_us']/base[key]['gpu_p50_us'] for key in base}
    geometric_mean = math.exp(sum(math.log(r) for r in ratios.values())/len(ratios))
    total_ratio = sum(r['gpu_p50_us'] for r in candidate.values())/sum(r['gpu_p50_us'] for r in base.values())
    return dict(retain=geometric_mean<=1 and total_ratio<=1,
                reason='both GPU geometric mean and sum of per-fixture p50 must not worsen',
                geometric_mean_ratio=geometric_mean, sum_p50_ratio=total_ratio, per_fixture_ratios=ratios,
                cpu_sum_p50_ratio=sum(r['cpu_p50_us'] for r in candidate.values())/sum(r['cpu_p50_us'] for r in base.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', nargs='?', choices=['quick', 'full'], default='quick')
    parser.add_argument('--diagnose-adaptive', action='store_true',
                        help='one bounded old-policy trace phase, then three-way candidate sweep')
    parser.add_argument('--resume', type=Path, help='resume unexecuted cases from a saved batch; verify artifacts, no rebuild')
    parser.add_argument('--trace-restarts', action='store_true', help='audit candidate restart decisions for every fixture after timing trials')
    parser.add_argument('--profile-global', action='store_true', help='bounded global-solver cost/profile and cache comparison batch')
    args = parser.parse_args()
    if args.profile_global:
        require(not args.trace_restarts and not args.diagnose_adaptive,
                'global profile is one standalone automated batch')
        from profile_global import run
        return run(args.mode,args.resume)
    samples, timeout = (2, 20) if args.mode == 'quick' else (5, 45)
    out = args.resume.resolve() if args.resume else ROOT/'dev-test-results'/('g5-sweep-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True, exist_ok=bool(args.resume))
    previous = json.loads((out/'results.json').read_text()) if args.resume else None
    workflow = Workflow(out)
    lock = workflow.cache/'running.lock'
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    source_names = dependencies(['physics.hlsl', 'physics_main.zig', 'physics.c', 'physics_verify.c', 'runtime.c'])
    source_hashes = {name:digest(ROOT/name) for name in source_names}
    runs, fixtures = [], []
    try:
        if not previous:
            workflow.run('sweep-unit-tests', [sys.executable, '-m', 'unittest', 'test_sweep_g5', '-q'], timeout=30)
        # Complete all preparation before starting serialized GPU measurement.
        if previous:
            require(previous['source_sha256'] == source_hashes, 'resume source differs from compiled batch')
            require(previous['mode'] == args.mode, 'resume sample budget changed')
            variants = previous['builds']
            for variant in variants.values():
                directory = Path(variant['exe']).parent
                require(all(digest(directory/name) == value for name, value in variant['sha256'].items()),
                        'resume binary/shader corruption or mutation')
            shutil.copy2(out/'results.json', out/'results-before-resume.json')
        else:
            with contextlib.redirect_stdout(io.StringIO()):
                variants = build_variants(workflow, args.diagnose_adaptive, args.trace_restarts)
        shutil.copy2(ROOT/'projected_solver.hlsl', out/'tested-projected_solver.hlsl')
        prepared = []
        for topology in ('chain', 'branching', 'dense', 'oblique'):
            for n in ([16, 64, 256, 1024] if topology == 'chain' else [64, 256]):
                path = out/f'{topology}-{n}.bin'
                description, expected = fixture(topology, n, path)
                fixtures.append(description)
                prepared.append((topology, n, path, expected))
        diagnostics = []
        cached = {(r['topology'], r['n'], r['solver'], r['sample']):r
                  for r in (previous['runs'] if previous else []) if not r['status'].startswith('BLOCKED_')}
        old_diagnostics = {(r['n'], r['solver']):r for r in (previous.get('diagnostics', []) if previous else [])}
        def diagnostic(solver, n, path, expected):
            old = old_diagnostics.get((n, solver))
            if old and old.get('returncode') == 0:
                # Repair decoding from the completed export, never repeat GPU work.
                row = dict(old)
                payload = json.loads(Path(row['raw_json']).read_text())
                row['proof'] = audit(payload, Path(row['raw_json']), path, expected)
                row['trace'] = read_solver_trace(payload, Path(row['raw_json']))
                row['status'] = 'REJECTED' if row['proof']['rejected'] else 'CONVERGED'
                row.pop('error', None)
                row['reused_completed_gpu_case'] = True
                return row
            return execute(variants[solver]['exe'], out, 'chain', n, solver, 0, path, expected, timeout)
        fallback_supported = not args.diagnose_adaptive
        if args.diagnose_adaptive:
            for topology, n, path, expected in prepared:
                if topology == 'chain' and n in (64, 256, 1024):
                    row = diagnostic('AdaptiveTrace', n, path, expected)
                    diagnostics.append(row)
                    if row['status'] in ('ERROR', 'TIMEOUT', 'ADMISSION_REJECTED'):
                        break
            fallback_supported = (len(diagnostics) == 3 and
                diagnostics[0]['status'] == 'CONVERGED' and
                all(r['status'] == 'REJECTED' and r.get('error_flags') == 2 and
                    any(t['iteration'] == 512 and t['kkt_ratio'] > 1 for t in r.get('trace', []))
                    for r in diagnostics[1:]))
            (out/'diagnosis.json').write_text(json.dumps(dict(fallback_supported=fallback_supported,
                                                           runs=diagnostics), indent=2))
        blocked = any(r['status'] == 'TIMEOUT' for r in diagnostics)
        for topology, n, path, expected in prepared:
            # Reverse order per sample to balance the three serial variants.
            for sample in range(samples):
                for solver in (SOLVERS if sample % 2 == 0 else SOLVERS[::-1]):
                    key = (topology, n, solver, sample)
                    if key in cached:
                        row = dict(cached[key], reused_completed_gpu_case=True)
                    elif solver == 'Adaptive' and not fallback_supported:
                        row = dict(topology=topology, n=n, solver=solver, sample=sample,
                                   status='BLOCKED_DIAGNOSTIC', error='diagnostic evidence did not justify fallback')
                    elif blocked:
                        row = dict(topology=topology, n=n, solver=solver, sample=sample,
                                   status='BLOCKED_AFTER_TIMEOUT', error='No further GPU work after timeout; device completion unverified')
                    else:
                        row = execute(variants[solver]['exe'], out, topology, n, solver, sample, path, expected, timeout)
                    runs.append(row)
                    (out/'progress.json').write_text(json.dumps(runs, indent=2))
                    blocked |= row['status'] == 'TIMEOUT'
        if args.diagnose_adaptive and fallback_supported and not blocked:
            for topology, n, path, expected in prepared:
                if topology == 'chain' and n in (64, 256, 1024):
                    row = diagnostic('CandidateTrace', n, path, expected)
                    diagnostics.append(row)
                    if row['status'] == 'TIMEOUT':
                        break
        if args.trace_restarts and not blocked:
            for topology, n, path, expected in prepared:
                row = execute(variants['RestartTrace']['exe'], out, topology, n,
                              'RestartTrace', 0, path, expected, timeout)
                diagnostics.append(row)
                if row['status'] == 'TIMEOUT':
                    break
        require(source_hashes == {name:digest(ROOT/name) for name in source_names}, 'production source changed during sweep')
        summary, regressions = summarize(runs)
        adaptive = [r for r in runs if r['solver'] == 'Adaptive']
        adaptive_ok = all(r['status'] == 'CONVERGED' for r in adaptive)
        adaptive_ok &= all(r['status'] == 'CONVERGED' for r in diagnostics if r['solver'] in ('CandidateTrace', 'RestartTrace'))
        balance = performance_balance(summary)
        result = dict(mode=args.mode, qualification=False, samples_per_configuration=samples,
                      adaptive_acceptance=('RETAIN_QUICK_BALANCE_VERIFIED' if balance['retain'] else 'REJECT_PERFORMANCE_BALANCE') if adaptive_ok else 'REJECT_CONVERGENCE_OR_CORRECTNESS',
                      performance_balance=balance,
                      timeout_seconds=timeout, iterations_limit=4096, max_work=8388608,
                      candidate_policy=4, fallback_supported_by_diagnostic=fallback_supported,
                      diagnostics=diagnostics, production_policy=1,
                      scope='cold independent one-tick compressive fixtures; no sustained or million-object claim',
                      timing_note='End-to-end GPU timestamps include discovery, graph, solver, barriers and publication/readback; CPU includes recording plus submissions. Quick p95 is maximum of two samples.',
                      rejection_note='Rejected attempted-state KKT/energy are measured, not accepted physics. Published rollback is verified independently. No debug-layer/GBV claim.',
                      fixtures=fixtures, builds=variants,
                      build_actions=(previous['build_actions'] if previous else [])+workflow.actions,
                      resumed_completed_cases=sum(r.get('reused_completed_gpu_case', False) for r in runs+diagnostics),
                      cache_reused=workflow.reused, source_sha256=source_hashes,
                      sweep_sha256=digest(Path(__file__)), runs=runs, summary=summary,
                      regressions=regressions, first_regression=regressions[0] if regressions else None)
        (out/'results.json').write_text(json.dumps(result, indent=2))
        trace_rows = [dict(n=r['n'], solver=r['solver'], **record)
                      for r in diagnostics for record in r.get('trace', [])]
        if trace_rows:
            with (out/'residual-traces.csv').open('w', newline='') as file:
                writer = csv.DictWriter(file, fieldnames=list(trace_rows[0]))
                writer.writeheader()
                writer.writerows(trace_rows)
        columns = [key for key in summary[0] if key != 'gpu_stage_p50_us']
        with (out/'results.csv').open('w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=columns, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(summary)
        print('Topology  N    Solver     C/R/T/E  Contacts Iter  KKT(max) GPU p50/p95 us CPU us')
        def fmt(value):
            return '-' if value is None else f'{value:.1f}'
        for row in summary:
            counts = '/'.join(str(row[k]) for k in ('converged', 'rejected', 'timeouts', 'errors'))
            print(f"{row['topology']:9} {row['n']:4} {row['solver']:9} {counts:8} {str(row['contacts']):>5} {str(row['iterations']):>4} {fmt(row['max_kkt']):>9} {fmt(row['gpu_p50_us']):>8}/{fmt(row['gpu_p95_us']):<8} {fmt(row['cpu_p50_us'])}")
        print('First regression:', json.dumps(result['first_regression']))
        print('Candidate:', result['adaptive_acceptance'], 'Diagnostic supports fallback:', fallback_supported)
        print('Balance vs policy 3:', json.dumps(balance))
        for row in diagnostics:
            history = row.get('trace', [])
            reductions = [(r['iteration'], round(r['omega_after'], 6)) for r in history if r['event'] == 2]
            print('Trace', row['solver'], row['n'], row['status'], 'reductions=', reductions,
                  'restart=', [r['iteration'] for r in history if r['event'] == 8],
                  'final omega=', history[-1]['omega_after'] if history else None)
        print('Admission rejections:', sum(r['admission_rejected'] for r in summary),
              'Blocked after timeout:', sum(r['blocked'] for r in summary))
        print('Evidence:', out)
        return int(any(r['status'] != 'CONVERGED' for r in runs))
    except Exception as error:
        (out/'failure.json').write_text(json.dumps(dict(error=str(error), runs=runs, fixtures=fixtures), indent=2))
        raise
    finally:
        lock.unlink()


if __name__ == '__main__':
    raise SystemExit(main())
