// Separate test executable: validates compaction of already-mutated resident
// values without changing the executable used for matched layout measurements.
const std=@import("std");const s=@import("storage.zig");const e=s.entity;const l=s.l;const c=s.c;const tx=@import("transaction.zig");const a=std.heap.c_allocator;
fn require(v:bool) !void {if(!v)return error.Adversarial;}
fn check(b:*s.Bundle,m:*e.Store) !u64 {
 const words=try b.read(0);var compared:u64=0;
 for(0..m.count) |dense|{const id=m.dense_slot[dense];const wanted=s.expected(id,m.age[id],b.stride);for(wanted,0..) |w,f|{try require(words[@intCast((try l.address(b.kind,b.cap,dense,f))/4)]==w);compared+=1;}}
 for(words[@intCast((b.plan.logical[0]-l.guard_bytes)/4)..]) |w|try require(w==0xbaadc0de);try b.unmap();
 const maps=try b.read(1);for(0..b.cap) |i|{try require(maps[2*i]==m.to_dense[i] and maps[2*i+1]==m.generation[i] and maps[2*@as(usize,b.cap)+i]==m.dense_slot[i]);}try b.unmap();return compared;
}
pub fn main() !void {
 const args=try std.process.argsAlloc(a);defer std.process.argsFree(a,args);if(args.len!=4)return error.Argument;
 const n=try std.fmt.parseInt(u32,args[1],10);const kind=try std.fmt.parseInt(u32,args[2],10);if(n<100000)return error.Argument;
 const d=try s.open(true);defer c.s_close(d);const cap=try l.capacityFor(try l.add(n,32));var b=try s.Bundle.init(d,n,cap,kind,10,0);defer b.deinit();try b.initialize();var model=try e.Store.init(a,cap,n);defer model.deinit();
 try s.ck(c.s_begin(d));try b.pipeline(true,false,false);try s.ck(c.s_submit(d,0));try s.ck(c.s_wait(d));try model.tick();const before=try check(&b,&model);
 const ids=[_]u32{0,n/2,n-1,65535,65536};var actions:[15]tx.Action=undefined;
 for(ids,0..) |id,j|actions[j]=.{.destroy=model.handle(id)};
 for(5..10) |j|actions[j]=.{.create={}};
 for(ids,0..) |id,j|actions[10+j]=.{.lookup=model.handle(id)};
 var pending=try tx.prepare(&model,&actions);errdefer pending.rollback();try b.commands(pending.commands[0..pending.len]);try pending.publish();const after=try check(&b,&model);
 const control=try b.read(6);for(10..15) |j|try require(control[4+j]==e.none);try b.unmap();
 try s.ck(c.s_begin(d));const k=b.constants(true);try b.dispatch(17,b.cap,&k,b.handles[8]);try b.pipeline(true,false,false);try s.ck(c.s_submit(d,0));try s.ck(c.s_wait(d));try model.tick();const post=try check(&b,&model);
 // Exact command-capacity edge: the final lookup occupies control[1027].
 const query_handle=model.handle(0);const wanted=try model.lookup(query_handle);var queries:[l.command_capacity]tx.Action=undefined;@memset(&queries,.{.lookup=query_handle});var maximum=try tx.prepare(&model,&queries);try b.commands(maximum.commands[0..maximum.len]);try maximum.publish();
 const query_result=try b.read(6);for(0..l.command_capacity) |j|try require(query_result[4+j]==wanted);try b.unmap();
 var overflow:[l.command_capacity+1]e.Command=undefined;@memset(&overflow,.{.op=3,.slot=0,.generation=query_handle.generation,.dense=0});const prior_fence=c.s_fence(d);if(b.commands(&overflow)) |_| {return error.ExpectedCommandRejection;}else |err|{if(err!=error.CommandCapacity)return err;}try require(c.s_fence(d)==prior_fence);
 // Test resource-generation rejection after the SAME table index is reused.
 const old=c.s_new(d,65536,0,"resource-generation old");try require(old!=0);try s.ck(c.s_retire(d,old));_=c.s_collect(d);const replacement=c.s_new(d,65536,0,"resource-generation replacement");try require(replacement!=0 and @as(u32,@truncate(old))==@as(u32,@truncate(replacement)) and old!=replacement);try require(c.s_retire(d,old)==0);try s.ck(c.s_retire(d,replacement));_=c.s_collect(d);
 try require(c.s_errors(d)==0);
 const output=try std.json.Stringify.valueAlloc(a,.{.status="MUTATED_PAYLOAD_COMPACTION_VERIFIED",.n=n,.layout=kind,.words_before_compaction=before,.words_immediately_after_compaction=after,.words_after_next_pipeline=post,.mapping_entries_per_check=@as(u64,cap)*3,.max_command_batch_verified=l.command_capacity,.over_capacity_rejected_before_submission=true,.old_generations_rejected=true,.reused_resource_index_rejects_old_generation=true,.gpu_based_validation=true,.gpu_validation_errors=c.s_errors(d)},.{.whitespace=.indent_2});defer a.free(output);try std.fs.cwd().writeFile(.{.sub_path=args[3],.data=output});
 std.debug.print("MUTATED PAYLOAD VERIFIED n={} layout={} words={}\n",.{n,kind,before+after+post});
}
