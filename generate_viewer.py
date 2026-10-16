"""Versioned native/HLSL render-control ABI (entity SoA layout unchanged)."""
from pathlib import Path
import hashlib,json
r=Path(__file__).parent;raw=(r/'viewer-schema.json').read_bytes();s=json.loads(raw);tag=hashlib.sha256(raw).hexdigest()
h=['// Generated viewer ABI SHA256 '+tag,'#ifndef G4_VIEWER_LAYOUT_H','#define G4_VIEWER_LAYOUT_H',f'#define G4_V_VERSION {s["version"]}u',f'#define G4_V_CAMERA_WORDS {len(s["camera"])}u',f'#define G4_V_HUD_PIXEL_STRIDE {s["hud_pixel_stride"]}u',f'#define G4_V_HUD_PIXELS {s["hud_pixel_capacity"]}u']
for i,(kind,name) in enumerate(s['camera']):h.append('#define G4_V_'+name.upper()+' '+str(i)+'u')
h+=['#endif'];(r/'viewer-layout.h').write_text('\n'.join(h)+'\n')
hlsl=['// Generated viewer ABI SHA256 '+tag,'#include "viewer-layout.h"','cbuffer Camera:register(b0){']+[kind+' '+name+';' for kind,name in s['camera']]+['};','uint cameraWord(uint index){','uint values[G4_V_CAMERA_WORDS]={'+','.join(('asuint('+name+')') if kind=='float' else name for kind,name in s['camera'])+'};return values[index];','}']
(r/'viewer-cbuffer.hlsl').write_text('\n'.join(hlsl)+'\n')
