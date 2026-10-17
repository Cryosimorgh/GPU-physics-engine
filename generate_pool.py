from pathlib import Path
import hashlib,json
r=Path(__file__).parent;raw=(r/'pool-schema.json').read_bytes();s=json.loads(raw)
t='// Generated pool contract SHA256 '+hashlib.sha256(raw).hexdigest()+'\n#ifndef POOL_LAYOUT_H\n#define POOL_LAYOUT_H\n'
for k,v in s.items():t+='#define POOL_'+k.upper()+' '+str(v)+('u' if isinstance(v,int) else '')+'\n'
t+='#define POOL_DATA(meta_guard) ((meta_guard)+256u)\n#define POOL_ROLL(base,field,id) ((base)+POOL_CONFIG_BYTES+64u*(field)+4u*(id))\n#endif\n'
(r/'pool-layout.h').write_text(t)
