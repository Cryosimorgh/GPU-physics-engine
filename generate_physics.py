from pathlib import Path
import hashlib,json
r=Path(__file__).parent;raw=(r/'physics-schema.json').read_bytes();s=json.loads(raw)
lines=['// Generated physics ABI SHA256 '+hashlib.sha256(raw).hexdigest(),'#ifndef G3_LAYOUT_H','#define G3_LAYOUT_H']
for k,v in s.items():
 if isinstance(v,int):lines.append('#define G3_'+k.upper()+' '+str(v)+'u')
for group,param,base in [('metadata','c',s['header_bytes']),('arena','p',0)]:
 coefficient=0
 for entry in s[group]:
  name,width=entry[:2];stride=entry[2] if len(entry)>2 else width
  lines.append(f'#define G3_{name.upper()}({param},i) ({base}u+{coefficient}u*({param})+{stride}u*(i))');coefficient+=width
 lines.append(f'#define G3_{group.upper()}_END({param}) ({base}u+{coefficient}u*({param}))');lines.append(f'#define G3_{group.upper()}_STRIDE {coefficient}u')
lines+=['#define G3_ROOT_BOUND(n,f) (((f)&4u)?(n):(((n)+1u)/2u))', '#define G3_ARGS_CHUNKS(n,f) ((G3_ROOT_BOUND(n,f)+G3_SOLVER_CHUNK_GROUPS-1u)/G3_SOLVER_CHUNK_GROUPS)', '#define G3_ARGS_END(n,f) (G3_INDIRECT_HEADER_BYTES+G3_INDIRECT_STRIDE_BYTES*G3_ARGS_CHUNKS(n,f))']
lines+=['#define G3_TAG 0x'+hashlib.sha256(raw).hexdigest()[:8]+'u','#endif']
(r/'physics-layout.h').write_text('\n'.join(lines)+'\n')
(r/'physics-constants.hlsl').write_text('// Generated; same 16 DWORD root constants\ncbuffer PhysicsConstants:register(b0){'+''.join('uint '+x+';' for x in s['constants'])+'};\n')
print('Physics metadata bytes/entity:',sum(v for _,v in s['metadata']),'contact arena bytes/reservation:',sum(x[1] for x in s['arena']))
