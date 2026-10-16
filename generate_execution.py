from pathlib import Path
import hashlib,json
r=Path(__file__).parent;raw=(r/'execution-schema.json').read_bytes();s=json.loads(raw)
lines=['// Generated execution ABI SHA256 '+hashlib.sha256(raw).hexdigest(),'#ifndef G4_EXECUTION_LAYOUT_H','#define G4_EXECUTION_LAYOUT_H']
for key,value in s.items():
 if isinstance(value,int):lines.append('#define G4_'+key.upper()+' '+str(value)+'u')
lines.append('#endif');(r/'execution-layout.h').write_text('\n'.join(lines)+'\n')
