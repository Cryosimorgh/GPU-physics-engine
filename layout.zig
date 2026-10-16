// generated schema d22e4449ef31ef1fc3ab27fd610037cbd1f8c56ee864b4d2f1443aa18156a272
const std=@import("std");
pub const version:u32=1;
pub const fields:u64=16;
pub const tile:u64=32;
pub const threads:u64=256;
pub const command_capacity:u64=1024;
pub const constant_count:usize=16;
pub fn add(a:u64,b:u64) !u64{return std.math.add(u64,a,b) catch error.Overflow;}
pub fn mul(a:u64,b:u64) !u64{return std.math.mul(u64,a,b) catch error.Overflow;}
pub fn padded(n:u64) !u64{return try mul((try add(n,tile-1))/tile,tile);}
pub fn prefixWords(cap:u64) !u64 {var k=(try add(cap,255))/256;var sum:u64=0;while(true){sum=try add(sum,try mul(2,k));if(k<=256)break;k=(try add(k,255))/256;}return sum;}
pub const record_bytes:u64=64;
pub const guard_words:u64=64;
pub const guard_bytes:u64=256;
pub const command_words:u64=8;
pub const field_count:usize=16;
pub fn capacityFor(n:u64) !u32 {const cap=try padded(n);if(cap==0 or cap>std.math.maxInt(u32) or try add(try mul(cap,record_bytes),guard_bytes)>std.math.maxInt(u32))return error.AddressOverflow;return @intCast(cap);}
pub fn bufferBytes(cap:u64) ![10]u64 {return .{try add(try mul(record_bytes,cap),guard_bytes),try add(try mul(12,cap),guard_bytes),try add(try mul(4,try add(try mul(2,cap),1)),guard_bytes),try add(try mul(4,try add(try add(try prefixWords(cap),guard_words),cap)),guard_bytes),try add(try mul(32,cap),guard_bytes),try add(try mul(28,cap),guard_bytes),try add(try mul(4,try add(4,command_capacity)),guard_bytes),try add(@max(try mul(record_bytes,cap),try mul(4,try add(4,command_capacity))),guard_bytes),try mul(try mul(command_words,4),command_capacity),try mul(record_bytes,cap)};}
pub const buffer_kinds=[_]i32{0,0,0,0,0,0,0,2,1,0};
pub const buffer_names=[_][:0]const u8{"components","identity_maps","active_flags_indices_count","active_prefix_scratch","coverage_counters","key_checksum_render_results","structural_control","validation_readback","command_upload","canonical_conversion_scratch"};
pub fn address(kind:u32,cap:u64,i:u64,f:u64) !u64 {if(i>=cap or f>=fields or kind>2)return error.Bounds;const w=switch(kind){0=>try add(try mul(i,fields),f),1=>try add(try mul(f,cap),i),2=>try add(try add(try mul(i/tile,tile*fields),try mul(f,tile)),i%tile),else=>unreachable};return mul(w,4);}
