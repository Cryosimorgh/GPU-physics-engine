import json,hashlib,ast
from pathlib import Path
r=Path(__file__).parent;s=json.loads((r/'schema.json').read_text());h=hashlib.sha256((r/'schema.json').read_bytes()).hexdigest()
z=f'// generated schema {h}\nconst std=@import("std");\npub const version:u32={s["version"]};\npub const fields:u64={len(s["fields"])};\npub const tile:u64={s["tile"]};\npub const threads:u64={s["threads"]};\npub const command_capacity:u64={s["command_capacity"]};\npub const constant_count:usize={len(s["constants"])};\n'
z+='pub fn add(a:u64,b:u64) !u64{return std.math.add(u64,a,b) catch error.Overflow;}\npub fn mul(a:u64,b:u64) !u64{return std.math.mul(u64,a,b) catch error.Overflow;}\n'
z+='pub fn padded(n:u64) !u64{return try mul((try add(n,tile-1))/tile,tile);}\n'
z+='pub fn prefixWords(cap:u64) !u64 {var k=(try add(cap,255))/256;var sum:u64=0;while(true){sum=try add(sum,try mul(2,k));if(k<=256)break;k=(try add(k,255))/256;}return sum;}\n'
constants={'record_bytes':len(s['fields'])*4,'guard_words':s['guard_words'],'guard_bytes':s['guard_words']*4,'command_capacity':s['command_capacity'],'command_words':s['command_words']}
for name,value in constants.items():
    if name!='command_capacity':z+=f'pub const {name}:u64={value};\n'
z+=f'pub const field_count:usize={len(s["fields"])};\n'
z+='pub fn capacityFor(n:u64) !u32 {const cap=try padded(n);if(cap==0 or cap>std.math.maxInt(u32) or try add(try mul(cap,record_bytes),guard_bytes)>std.math.maxInt(u32))return error.AddressOverflow;return @intCast(cap);}\n'
def expression(n):
    if isinstance(n,ast.Constant):return str(n.value)
    if isinstance(n,ast.Name):return n.id
    if isinstance(n,ast.BinOp):return f'try {"add" if isinstance(n.op,ast.Add) else "mul"}({expression(n.left)},{expression(n.right)})'
    if isinstance(n,ast.Call):return ('@max' if n.func.id=='max' else 'try prefixWords')+'('+','.join(expression(a) for a in n.args)+')'
    raise ValueError(n)
z+='pub fn bufferBytes(cap:u64) ![10]u64 {return .{'+','.join(expression(ast.parse(b['bytes'],mode='eval').body) for b in s['buffers'])+'};}\n'
z+='pub const buffer_kinds=[_]i32{'+','.join(str(b['kind']) for b in s['buffers'])+'};\n'
z+='pub const buffer_names=[_][:0]const u8{'+','.join('"'+b['name']+'"' for b in s['buffers'])+'};\n'
z+='pub fn address(kind:u32,cap:u64,i:u64,f:u64) !u64 {if(i>=cap or f>=fields or kind>2)return error.Bounds;const w=switch(kind){0=>try add(try mul(i,fields),f),1=>try add(try mul(f,cap),i),2=>try add(try add(try mul(i/tile,tile*fields),try mul(f,tile)),i%tile),else=>unreachable};return mul(w,4);}\n'
out={'layout.zig':z,'layout.h':'// generated '+h+'\n#pragma once\n#define S_CONSTANTS '+str(len(s['constants']))+'\n#define S_COMMANDS '+str(s['command_capacity'])+'\n'}
hs='// generated '+h+'\n#define FIELDS '+str(len(s['fields']))+'u\n#define TILE '+str(s['tile'])+'u\n#define THREADS '+str(s['threads'])+'\n#define COMMAND_CAPACITY '+str(s['command_capacity'])+'u\n'
hs+='cbuffer C:register(b0){'+''.join('uint '+x+';' for x in s['constants'])+'};\n'
hs+='uint address(uint kind,uint cap,uint i,uint field){return 4*(kind==0?i*FIELDS+field:kind==1?field*cap+i:(i/TILE)*(TILE*FIELDS)+field*TILE+i%TILE);}\nuint item(uint3 group,uint lane){return (group.x+65535u*group.y)*THREADS+lane;}\n'
hs+='uint prefixWords(uint cap){uint k=(cap+255)/256,sum=0;for(;;){sum+=2*k;if(k<=256)break;k=(k+255)/256;}return sum;}\n'
for name,value in constants.items():hs+=f'static const uint {name}={value}u;\n'
hs+='uint resourceBytes(uint slot,uint cap){switch(slot){'+''.join(f'case {i}:return {b["bytes"]};' for i,b in enumerate(s['buffers']))+'default:return 0;}}\n'
out['layout.hlsl']=hs
import sys
for name,data in out.items():
    if '--check' in sys.argv:assert (r/name).read_text()==data,name
    else:(r/name).write_text(data)
print('Schema verified' if '--check' in sys.argv else 'Schema generated')
