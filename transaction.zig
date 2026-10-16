// Exclusive CPU structural boundary. The bounded undo journal keeps preparation
// O(command_count), rather than copying all entity metadata for each batch.
const std=@import("std");const e=@import("entity.zig");const l=@import("layout.zig");
pub const Action=union(enum){create:void,destroy:e.Handle,lookup:e.Handle};
const Slot=struct{id:u32,generation:u32,dense:u32,age:u32};
const Dense=struct{index:u32,value:u32};
const Undo=struct{count:u32,slots:[2]Slot,slot_count:usize,dense:[2]Dense,dense_count:usize};
pub const Prepared=struct {
 model:*e.Store,commands:[l.command_capacity]e.Command=undefined,undos:[l.command_capacity]Undo=undefined,len:usize=0,undo_count:usize=0,free_length:usize,free_saved:[l.command_capacity]u32=undefined,free_saved_count:usize=0,finished:bool=false,
 fn slot(m:*e.Store,id:u32) Slot{return .{.id=id,.generation=m.generation[id],.dense=m.to_dense[id],.age=m.age[id]};}
 pub fn rollback(p:*Prepared) void {
  if(p.finished)return;var j=p.undo_count;while(j>0){j-=1;const u=p.undos[j];for(u.slots[0..u.slot_count]) |v|{p.model.generation[v.id]=v.generation;p.model.to_dense[v.id]=v.dense;p.model.age[v.id]=v.age;}for(u.dense[0..u.dense_count]) |v|p.model.dense_slot[v.index]=v.value;p.model.count=u.count;}
  p.model.free.items.len=p.free_length;@memcpy(p.model.free.items[p.free_length-p.free_saved_count..],p.free_saved[0..p.free_saved_count]);p.finished=true;
 }
 pub fn publish(p:*Prepared) !void {if(p.finished)return error.Transaction;p.model.epoch=try std.math.add(u32,p.model.epoch,1);p.finished=true;}
};
pub fn prepare(m:*e.Store,actions:[]const Action) !Prepared {
 if(actions.len>l.command_capacity)return error.CommandCapacity;if(m.epoch==std.math.maxInt(u32))return error.EpochOverflow;
 var p:Prepared=.{.model=m,.free_length=m.free.items.len};p.free_saved_count=@min(actions.len,m.free.items.len);@memcpy(p.free_saved[0..p.free_saved_count],m.free.items[m.free.items.len-p.free_saved_count..]);errdefer p.rollback();
 for(actions) |action| {
  switch(action){
   .create=>{
    if(m.free.items.len==0)return error.Capacity;const id=m.free.items[m.free.items.len-1];
    p.undos[p.undo_count]=.{.count=m.count,.slots=.{Prepared.slot(m,id),undefined},.slot_count=1,.dense=.{.{.index=m.count,.value=m.dense_slot[m.count]},undefined},.dense_count=1};p.undo_count+=1;p.commands[p.len]=(try m.create()).command;
   },
   .destroy=>|h|{
    const d=try m.lookup(h);const last=m.count-1;const moved=m.dense_slot[last];
    p.undos[p.undo_count]=.{.count=m.count,.slots=.{Prepared.slot(m,h.slot),Prepared.slot(m,moved)},.slot_count=2,.dense=.{.{.index=d,.value=m.dense_slot[d]},.{.index=last,.value=m.dense_slot[last]}},.dense_count=2};p.undo_count+=1;p.commands[p.len]=try m.destroy(h);
   },
   .lookup=>|h|{if(h.slot>=m.generation.len)return error.Stale;p.commands[p.len]=.{.op=3,.slot=h.slot,.generation=h.generation,.dense=0};},
  }p.len+=1;
 }
 return p;
}
