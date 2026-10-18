"""Bounded G5 connected-island profiling through the existing headless CLI.

python profile_islands.py --sizes 16 64 256 1024 --repeats 3 --require-convergence
Independent one-tick compressive-chain trials, not sustained/full qualification.
No engine/shader changes, screenshots, or viewer launches.
"""
from pathlib import Path
import argparse, datetime, hashlib, json, math, os, re, statistics, struct
from dev_test import ROOT, Workflow
from fractions import Fraction


def momentum_oracle(velocities,masses):
    """Independent 1D inelastic contact projection by exact weighted PAVA.

    Test oracle only: no iteration, contact coloring or GPU solver code reused.
    Project velocities onto v[i] <= v[i+1], preserving total momentum, then
    recover compressive contact impulses from the momentum prefix balance.
    """
    blocks=[]
    for i,(velocity,mass) in enumerate(zip(velocities,masses)):
        mass=Fraction(mass);assert mass>0
        blocks.append([i,i+1,mass,mass*Fraction(velocity)])
        while len(blocks)>1 and blocks[-2][3]/blocks[-2][2]>blocks[-1][3]/blocks[-1][2]:
            right=blocks.pop();left=blocks.pop()
            blocks.append([left[0],right[1],left[2]+right[2],left[3]+right[3]])
    result=[Fraction(0)]*len(velocities)
    for first,end,mass,momentum in blocks:result[first:end]=[momentum/mass]*(end-first)
    impulses=[];balance=Fraction(0)
    for i in range(len(result)):
        balance+=Fraction(masses[i])*(Fraction(velocities[i])-result[i])
        if i+1<len(result):
            assert balance>=0 and balance*(result[i+1]-result[i])==0
            impulses.append(balance)
    assert balance==0
    assert sum(Fraction(m)*v*v for m,v in zip(masses,result))<=sum(Fraction(m)*Fraction(v)**2 for m,v in zip(masses,velocities))
    return list(map(float,result)),list(map(float,impulses))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fixture(n, path):
    # Dyadic positions, radii and velocities are exactly representable in f32.
    # Disk centers are one diameter apart; every neighbor initially approaches.
    bodies=[]
    for i in range(n):
        x=(2*i-(n-1))/16
        vx=(n-1-2*i)/(2*n)
        bodies.append(struct.pack('<12f4I',x,0,vx,0,0,0,1,512,1/16,0,vx*vx,0,0,0,1,i))
    data=b''.join(bodies);path.write_bytes(data)
    decoded=[struct.unpack('<16f',b) for b in bodies]
    contacts=set()
    for i,a in enumerate(decoded):
        assert all(math.isfinite(x) for x in a[:12])
        for j in range(i):
            b=decoded[j];distance=math.hypot(a[0]-b[0],a[1]-b[1]);radius=a[8]+b[8]
            assert distance>=radius,('initial overlap',i,j)
            if distance==radius:contacts.add((j,i))
    assert contacts=={(i,i+1) for i in range(n-1)}
    return dict(n=n,radius_m=1/16,center_spacing_m=1/8,world_extent_m=[n/8,1/8],
                initial_area_occupancy=math.pi/4,velocity_x_m_s=[decoded[-1][2],decoded[0][2]],
                dt_s=1/128,initial_overlaps=0,initial_contacts=n-1,islands=1,
                momentum_x=sum(b[2] for b in decoded),energy_j=sum(.5*b[2]**2 for b in decoded),
                input_sha256=digest(path))


def member_offset(name,cap,i=0):
    # Read the existing generated ABI rather than inventing a telemetry layout.
    text=(ROOT/'physics-layout.h').read_text()
    pattern=rf'^#define G3_{name}\(c,i\) \(256u\+(\d+)u\*\(c\)\+(\d+)u\*\(i\)\)$'
    match=re.search(pattern,text,re.M)
    if not match:raise RuntimeError('Unsupported generated ABI: '+name)
    stride,width=map(int,match.groups());return 256+stride*cap+width*i


