const std=@import("std");
pub const none=std.math.maxInt(u32);
pub const Handle=packed struct {slot:u32,generation:u32};
pub const Command=extern struct {op:u32,slot:u32,generation:u32,dense:u32,next_generation:u32=0,pad:[3]u32=.{0,0,0}};
pub const Store=struct {
 allocator:std.mem.Allocator, generation:[]u32,to_dense:[]u32,dense_slot:[]u32,age:[]u32,free:std.ArrayList(u32)=.empty,count:u32=0,epoch:u32=0,
 pub fn init(a:std.mem.Allocator,capacity:u32,count:u32) !Store {
  if(count>capacity)return error.Capacity;
  const g=try a.alloc(u32,capacity);errdefer a.free(g);
  const d=try a.alloc(u32,capacity);errdefer a.free(d);
  const s=try a.alloc(u32,capacity);errdefer a.free(s);
  const age=try a.alloc(u32,capacity);errdefer a.free(age);
  var out:Store=.{.allocator=a,.generation=g,.to_dense=d,.dense_slot=s,.age=age,.count=count};errdefer out.free.deinit(a);
  @memset(g,1);@memset(d,none);@memset(s,none);@memset(age,0);
  for(0..count) |i|{d[i]=@intCast(i);s[i]=@intCast(i);}
  try out.free.ensureTotalCapacityPrecise(a,capacity);
  var i=capacity;while(i>count){i-=1;out.free.appendAssumeCapacity(i);}
  return out;
 }
 pub fn deinit(s:*Store) void {s.allocator.free(s.generation);s.allocator.free(s.to_dense);s.allocator.free(s.dense_slot);s.allocator.free(s.age);s.free.deinit(s.allocator);}
 pub fn lookup(s:*const Store,h:Handle) !u32 {
  if(h.slot>=s.generation.len or s.generation[h.slot]!=h.generation)return error.Stale;
  const d=s.to_dense[h.slot];if(d>=s.count or s.dense_slot[d]!=h.slot)return error.Stale;return d;
 }
 pub fn handle(s:*const Store,slot:u32) Handle{return .{.slot=slot,.generation=s.generation[slot]};}
 pub fn create(s:*Store) !struct{handle:Handle,command:Command} {
  if(s.free.items.len==0 or s.count>=s.dense_slot.len)return error.Capacity;
  const slot=s.free.pop().?;const d=s.count;s.count+=1;s.to_dense[slot]=d;s.dense_slot[d]=slot;s.age[slot]=0;
  return .{.handle=s.handle(slot),.command=.{.op=1,.slot=slot,.generation=s.generation[slot],.dense=d}};
 }
 pub fn destroy(s:*Store,h:Handle) !Command {
  const d=try s.lookup(h);const last=s.count-1;const moved=s.dense_slot[last];s.dense_slot[d]=moved;s.to_dense[moved]=d;s.dense_slot[last]=none;s.count-=1;s.to_dense[h.slot]=none;
  if(s.generation[h.slot]!=none){s.generation[h.slot]+=1;s.free.appendAssumeCapacity(h.slot);}
  return .{.op=2,.slot=h.slot,.generation=h.generation,.dense=d,.next_generation=s.generation[h.slot]};
 }
 pub fn tick(s:*Store) !void {for(s.dense_slot[0..s.count]) |id|s.age[id]=try std.math.add(u32,s.age[id],1);}
 pub fn expanded(s:*const Store,new_capacity:u32) !Store {
  if(new_capacity<=s.generation.len)return error.Capacity;
  var next=try Store.init(s.allocator,new_capacity,0);errdefer next.deinit();
  const old=s.generation.len;@memcpy(next.generation[0..old],s.generation);@memcpy(next.to_dense[0..old],s.to_dense);@memcpy(next.dense_slot[0..s.count],s.dense_slot[0..s.count]);@memcpy(next.age[0..old],s.age);
  // Keep reusable IDs in the same order, then add fresh IDs explicitly.
  next.free.clearRetainingCapacity();var i=new_capacity;while(i>old){i-=1;next.free.appendAssumeCapacity(@intCast(i));}for(s.free.items) |id|next.free.appendAssumeCapacity(id);
  next.count=s.count;next.epoch=s.epoch;return next;
 }
 pub fn grow(s:*Store,new_capacity:u32) !void {
  const next=try s.expanded(new_capacity);s.deinit();s.*=next;
 }
};
