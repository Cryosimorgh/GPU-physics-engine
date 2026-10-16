from pathlib import Path
import hashlib,json
r=Path(__file__).parent;raw=(r/'billiards-schema.json').read_bytes();s=json.loads(raw)
lines=['// Generated scene ABI SHA256 '+hashlib.sha256(raw).hexdigest(),'#ifndef BILLIARDS_LAYOUT_H','#define BILLIARDS_LAYOUT_H']
for key,value in s.items():
 if isinstance(value,(int,float)):lines.append('#define BILLIARDS_'+key.upper()+' '+(str(value)+'u' if isinstance(value,int) else repr(value)))
lines.append('#endif');(r/'billiards-layout.h').write_text('\n'.join(lines)+'\n')
