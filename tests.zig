const std=@import("std");const e=@import("entity.zig");const l=@import("layout.zig");
test "identity randomized swap compaction and generation reuse independent model" {
 var s=try e.Store.init(std.testing.allocator,256,0);defer s.deinit();
 var live:[256]?e.Handle=.{null}**256;var random=std.Random.DefaultPrng.init(713);
 for(0..20000) |_| {
  const slot=random.random().uintLessThan(u32,256);
  if(live[slot]) |h|{_=try s.destroy(h);live[slot]=null;try std.testing.expectError(error.Stale,s.lookup(h));}
  else if(s.free.items.len>0){const v=try s.create();live[v.handle.slot]=v.handle;}
  var count:u32=0;
  for(live,0..) |h,i|if(h) |handle|{count+=1;const d=try s.lookup(handle);try std.testing.expectEqual(@as(u32,@intCast(i)),s.dense_slot[d]);};
  try std.testing.expectEqual(count,s.count);
 }
 try s.grow(512);for(live) |h|if(h) |handle|{_=try s.lookup(handle);};
}
test "generation wrap never aliases and failed create/delete leave count unchanged" {
 try std.testing.expectEqual(@as(usize,8),@sizeOf(e.Handle));try std.testing.expectEqual(@as(u64,0x1234567887654321),@as(u64,@bitCast(e.Handle{.slot=0x87654321,.generation=0x12345678})));
 var s=try e.Store.init(std.testing.allocator,1,1);defer s.deinit();s.generation[0]=e.none;const old=s.handle(0);_=try s.destroy(old);try std.testing.expectEqual(@as(u32,0),s.count);try std.testing.expectError(error.Capacity,s.create());try std.testing.expectError(error.Stale,s.destroy(old));
}
test "generated layouts bijection boundaries and checked arithmetic" {
 for([_]u64{32,64}) |cap|for(0..3) |kind|{var seen:[1024]bool=.{false}**1024;for(0..@intCast(cap)) |i|for(0..16) |f|{const word=try l.address(@intCast(kind),cap,i,f)/4;try std.testing.expect(!seen[@intCast(word)]);seen[@intCast(word)]=true;};for(seen[0..@intCast(cap*16)]) |yes|try std.testing.expect(yes);};
 for([_]u64{1,31,32,33,65535,65536,100000,1000000,10000000}) |n|{
  const cap=try l.padded(n);for(0..3) |kind|{const end=try l.mul(cap,64);for([_]u64{0,n-1}) |i|for(0..16) |f|try std.testing.expect(try l.address(@intCast(kind),cap,i,f)<end);}
 }
 try std.testing.expectError(error.Overflow,l.mul(std.math.maxInt(u64),64));try std.testing.expectError(error.Overflow,l.padded(std.math.maxInt(u64)));
 try std.testing.expectError(error.AddressOverflow,l.capacityFor(std.math.maxInt(u32)));try std.testing.expectError(error.AddressOverflow,l.capacityFor(67108864));try std.testing.expectEqual(@as(u32,67108832),try l.capacityFor(67108832));
}
test "bounded structural transaction rollback preserves exact mappings and reusable IDs" {
 const tx=@import("transaction.zig");var m=try e.Store.init(std.testing.allocator,32,8);defer m.deinit();
 const stale=e.Handle{.slot=2,.generation=0};const before=m.free.items[m.free.items.len-1];
 const invalid=[_]tx.Action{.{.destroy=m.handle(3)},.{.create={}},.{.create={}},.{.destroy=stale}};
 try std.testing.expectError(error.Stale,tx.prepare(&m,&invalid));try std.testing.expectEqual(@as(u32,8),m.count);try std.testing.expectEqual(before,m.free.items[m.free.items.len-1]);
 for(0..8) |i|try std.testing.expectEqual(@as(u32,@intCast(i)),try m.lookup(m.handle(@intCast(i))));
 var too_many:[1025]tx.Action=undefined;@memset(&too_many,.{.create={}});try std.testing.expectError(error.CommandCapacity,tx.prepare(&m,&too_many));
 var pending=try tx.prepare(&m,&.{.{.destroy=m.handle(3)},.{.create={}}});try pending.publish();try std.testing.expectEqual(@as(u32,1),m.epoch);
}
test "CPU growth allocation failure preserves old authority transactionally" {
 for(0..5) |index|{
  var m=try e.Store.init(std.testing.allocator,32,8);defer m.deinit();
  var fail=std.testing.FailingAllocator.init(std.testing.allocator,.{.fail_index=index});m.allocator=fail.allocator();
  try std.testing.expectError(error.OutOfMemory,m.grow(64));m.allocator=std.testing.allocator;
  try std.testing.expectEqual(@as(u32,8),m.count);for(0..8) |i|try std.testing.expectEqual(@as(u32,@intCast(i)),try m.lookup(m.handle(@intCast(i))));
 }
}
