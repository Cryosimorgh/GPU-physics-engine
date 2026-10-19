"""Independent offline arithmetic witness; never solves or advances physics."""
import hashlib,json,struct
from pathlib import Path
from run_g6_p8a import decode
def f32(x):return struct.unpack('<f',struct.pack('<f',x))[0]
def analyze(prefix):
    prefix=Path(prefix);trial=Path(str(prefix)+'.failure-trial.bin').read_bytes();meta=Path(str(prefix)+'.failure-meta.bin').read_bytes();source=Path(str(prefix)+'.failure-state.bin').read_bytes();contacts=Path(str(prefix)+'.failure-contacts.bin').read_bytes()
    fault=decode(meta);cap=len(source)//64;n=16;a,b,k=fault['a'],fault['b'],fault['index'];assert cap==32 and n<=b<n+4
    get=lambda i,f:struct.unpack_from('<f',trial,4*(f*cap+i))[0]
    mf=lambda stride:struct.unpack_from('<f',meta,256+stride*cap+4*a)[0]
    w=f32(2.54);h=f32(1.27);x,y,r=get(a,0),get(a,1),get(a,8);side=b-n
    # Mirror IEEE binary32 operation boundaries from append(); independently
    # compare with the binary64 geometry() acceptance expression on same inputs.
    gap32=[f32(f32(x-f32(0))-r),f32(f32(w-r)-x),f32(f32(y-f32(0))-r),f32(f32(h-r)-y)][side]
    gap64=[x-r,w-r-x,y-r,h-r-y][side];dt=1/128
    nx,ny=[(1.,0.),(-1.,0.),(0.,1.),(0.,-1.)][side]
    free=(mf(88),mf(92),mf(96));pb=256+164*cap+256
    persistent=struct.unpack_from('<I',source,4*(12*cap+a))[0]
    material=struct.unpack_from('<8f',meta,pb);vn=free[0]*nx+free[1]*ny
    def target(gap):
        value=-max(0.,gap)/dt
        if not (persistent & (1<<(16+side))) and vn < -material[7] and vn < -max(0.,gap)/dt:value=max(value,-material[1]*vn)
        return value
    stored=struct.unpack_from('<f',contacts,80*k+20)[0];ln=struct.unpack_from('<d',contacts,108*256+8*k)[0];lt=struct.unpack_from('<d',contacts,116*256+8*k)[0]
    vx,vy,omega,im,ii=[get(a,f) for f in [2,3,5,6,7]];relative=vx*nx+vy*ny
    target32=f32(target(gap32));target64=target(gap64);q_stored=relative-stored;q_reference=relative-target64
    scale=max(.001,abs(target64),abs(vx),abs(vy));tolerance=44*2**-23*scale+8*2**-23*abs(omega*r)
    rn= min(q_reference,max(0,ln)*im) if q_reference>=0 else -q_reference
    rolling=meta[pb+32:pb+160]
    # ph_read(0) deliberately excludes G1's 256-byte source guard. P8's hash
    # includes it. Reconstruct the declared initialized guard and require an
    # exact match to BOTH independently recorded live full-state hashes.
    guard=struct.pack('<I',0xbaadc0de)*64;snapshot=hashlib.sha256(source+guard+rolling).hexdigest()
    ticks=[json.loads(line) for line in Path(str(prefix)+'.jsonl').read_text().splitlines() if json.loads(line)['type']=='TICK']
    assert snapshot==ticks[-1]['state_hash']==ticks[-2]['state_hash']
    assert fault['subcode']==1 and fault['value']==rn and fault['threshold']==tolerance
    assert target32==stored and q_stored==0 and rn>tolerance
    # This equality isolates the rail-gap rounding discrepancy, not iteration
    # convergence: solver satisfies its stored target exactly at publication f32.
    assert rn==target64-stored==(gap32-gap64)/dt
    result={'classification':'NUMERICAL REPRESENTATION MISMATCH IN POOL RAIL CONTACT TARGET','subcode':1,'body':a,'body_generation':struct.unpack_from('<I',contacts,80*k+68)[0],'wall':b,'side':['left','right','bottom','top'][side],'contact_index':k,
            'body_state':dict(x=x,y=y,vx=vx,vy=vy,omega=omega,radius=r,inverse_mass=im,inverse_inertia=ii),'free_velocity':free,'persistent_mask':persistent,'material':material,
            'world_width_float32':w,'gap_append_float32':gap32,'gap_validator_float64':gap64,'gap_difference':gap32-gap64,'target_stored_float32':stored,'target_from_float32_gap':target32,'target_validator_float64':target64,'relative_normal_velocity':relative,'normal_residual_stored_equation':q_stored,'normal_residual_validator':rn,'validation_threshold':tolerance,'ratio':rn/tolerance,'normal_impulse':ln,'tangent_impulse':lt,'friction_limit':material[5]*ln,'published_state_sha256':snapshot,'guard_hash_scope':'64 initialized 0xbaadc0de words reconstructed from G1 contract; final full digest must equal live prior/rejected P8 state hashes',
            'invalid_input_evidence':False,'position_correction_caused_this_rejection':False,'iteration_exhaustion_caused_this_rejection':False,'correction_applied':False,
            'proposed_correction':'Evaluate each pool rail gap in binary64 from stored f32 inputs before poolTarget(), consistently with geometry(); retain final target storage, tolerance, equations, KKT, work limits and rollback. Separate follow-up validation required.'}
    return result
if __name__=='__main__':
    E=Path(__file__).resolve().parent/'evidence/g6-p8a';all_results=[]
    for i in range(2):
        r=analyze(E/f'diagnostic-{i}.json');(E/f'arithmetic-{i}.json').write_text(json.dumps(r,indent=2));all_results.append(r)
    assert all_results[0]==all_results[1]
    print(json.dumps(all_results[0],indent=2))
