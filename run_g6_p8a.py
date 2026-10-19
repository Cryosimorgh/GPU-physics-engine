"""Two serialized failure-localization repeats using the unchanged P8 fixture.
Run run_p8a_control.py first on unchanged shaders; then build the diagnostic host.
No viewer, solver-policy sweep, or accepted-tick diagnostic GPU readbacks.
"""
from pathlib import Path
import hashlib,json,shutil,struct,subprocess,time
from dev_test import Workflow,sdk,digest,dependencies
R=Path(__file__).resolve().parent;E=R/'evidence/g6-p8a'
NAMES=['ph_guards','ph_check_contacts','ph_check_bodies','ph_pool_positions','ph_check_pairs']
CODES={1:'contact normal KKT residual',2:'contact tangent KKT residual',3:'negative/nonfinite normal impulse',4:'tangent friction bound',5:'body impulse reconstruction',6:'coincident pool positions',7:'64-pass position correction not converged',8:'position correction displacement cap',9:'post-correction pair penetration'}
def read_rows(path):return [json.loads(x) for x in path.read_text().splitlines()]
def decode(meta):
    cap=32;at=256+164*cap+256+448
    code,tick,a,b,contact,detail=struct.unpack_from('<6I',meta,at)
    value,limit,aux0,aux1=struct.unpack_from('<4d',meta,at+24);extra=struct.unpack_from('<2I',meta,at+56)
    return dict(subcode=code,predicate=CODES.get(code,'UNKNOWN'),tick=tick,a=a,b=b,index=contact,detail=detail,value=value,threshold=limit,auxiliary0=aux0,auxiliary1=aux1,extra=extra)
def main():
    assert (E/'control-provenance.json').exists(),'Unchanged control must be recorded first'
    assert not (E/'diagnostic-results.json').exists(),'Preserve existing evidence'
    out=E/'variant-build';out.mkdir(exist_ok=True);w=Workflow(out);variant=E/'diagnostic-shaders';variant.mkdir(exist_ok=True)
    # Normal verified host/shaders already built once, reuse them here.
    exe=w.gpu('physics')
    build={'host_sha256':digest(exe),'source_sha256':{n:digest(R/n) for n in dependencies(['physics_main.zig','sustained_physics.zig','runtime.c','spatial.c','physics.c','physics_verify.c','physics_tests.c'])},'normal_shaders':{p.name:digest(p) for p in R.glob('*.dxil')},'diagnostic_shaders':{},'tools':w.tool_hashes}
    for name in NAMES:
        dst=(variant/(name+'.dxil')).relative_to(R).as_posix()
        w.build('p8a-'+name,['physics.hlsl'],[dst],[sdk()[1],'-T','cs_6_0','-Gis','-D','G6_POOL_FAILURE_DIAGNOSTICS=1','-E',name,'-Fo',dst,'physics.hlsl'])
        build['diagnostic_shaders'][name+'.dxil']=digest(R/dst)
    build['actions']=w.actions;build['reused']=w.reused;(E/'diagnostic-build.json').write_text(json.dumps(build,indent=2))
    result={'runs':[],'G5':'DEFERRED','G6':'NOT QUALIFIED','correction_applied':False}
    try:
        for name in NAMES:shutil.copy2(variant/(name+'.dxil'),R/'zig-out/bin'/(name+'.dxil'))
        for i in range(2):
            path=E/f'diagnostic-{i}.json';cmd=[str(exe),'--n','16','--fixture','13','--flags','7','--contacts','256','--pairs','256','--cell-mode','1','--seconds','30','--out',str(path)]
            start=time.monotonic()
            with (E/f'diagnostic-{i}.log').open('wb') as f:p=subprocess.run(cmd,cwd=R,stdout=f,stderr=subprocess.STDOUT,timeout=40)
            rows=read_rows(Path(str(path)+'.jsonl'));ticks=[r for r in rows if r['type']=='TICK'];last=ticks[-1]
            data=Path(str(path)+'.failure-meta.bin').read_bytes();fault=decode(data)
            run={'command':cmd,'exit':p.returncode,'wall_s':time.monotonic()-start,'fault':fault,'failure_tick':last['tick'],'error_flags':last['error_flags'],'published':last['published'],'rollback_verified':last['rollback_verified'],'prior_hash':ticks[-2]['state_hash'],'rejected_hash':last['state_hash'],'shots':[r['tick'] for r in ticks if r['shot']],'cleanup':json.loads(path.read_text())}
            assert fault['subcode'] in CODES and fault['tick']==last['tick'] and last['error_flags']==32 and last['published']==0
            assert run['prior_hash']==run['rejected_hash'] and run['rollback_verified'] and run['cleanup']['cleanup_ok']
            result['runs'].append(run)
        reference=read_rows(E/'original-P8/small-pool.json.jsonl');control=read_rows(E/'control.json.jsonl')
        ref=[r for r in reference if r['type']=='TICK'];ctl=[r for r in control if r['type']=='TICK']
        assert len(ref)==len(ctl)==4073 and all(a['state_hash']==b['state_hash'] for a,b in zip(ref,ctl))
        for i,run in enumerate(result['runs']):
            candidate=[r for r in read_rows(E/f'diagnostic-{i}.json.jsonl') if r['type']=='TICK']
            run['identical_all_state_hashes']=len(candidate)==len(ref) and all(a['state_hash']==b['state_hash'] for a,b in zip(ref,candidate))
            run['same_shots_as_P8']=run['shots']==[r['tick'] for r in ref if r['shot']]
            assert run['identical_all_state_hashes'] and run['same_shots_as_P8']
        result['status']='LOCALIZED'
    finally:
        for name in NAMES:shutil.copy2(R/(name+'.dxil'),R/'zig-out/bin'/(name+'.dxil'))
        (E/'diagnostic-results.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