def verify_attempt(payload,out,input_path):
    n=payload['n'];cap=payload['capacity']
    meta=Path(str(out)+'-meta-1.bin').read_bytes()
    arena=Path(str(out)+'-contacts-1.bin').read_bytes()
    state=Path(str(out)+'-state-1.bin').read_bytes()
    word=lambda at:struct.unpack_from('<I',meta,at)[0]
    count=word(8);pairs=set();parent=list(range(n));independent_ratio=0;actual_impulses=[0.]*(n-1);maximum_tolerance=0
    macro=re.search(r'^#define G3_LAMBDA_N\(p,i\) \(0u\+(\d+)u\*\(p\)\+(\d+)u\*\(i\)\)$',(ROOT/'physics-layout.h').read_text(),re.M)
    assert macro
    lambda_stride,lambda_width=map(int,macro.groups())
    trial=Path(str(out)+'-trial-1.bin').read_bytes()
    rounded=[struct.unpack_from('<16f',trial,64*i) for i in range(n)]
    work=[tuple(struct.unpack_from('<d',meta,member_offset('WORK_'+axis,cap,i))[0] for axis in ['VX','VY']) for i in range(n)]
    def root(i):
        while parent[i]!=i:i=parent[i]
        return i
    # Verify actual emitted records and identity, independently reconstructing
    # the full graph even when convergence rejection bypasses CPU KKT checks.
    for k in range(count):
        rec=struct.unpack_from('<20I',arena,80*k);a,b=rec[:2]
        assert 0<=a<b<n and (a,b) not in pairs
        assert rec[16:20]==(a,1,b,1)
        pairs.add((a,b));ra,rb=root(a),root(b);parent[max(ra,rb)]=min(ra,rb)
        # Independently audit the existing normal projected-KKT residual on
        # attempted state, including rejects (the CLI CPU verifier exits early
        # on a flagged tick). No corrective solver or CPU integration here.
        fields=struct.unpack_from('<20f',arena,80*k)
        nx,ny,target,kn=fields[3],fields[4],fields[5],fields[8]
        ln=struct.unpack_from('<d',arena,lambda_stride*payload['contact_capacity']+lambda_width*k)[0]
        assert math.isfinite(ln) and ln>=0 and kn==2 and target==0 and fields[9]==0
        assert b==a+1;actual_impulses[a]=ln
        normal=(rounded[a][2]-rounded[b][2])*nx+(rounded[a][3]-rounded[b][3])*ny-target
        residual=min(normal,ln*kn) if normal>=0 else -normal
        tolerance=32*2**-23*max(.001,abs(target),abs(work[a][0]),abs(work[a][1]),abs(work[b][0]),abs(work[b][1]))
        independent_ratio=max(independent_ratio,residual/tolerance)
        maximum_tolerance=max(maximum_tolerance,tolerance)
    assert pairs=={(i,i+1) for i in range(n-1)},('contact coverage',n,count)
    assert {root(i) for i in range(n)}=={0}
    assert payload['largest']==n and payload['islands']==1
    assert all(word(member_offset('PARENT',cap,i))==0 for i in range(n))
    assert word(member_offset('SIZE',cap))==n
    ratio=struct.unpack_from('<f',meta,member_offset('RATIO',cap))[0]
    assert math.isclose(independent_ratio,ratio,rel_tol=2e-6,abs_tol=1e-5),('CPU/GPU KKT audit',independent_ratio,ratio)
    it=word(member_offset('ITERATIONS',cap));colors=word(member_offset('COLORS',cap))
    assert it==payload['total_iterations'] and math.isfinite(ratio)
    rejected=payload['error_flags']!=0
    if rejected:
        assert payload['error_flags']==2,('unexpected error',payload['error_flags'])
        assert payload['actual_published']==0 and payload['rollback_verified'] is True
        assert state==input_path.read_bytes() and ratio>1
    else:
        assert payload['status']=='PASS' and payload['actual_processed']==n
        assert payload['independent']['objects']==n and payload['independent']['contacts']==n-1
        assert payload['independent']['largest']==n and payload['independent']['islands']==1
        assert payload['independent']['residual_ratio']<=1 and ratio<=1
    assert payload['validation_errors']==0
    initial=[struct.unpack_from('<16f',input_path.read_bytes(),64*i) for i in range(n)]
    reference_velocity,reference_impulse=momentum_oracle([x[2] for x in initial],[1/x[6] for x in initial])
    velocity_error=max(abs(work[i][0]-reference_velocity[i]) for i in range(n))
    impulse_error=max(abs(a-b) for a,b in zip(actual_impulses,reference_impulse))
    reconstruction_error=0
    for i in range(n):
        reconstructed=initial[i][2]+(actual_impulses[i-1] if i else 0)-(actual_impulses[i] if i+1<n else 0)
        reconstruction_error=max(reconstruction_error,abs(work[i][0]-reconstructed))
    assert reconstruction_error<=2e-12*max(1,max(actual_impulses)),('1D impulse reconstruction',reconstruction_error)
    momentum_error=abs(sum(v[0] for v in work)-sum(x[2] for x in initial))
    assert momentum_error<=n*2e-12*max(1,max(actual_impulses))
    # The oracle is exact. The allowed velocity/impulse discrepancy is an
    # a-posteriori chain bound implied by the unchanged local KKT tolerance,
    # not a replacement or relaxation of the GPU/CPU acceptance criteria.
    if not rejected:
        bound=(n-1)*maximum_tolerance+momentum_error/n
        assert velocity_error<=bound+2e-12
        assert impulse_error<=n*(bound+2e-12)
    return dict(actual_bodies=n,actual_contacts=count,actual_islands=1,solver_iterations=it,
                colors=colors,solver_residual_ratio=ratio,independent_attempt_residual_ratio=independent_ratio,cpu_kkt_verified=not rejected,
                cpu_kkt_residual_ratio=payload['independent']['residual_ratio'] if not rejected else None,
                rollback_verified=payload['rollback_verified'] if rejected else None,
                rejected=rejected,error_flags=payload['error_flags'],oracle_velocity_error=velocity_error,
                oracle_impulse_error=impulse_error,oracle_impulse_max=max(reference_impulse),
                momentum_error=momentum_error,impulse_reconstruction_error=reconstruction_error)


