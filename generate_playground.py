from pathlib import Path
import json,hashlib
r=Path(__file__).parent;raw=(r/'playground-schema.json').read_bytes();s=json.loads(raw)
text='// Generated playground scene/command contract SHA256 '+hashlib.sha256(raw).hexdigest()+'\n#ifndef PLAYGROUND_LAYOUT_H\n#define PLAYGROUND_LAYOUT_H\n'
for k,v in s.items():text+='#define PLAY_'+k.upper()+' '+(str(v)+'u' if isinstance(v,int) else str(v))+'\n'
text+='\n#endif\n';(r/'playground-layout.h').write_text(text)
