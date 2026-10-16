const std=@import("std");
pub const l=@import("layout.zig");pub const entity=@import("entity.zig");
pub const c=@cImport({@cInclude("runtime.h");});
const a=std.heap.c_allocator;
pub const passes=[_][]const u8{"initialize","classify","scan_counts","add_prefix","scatter_safe","integrate","keys","update_motion","gather","full_state","pack_render","consume_render","convert","mutate","grow_maps","full_state_vector","empty_active","clear_coverage"};
pub fn ck(v:c_int) !void {if(v==0)return error.GPU;}
pub fn open(debug:bool) !*c.StorageDevice {
 const d=c.s_open(@intFromBool(debug)) orelse return error.Device;errdefer c.s_close(d);
 for(passes,0..) |name,i|{const path=try std.fmt.allocPrint(a,"{s}.dxil",.{name});defer a.free(path);const bytes=try std.fs.cwd().readFileAlloc(a,path,16*1024*1024);defer a.free(bytes);try ck(c.s_load(d,@intCast(i),bytes.ptr,bytes.len));}return d;
}
pub fn aligned(x:u64) !u64{return (try l.add(x,65535)) & ~@as(u64,65535);}
pub fn scratchWords(cap:u64) !u64 {return l.prefixWords(cap);}
pub const Ledger=struct {capacity:u32,n:u32,logical:[10]u64,device:[10]u64,total:u64,guard_bytes:u64=256,per_frame_copies:u32=1,contacts:u32=0};
pub fn ledger(d:*c.StorageDevice,n:u32,cap:u32) !Ledger {
 if(cap==0 or cap<n or cap%l.tile!=0)return error.Capacity;
 var x:Ledger=.{.capacity=cap,.n=n,.logical=undefined,.device=undefined,.total=0};
 x.logical=try l.bufferBytes(cap);
 for(x.logical,0..) |bytes,i|{if(bytes>std.math.maxInt(u32))return error.AddressOverflow;const size=c.s_allocation(d,bytes,l.buffer_kinds[i]);if(size==std.math.maxInt(u64))return error.DeviceDimension;x.device[i]=size;x.total=try l.add(x.total,size);}

 return x;
}
pub const Bundle=struct {
 d:*c.StorageDevice,n:u32,cap:u32,kind:u32,stride:u32,epoch:u32=0,handles:[10]u64=.{0}**10,plan:Ledger,allocation_us:f64=0,active_epoch:?u32=null,active_stride:u32=0,active_n:u32=0,vector_full:bool=false,poisoned:bool=false,
 pub fn init(d:*c.StorageDevice,n:u32,cap:u32,kind:u32,stride:u32,budget_cap:u64) !Bundle {
  if(kind>2)return error.Config;const p=try ledger(d,n,cap);if(c.s_admit(d,p.total,budget_cap)==0)return error.MemoryAdmission;
  var s:Bundle=.{.d=d,.n=n,.cap=cap,.kind=kind,.stride=stride,.plan=p};errdefer s.deinit();
  const start=c.s_clock();for(0..10) |i|{s.handles[i]=c.s_new(d,p.logical[i],l.buffer_kinds[i],l.buffer_names[i]);if(s.handles[i]==0)return error.Allocation;}
  s.allocation_us=c.s_clock()-start;return s;
 }
 pub fn deinit(s:*Bundle) void {for(&s.handles) |*h|if(h.*!=0){if(c.s_retire(s.d,h.*)==0)std.process.exit(3);h.*=0;};_=c.s_collect(s.d);}
 pub fn constants(s:*const Bundle,verify:bool) [l.constant_count]u32 {return .{s.n,s.cap,s.kind,s.stride,@intFromBool(verify),0,0,s.cap,0,0,0,0,0,s.epoch,0,0};}
 pub fn bind(s:*Bundle,k:*const [l.constant_count]u32,input:u64) !void {if(s.poisoned)return error.Poisoned;const h:[8]u64=.{s.handles[0],s.handles[1],s.handles[2],s.handles[3],s.handles[4],s.handles[5],s.handles[6],input};try ck(c.s_bind(s.d,&h,k));}
 pub fn dispatch(s:*Bundle,pass:u32,count:u32,k:*const [l.constant_count]u32,input:u64) !void {try s.bind(k,input);try ck(c.s_dispatch(s.d,@intCast(pass),count));}
 pub fn initialize(s:*Bundle) !void {try ck(c.s_begin(s.d));const k=s.constants(false);try s.dispatch(0,s.cap,&k,s.handles[8]);try ck(c.s_submit(s.d,0));try ck(c.s_wait(s.d));}
 pub fn compact(s:*Bundle,verify:bool) !void {
  var k=s.constants(verify);try s.dispatch(1,s.n,&k,s.handles[8]);
  var counts:[8]u32=undefined;var offsets:[8]u32=undefined;var levels:usize=0;var size=(s.n+255)/256;var offset:u32=0;
  while(true){counts[levels]=size;offsets[levels]=offset;levels+=1;offset+=2*size;if(size<=256)break;size=(size+255)/256;}
  for(0..levels) |i|{k[8]=counts[i];k[9]=offsets[i];k[10]=offsets[i]+counts[i];k[11]=if(i+1<levels)offsets[i+1] else 0;try s.dispatch(2,counts[i],&k,s.handles[8]);}
  var j=levels-1;while(j>0){j-=1;k[8]=counts[j];k[10]=offsets[j]+counts[j];k[11]=offsets[j+1]+counts[j+1];try s.dispatch(3,counts[j],&k,s.handles[8]);}
  k=s.constants(verify);k[10]=counts[0];try s.dispatch(4,s.n,&k,s.handles[8]);
 }
 pub fn pipeline(s:*Bundle,verify:bool,rebuild:bool,timed:bool) !void {
  if(timed)try ck(c.s_stamp(s.d,0));
  if(rebuild or s.active_epoch==null or s.active_epoch.?!=s.epoch or s.active_stride!=s.stride or s.active_n!=s.n){if(s.n==0){const k=s.constants(verify);try s.dispatch(16,1,&k,s.handles[8]);}else try s.compact(verify);s.active_epoch=s.epoch;s.active_stride=s.stride;s.active_n=s.n;}
  if(timed)try ck(c.s_stamp(s.d,1));
  const k=s.constants(verify);
  for([_]u32{5,6,7,8,9,10,11},0..) |pass,i|{if(s.n>0)try s.dispatch(if(pass==9 and s.vector_full)15 else pass,s.n,&k,s.handles[8]);if(timed)try ck(c.s_stamp(s.d,@intCast(i+2)));}
 }
 pub fn read(s:*Bundle,index:usize) ![]const u32 {
  const bytes=s.plan.logical[index];if(bytes>s.plan.logical[7])return error.ReadbackCapacity;
  try ck(c.s_begin(s.d));try ck(c.s_transition(s.d,s.handles[index],1));try ck(c.s_copy(s.d,s.handles[7],s.handles[index],bytes));try ck(c.s_transition(s.d,s.handles[index],0));try ck(c.s_submit(s.d,0));try ck(c.s_wait(s.d));
  const p=c.s_map(s.d,s.handles[7],bytes) orelse return error.Map;
  return @as([*]const u32,@ptrCast(@alignCast(p)))[0..@intCast(bytes/4)];
 }
 pub fn unmap(s:*Bundle) !void {try ck(c.s_unmap(s.d,s.handles[7],0));}
 pub fn convertSource(s:*Bundle,old:u64,old_kind:u32,old_cap:u32,verify:bool) !void {
  var k=s.constants(verify);k[6]=old_kind;k[7]=old_cap;try ck(c.s_transition(s.d,old,3));try s.dispatch(12,s.n,&k,old);try ck(c.s_transition(s.d,old,0));
 }
 pub fn commands(s:*Bundle,commands_:[]const entity.Command) !void {
  if(s.poisoned)return error.Poisoned;
  if(commands_.len>l.command_capacity)return error.CommandCapacity;
  for(commands_) |command|if(command.op<1 or command.op>3 or command.slot>=s.cap)return error.Command;
  if(s.epoch==std.math.maxInt(u32))return error.EpochOverflow;
  const bytes=std.mem.sliceAsBytes(commands_);const p=c.s_map(s.d,s.handles[8],0) orelse return error.Map;
  @memcpy(@as([*]u8,@ptrCast(p))[0..bytes.len],bytes);try ck(c.s_unmap(s.d,s.handles[8],bytes.len));
  try ck(c.s_begin(s.d));var k=s.constants(false);k[12]=@intCast(commands_.len);try s.dispatch(13,1,&k,s.handles[8]);try ck(c.s_submit(s.d,0));try ck(c.s_wait(s.d));
  const control=try s.read(6);const errors=control[0];const count=control[1];const epoch=control[2];try s.unmap();
  if(errors!=0 or epoch!=s.epoch+1){s.poisoned=true;return error.StructuralCommit;}
  s.n=count;s.plan.n=count;s.epoch=epoch;
 }
};
pub fn seed(id:u32,field:u32,stride:u32) u32 {
 const value:f32=switch(field){0=>@as(f32,@floatFromInt(id&1023))/1024,1=>@as(f32,@floatFromInt((id>>10)&1023))/1024,2=>@as(f32,@floatFromInt(@as(i32,@intCast(id%7))-3))/1024,3=>@as(f32,@floatFromInt(@as(i32,@intCast(id%5))-2))/1024,6=>1,7=>2,8=>1.0/256.0,else=>0};
 return switch(field){12=>id%3,14=>@intFromBool(activeId(id,stride)),15=>id,else=>@bitCast(value)};
}
pub fn activeId(id:u32,stride:u32) bool{return stride!=0 and id%stride==0;}
pub fn expected(id:u32,steps:u32,stride:u32) [l.field_count]u32 {
 var words:[l.field_count]u32=undefined;for(0..l.field_count) |f|words[f]=seed(id,@intCast(f),stride);
 const k:f64=@floatFromInt(steps);const active_:f64=if(activeId(id,stride))1 else 0;
 const coeff=((2+active_)*k*(k-1)/2+(1+active_)*k)/65536;
 const vx:f32=@bitCast(words[2]);const vy:f32=@bitCast(words[3]);const x:f32=@bitCast(words[0]);const y:f32=@bitCast(words[1]);
 words[0]=@bitCast(@as(f32,@floatCast(@as(f64,x)+(2+active_)*k*@as(f64,vx)/64+coeff)));
 words[1]=@bitCast(@as(f32,@floatCast(@as(f64,y)+(2+active_)*k*@as(f64,vy)/64-coeff)));
 words[2]=@bitCast(@as(f32,@floatCast(@as(f64,vx)+k/1024)));words[3]=@bitCast(@as(f32,@floatCast(@as(f64,vy)-k/1024)));
 return words;
}