def stages(t):
    result=dict(prepare=t[1],discovery=0,contact_admission=0,graph_ready=0,solver=0,round_finalize=t[27]-t[38],
                validation=t[28]-t[27],publication_readback=t[39]-t[28],total=t[39])
    for r in range(9):
        result['discovery']+=t[2+3*r]-(t[1] if r==0 else t[1+3*r])
        result['contact_admission']+=t[30+r]-t[2+3*r]
        if r<8:
            result['graph_ready']+=t[3+3*r]-t[30+r]
            result['solver']+=t[4+3*r]-t[3+3*r]
    assert abs(sum(v for k,v in result.items() if k!='total')-result['total'])<1e-6
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sizes',nargs='+',type=int,default=[16,64,256,1024])
    parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--require-convergence',action='store_true',help='Fail this targeted regression if any trial rejects; does not qualify G5')
    args=parser.parse_args()
    if any(n not in [16,64,256,1024] for n in args.sizes) or not 1<=args.repeats<=5:parser.error('bounded sizes/repeats only')
    out=ROOT/'dev-test-results'/('g5-islands-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(parents=True);workflow=Workflow(out)
    lock=workflow.cache/'running.lock'
    try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:raise RuntimeError(f'Another headless run or stale lock: {lock}; confirm it stopped before removing')
    os.write(fd,str(os.getpid()).encode());os.close(fd)
    runs=[];fixtures=[];summary=[]
    try:
        exe=workflow.gpu('physics')
        for n in args.sizes:
            input_path=out/f'chain-{n}.bin';fixtures.append(fixture(n,input_path))
            for repeat in range(args.repeats):
                path=out/f'n{n}-{repeat}.json'
                command=[exe,'--n',str(n),'--fixture','0','--flags','0','--input',input_path,
                         '--contacts',str(4*n),'--pairs',str(4*n),'--iterations','4096',
                         '--max-bodies','4096','--max-work','8388608','--steps','1','--warmup','0',
                         '--trace-last','--out',path]
                execution,_=workflow.run(f'n{n}-{repeat}',command,timeout=45)
                payload=json.loads(path.read_text());proof=verify_attempt(payload,path,input_path)
                timing=stages(payload['gpu_cumulative_us'][0][:40])
                runs.append(dict(n=n,repeat=repeat,execution=execution,proof=proof,gpu_stage_us=timing,
                                 cpu_record_us=payload['cpu_recording_us'][0],cpu_queue_submit_us=payload['cpu_queue_submission_us'][0],
                                 cpu_record_submit_us=payload['cpu_submission_us'][0],cpu_blocking_us=payload['cpu_blocking_us'][0],
                                 memory=payload['memory'],state_sha256=payload['state_sha256']))
                print(f"{'REJECTED' if proof['rejected'] else 'CONVERGED'} n={n} island={proof['actual_bodies']} contacts={proof['actual_contacts']} iterations={proof['solver_iterations']} ratio={proof['solver_residual_ratio']:.5g} GPU={timing['total']:.2f}us solver={timing['solver']:.2f}us",flush=True)
            selected=[x for x in runs if x['n']==n]
            row=dict(n=n,island_size=n,contacts=n-1,trials=len(selected),
                     rejected=sum(x['proof']['rejected'] for x in selected),
                     solver_iterations=[x['proof']['solver_iterations'] for x in selected],
                     residual_ratio=[x['proof']['solver_residual_ratio'] for x in selected],
                     gpu_stage_us_p50={k:statistics.median(x['gpu_stage_us'][k] for x in selected) for k in selected[0]['gpu_stage_us']},
                     cpu_record_submit_us_p50=statistics.median(x['cpu_record_submit_us'] for x in selected),
                     cpu_record_us_p50=statistics.median(x['cpu_record_us'] for x in selected),
                     cpu_queue_submit_us_p50=statistics.median(x['cpu_queue_submit_us'] for x in selected))
            summary.append(row)
        rejected_count=sum(x['proof']['rejected'] for x in runs)
        result=dict(status='PASS' if args.require_convergence and not rejected_count else 'PROFILED_NOT_QUALIFIED',qualification=False,scope='G5 targeted single-connected-island cold one-tick trials',convergence_required=args.require_convergence,
                    notes='Three trials by default: exploratory medians, no tail-latency or sustained-throughput claim. GPU_REJECTED is a convergence failure, not an accepted physics pass. Full CLI CPU invariants apply only to converged trials; independent normal KKT audit of attempted state, exact contacts/graph and rollback checked on all trials. GPU timestamp intervals include barriers and inter-packet queue gaps; CPU record+submit includes all legacy split submissions.',
                    solver_iterations_limit=4096,max_work=8388608,local_bodies_limit=512,fixtures=fixtures,runs=runs,summary=summary,
                    binary_sha256=digest(exe),solver_dxil_sha256=digest(ROOT/'ph_solve.dxil'),source_sha256={name:digest(ROOT/name) for name in ['profile_islands.py','physics.c','physics.hlsl','projected_solver.hlsl','physics_main.zig','physics_verify.c','physics-layout.h']})
        (out/'result.json').write_text(json.dumps(result,indent=2));print('Evidence:',out,flush=True)
        if args.require_convergence and rejected_count:raise RuntimeError(f'{rejected_count} targeted convergence trials rejected')
    except Exception as error:
        (out/'failure.json').write_text(json.dumps(dict(status='FAIL',error=str(error),runs=runs,fixtures=fixtures),indent=2));raise
    finally:lock.unlink()


if __name__=='__main__':main()
