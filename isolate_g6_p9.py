"""Exactly two 33-tick native CLI traces after P9 stopped; no rebuild or solver edit."""
from pathlib import Path
import hashlib,json,re,struct,subprocess,time
from profile_islands import member_offset
R=Path(__file__).resolve().parent;E=R/'evidence/g6-p9/isolation'
def sig(value):return hashlib.sha256(json.dumps(value,separators=(',',':')).encode()).hexdigest()
def extract(path):
    payload=json.loads(path.read_text());n=payload['n'];cap=payload['capacity'];cc=payload['contact_capacity']
    meta=Path(str(path)+'-meta-33.bin').read_bytes();arena=Path(str(path)+'-contacts-33.bin').read_bytes();trial=Path(str(path)+'-trial-33.bin').read_bytes();state=Path(str(path)+'-state-33.bin').read_bytes()
    u32=lambda p,at:struct.unpack_from('<I',p,at)[0]
    def at(name,i):return member_offset(name,cap,i)
    def mv(name,i):return u32(meta,at(name,i))
    def ct(name,i):
        pattern=rf'^#define G3_{name}\(p,i\) \(0u\+(\d+)u\*\(p\)\+(\d+)u\*\(i\)\)$'
        match=re.search(pattern,(R/'physics-layout.h').read_text(),re.M);assert match,name
        a,b=map(int,match.groups());return a*cc+b*i
    count=u32(meta,8);keys=[];colors=[];by_root={}
    for k in range(count):
        rec=struct.unpack_from('<20I',arena,80*k)
        key=tuple(rec[:2]+rec[3:10]+(rec[12],)+rec[16:20]);keys.append(key);colors.append(rec[13])
    for root in range(n):
        length=mv('CONTACT_COUNT',root)
        if not length:continue
        start=struct.unpack_from('<Q',meta,at('CONTACT_START',root))[0]
        base=struct.unpack_from('<Q',meta,at('COLOR_BASE',root))[0];nc=mv('COLORS',root)
        order=[u32(arena,ct('ROOT_CONTACTS',start+j)) for j in range(length)]
        assert len(set(order))==length and all(k<count for k in order)
        starts=[u32(arena,ct('COLOR_START',base+j)) for j in range(nc+1)]
        assert starts[0]==start and starts[-1]==start+length
        groups=[];covered=[]
        for col,(first,end) in enumerate(zip(starts,starts[1:])):
            group=[u32(arena,ct('COLORED',j)) for j in range(first,end)];touched=set()
            for k in group:
                assert colors[k]==col
                bodies=[i for i in keys[k][:2] if i<n]
                assert not touched.intersection(bodies),'conflicting color';touched.update(bodies)
            covered+=group;groups.append(sorted(keys[k] for k in group))
        assert sorted(covered)==sorted(order)
        by_root[root]={'contacts':sorted(keys[k] for k in order),'order':[keys[k] for k in order],'passes':groups,'iterations':mv('ITERATIONS',root),'size':mv('SIZE',root)}
    inputs=[[u32(trial,64*i+4*f) for f in [0,1,4,6,7,8,9,12,15]]+[mv('FREE_'+axis,i) for axis in ['VX','VY','OMEGA','SLEEP']] for i in range(n)]
    return {'payload':payload,'contact_set':sig(sorted(keys)),'contact_order':sig(keys),'input_signature':sig(inputs),'roots':by_root,'state':state,'inputs':inputs}
def main():
    assert not E.exists(),'Preserve diagnostic evidence';E.mkdir()
    prior=json.loads((E.parent/'results.json').read_text());assert 'medium: state repeatability' in prior['first_failure']
    exe=R/'zig-out/bin/physics.exe';binary=hashlib.sha256(exe.read_bytes()).hexdigest();assert binary==prior['build']['binaries']['physics.exe']
    records=[];result={'status':'INCOMPLETE','purpose':'Localize the first tick32 repeatability failure; no broad testing resumed','binary_sha256':binary,'runs':records}
    try:
        values=[]
        for repeat in range(2):
            path=E/f'trace-{repeat}.json';cmd=[str(exe),'--n','1024','--fixture','10','--flags','4','--contacts','12288','--pairs','8192','--cell-mode','1','--steps','33','--verify-every-tick','--trace-last','--out',str(path)]
            start=time.monotonic()
            with (E/f'trace-{repeat}.log').open('wb') as f:p=subprocess.run(cmd,cwd=R,stdout=f,stderr=subprocess.STDOUT,timeout=30)
            records.append({'command':cmd,'exit':p.returncode,'wall_s':time.monotonic()-start});assert p.returncode==0
            data=extract(path);assert data['payload']['status']=='PASS' and data['payload']['validation_errors']==0;values.append(data)
        a,b=values
        changed=[root for root in a['roots'] if a['roots'][root]['passes']!=b['roots'][root]['passes']]
        physical=[];telemetry=[]
        for i in range(1024):
            for field in range(16):
                at=64*i+4*field;x=struct.unpack_from('<I',a['state'],at)[0];y=struct.unpack_from('<I',b['state'],at)[0]
                if x!=y:
                    v={'body':i,'field':field,'bits':[x,y],'values':[struct.unpack('<f',struct.pack('<I',w))[0] for w in [x,y]]}
                    (telemetry if field in [10,11,13,14] else physical).append(v)
        result.update(status='LOCALIZED',same_contact_set=a['contact_set']==b['contact_set'],same_input=a['input_signature']==b['input_signature'],contact_set_signatures=[a['contact_set'],b['contact_set']],input_signatures=[a['input_signature'],b['input_signature']],contact_order_signatures=[a['contact_order'],b['contact_order']],changed_color_roots=len(changed),physical_field_differences=len(physical),telemetry_field_differences=len(telemetry),examples=physical[:12],telemetry_examples=telemetry[:12],changed_root_examples=[{'root':r,'A':a['roots'][r],'B':b['roots'][r]} for r in changed[:3]],independent=[v['payload']['independent'] for v in values],cause='Atomic contact scatter changes greedy per-root color passes; valid tolerance-bounded PGS endpoints need not be bitwise identical. Default production scheduling is not canonical.',source_citations=['physics.hlsl:121-127 ph_contact_scatter, atomic cursor at125','physics.hlsl:130 ph_color greedy list order','physics.hlsl:205 ph_publish stores FP32 velocities and residual telemetry','projected_solver.hlsl:177 storeIsland rounds accepted FP64 state to FP32'])
        assert result['same_input'] and result['same_contact_set'] and changed and physical,'Evidence is insufficient to assign the scheduling cause'
    except Exception as error:result['status']='UNRESOLVED';result['error']=str(error)
    finally:
        (E/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:result.get(k) for k in ['status','same_input','same_contact_set','changed_color_roots','physical_field_differences','telemetry_field_differences','error']},indent=2))
    return result['status']!='LOCALIZED'
if __name__=='__main__':raise SystemExit(main())
