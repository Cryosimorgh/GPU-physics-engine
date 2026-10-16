import json,hashlib
from pathlib import Path
p=Path(__file__).parent
raw=(p/'spatial-schema.json').read_bytes();s=json.loads(raw);digest=hashlib.sha256(raw).hexdigest()
lines=['// Generated; edit spatial-schema.json. SHA256 '+digest,'#ifndef G2_LAYOUT_H','#define G2_LAYOUT_H']
for k,v in s.items():
 if isinstance(v,int):lines+=['#define G2_'+k.upper()+' '+str(v)+'u']
lines+=['#define G2_TAG 0x'+digest[:8]+'u','#define G2_COUNT(i) (G2_HEADER_BYTES+G2_COUNT_BYTES*(i))','#define G2_OFFSET(cap,i) (G2_HEADER_BYTES+G2_COUNT_BYTES*(cap)+G2_OFFSET_BYTES*(i))','#define G2_COVERAGE(cap,pass,i) (G2_HEADER_BYTES+(G2_COUNT_BYTES+G2_OFFSET_BYTES)*(cap)+4u*((pass)*(cap)+(i)))','#define G2_GRAPH_BASE(cap) (G2_HEADER_BYTES+(G2_COUNT_BYTES+G2_OFFSET_BYTES+G2_COVERAGE_BYTES_PER_ENTITY)*(cap))','#define G2_PARENT(cap,i) (G2_GRAPH_BASE(cap)+4u*(i))','#define G2_SIZE(cap,i) (G2_GRAPH_BASE(cap)+4u*(cap)+4u*(i))','#define G2_DEGREE(cap,i) (G2_GRAPH_BASE(cap)+8u*(cap)+4u*(i))','#define G2_CONTACT_COUNT(cap,i) (G2_GRAPH_BASE(cap)+G2_GRAPH_BYTES_PER_ENTITY*(cap)+G2_CONTACT_COUNT_BYTES*(i))','#define G2_CONTACT_OFFSET(cap,i) (G2_CONTACT_COUNT(cap,cap)+G2_CONTACT_OFFSET_BYTES*(i))','#define G2_SCAN_BASE(cap) (G2_CONTACT_OFFSET(cap,cap))','#endif']
(p/'spatial-layout.h').write_text('\n'.join(lines)+'\n')
