const std=@import("std");const s=@import("storage.zig");const c=@cImport({@cInclude("physics.h");@cInclude("playground-layout.h");});const a=std.heap.c_allocator;
fn ck(x:c_int)!void{if(x==0)return error.GPU;}
pub fn main()!void{
 const d=try s.open(true);defer s.c.s_close(d);var b=try s.Bundle.init(d,100,128,1,1,0);defer b.deinit();try b.initialize();
 for(0..7)|testcase|{
  const pc=c.PhysicsConfig{.n=100,.capacity=128,.contacts=1200,.pairs=1600,.design=1,.fixture=12,.iterations=4096,.sleep_frames=20,.max_bodies=4096,.max_work=8388608,.flags=5,.kick_slot=std.math.maxInt(u32),.dt=1.0/128.0,.budget=0};
  const p=c.ph_open(@ptrCast(d),&b.handles,&pc) orelse return error.Physics;defer c.ph_close(p);try ck(c.ph_cell_mode(p,1));try ck(c.ph_scene(p));
  const before=try b.read(0);var initial:[16*128]u32=undefined;@memcpy(&initial,before[0..initial.len]);try b.unmap();
  const h=s.c.s_new(d,32,1,"bounded GPU impulse contract test");if(h==0)return error.Allocation;defer {_=s.c.s_retire(d,h);_=s.c.s_collect(d);}
  const raw=s.c.s_map(d,h,0) orelse return error.Map;const words=@as([*]u32,@ptrCast(@alignCast(raw)));const cmd=[_]u32{c.PLAY_COMMAND_MAGIC,if(testcase==6)128 else 0,if(testcase==1)2 else 1,if(testcase==2)2 else 1,@bitCast(if(testcase==4)@as(f32,2.0) else if(testcase==5)std.math.nan(f32) else @as(f32,0.8)),0,1,if(testcase==3)1 else 0};@memcpy(words[0..8],&cmd);try ck(s.c.s_unmap(d,h,32));try ck(c.ph_user_command(p,h));
  var result:c.PhysicsResult=std.mem.zeroes(c.PhysicsResult);try ck(c.ph_tick(p,0,&result));const after=try b.read(0);defer b.unmap() catch {};
  if(testcase>0){if(result.error_flags!=128 or result.published!=0 or !std.mem.eql(u32,&initial,after[0..initial.len]))return error.InvalidCommandRollback;}
  else {if(result.error_flags!=0 or result.published!=100 or result.contacts==0 or result.largest!=2)return error.ContactCoverage;var momentum:f64=0;for(0..100)|i|{const vi:f32=@bitCast(initial[2*128+i]);const vf:f32=@bitCast(after[2*128+i]);momentum+=@as(f64,vf)-vi;const x:f32=@bitCast(initial[i]);const xf:f32=@bitCast(after[i]);if(@abs(@as(f64,xf)-(@as(f64,x)+@as(f64,vf)/128))>1e-6)return error.Position;}const neighbor_before:f32=@bitCast(initial[2*128+1]);const neighbor_after:f32=@bitCast(after[2*128+1]);if(@abs(momentum-0.8)>2e-6 or neighbor_after-neighbor_before<0.2)return error.MomentumTransfer;}
 }
 if(s.c.s_errors(d)!=0)return error.Validation;
 std.debug.print("PASS valid impulse, real neighbor momentum transfer, full 100-body integration; stale generation, epoch, tick, oversized dv, NaN and invalid ID reject with bit-identical source rollback; GBV clean\n",.{});
}
