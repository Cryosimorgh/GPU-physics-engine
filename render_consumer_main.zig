const std=@import("std");const s=@import("storage.zig");const c=@cImport({@cInclude("viewer.h");});
pub fn main()!void{
 const a=std.heap.c_allocator;const args=try std.process.argsAlloc(a);defer std.process.argsFree(a,args);
 var nonblocking:u32=0;var profile:u32=9;var samples:u32=16;var out:[:0]const u8="consumer.json";
 var i:usize=1;while(i<args.len):(i+=1){const flag=args[i];i+=1;if(i==args.len)return error.Argument;
  if(std.mem.eql(u8,flag,"--nonblocking"))nonblocking=try std.fmt.parseInt(u32,args[i],10) else if(std.mem.eql(u8,flag,"--out"))out=args[i] else if(std.mem.eql(u8,flag,"--profile"))profile=try std.fmt.parseInt(u32,args[i],10) else if(std.mem.eql(u8,flag,"--samples"))samples=try std.fmt.parseInt(u32,args[i],10) else return error.Argument;}
 if((profile!=9 and profile!=13) or samples>32 or nonblocking>1)return error.Config;
 const d=try s.open(samples==0);defer s.c.s_close(d);var b=try s.Bundle.init(d,16,try s.l.capacityFor(16),1,1,0);defer b.deinit();try b.initialize();
 if(c.viewer_consumer_mode_test(@ptrCast(d),&b.handles,profile,samples,nonblocking,out.ptr)==0)return error.Consumer;
}
