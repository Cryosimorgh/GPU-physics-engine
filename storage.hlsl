#include "layout.hlsl"
RWByteAddressBuffer data:register(u0);
RWByteAddressBuffer maps:register(u1);
RWByteAddressBuffer active:register(u2);
RWByteAddressBuffer scratch:register(u3);
RWByteAddressBuffer visits:register(u4);
RWByteAddressBuffer result:register(u5);
RWByteAddressBuffer control:register(u6);
ByteAddressBuffer inputData:register(t0);
uint loadField(uint i,uint f){return data.Load(address(layout,capacity,i,f));}
void storeField(uint i,uint f,uint v){data.Store(address(layout,capacity,i,f),v);}
bool isActive(uint id){if(strideActive==0)return false;return id%strideActive==0;}
void touch(uint pass,uint i){if(verify!=0){uint old;visits.InterlockedAdd(4*(pass*capacity+i),1,old);}}
uint seed(uint id,uint field){
 if(field==0)return asuint(float(id&1023u)/1024.0);
 if(field==1)return asuint(float((id>>10)&1023u)/1024.0);
 if(field==2)return asuint(float(int(id%7u)-3)/1024.0);
 if(field==3)return asuint(float(int(id%5u)-2)/1024.0);
 if(field==6)return asuint(1.0);if(field==7)return asuint(2.0);if(field==8)return asuint(1.0/256.0);
 if(field==12)return id%3u;if(field==14)return isActive(id);if(field==15)return id;return 0;
}
uint scratchWords(uint cap){return prefixWords(cap);}
[numthreads(THREADS,1,1)]void initialize(uint3 g:SV_GroupID,uint3 lane:SV_GroupThreadID){
 uint i=item(g,lane.x);if(i>=capacity)return;
 for(uint f=0;f<FIELDS;f++)storeField(i,f,i<n?seed(i,f):0xdeadbeefu);
 maps.Store(4*(2*i),i<n?i:0xffffffffu);maps.Store(4*(2*i+1),1);maps.Store(4*(2*capacity+i),i<n?i:0xffffffffu);
 active.Store(4*i,0);active.Store(4*(capacity+i),0xffffffffu);
 for(uint f=0;f<8;f++)visits.Store(4*(f*capacity+i),0);
 for(uint f=0;f<7;f++)result.Store(4*(f*capacity+i),0);
 if(i==0){active.Store(8*capacity,0);for(uint f=0;f<4+COMMAND_CAPACITY;f++)control.Store(f*4,0);control.Store(4,n);control.Store(8,epoch);
  for(uint j=0;j<guard_words;j++){data.Store(resourceBytes(0,capacity)-guard_bytes+4*j,0xbaadc0deu);maps.Store(resourceBytes(1,capacity)-guard_bytes+4*j,0xbaadc0deu);active.Store(resourceBytes(2,capacity)-guard_bytes+4*j,0xbaadc0deu);scratch.Store(resourceBytes(3,capacity)-guard_bytes+4*j,0xbaadc0deu);visits.Store(resourceBytes(4,capacity)-guard_bytes+4*j,0xbaadc0deu);result.Store(resourceBytes(5,capacity)-guard_bytes+4*j,0xbaadc0deu);control.Store(resourceBytes(6,capacity)-guard_bytes+4*j,0xbaadc0deu);}}

}
groupshared uint scan[256];
[numthreads(THREADS,1,1)]void classify(uint3 g:SV_GroupID,uint3 lane:SV_GroupThreadID){
 uint i=item(g,lane.x),l=lane.x,group=g.x+65535u*g.y;
 uint flag=0;if(i<n)flag=isActive(loadField(i,15));
 scan[l]=flag;GroupMemoryBarrierWithGroupSync();
 for(uint step=1;step<256;step*=2){uint x=l>=step?scan[l-step]:0;GroupMemoryBarrierWithGroupSync();scan[l]+=x;GroupMemoryBarrierWithGroupSync();}
 if(i<n){active.Store(4*i,flag);scratch.Store(4*(scratchWords(capacity)+guard_words+i),scan[l]-flag);storeField(i,14,flag);touch(0,i);}
 if(l==255&&group<(n+255)/256)scratch.Store(4*group,scan[l]);
}
[numthreads(THREADS,1,1)]void scan_counts(uint3 g:SV_GroupID,uint3 lane:SV_GroupThreadID){
 uint i=item(g,lane.x),l=lane.x,group=g.x+65535u*g.y;
 uint value=i<scanCount?scratch.Load(4*(scanInput+i)):0;
 scan[l]=value;GroupMemoryBarrierWithGroupSync();
 for(uint step=1;step<256;step*=2){uint v=l>=step?scan[l-step]:0;GroupMemoryBarrierWithGroupSync();scan[l]+=v;GroupMemoryBarrierWithGroupSync();}
 if(i<scanCount)scratch.Store(4*(scanOutput+i),scan[l]-value);
 if(l==255&&group<(scanCount+255)/256){if(scanCount<=256)active.Store(8*capacity,scan[l]);else scratch.Store(4*(scanParent+group),scan[l]);}
}
[numthreads(THREADS,1,1)]void add_prefix(uint3 g:SV_GroupID,uint3 lane:SV_GroupThreadID){uint i=item(g,lane.x);if(i>=scanCount)return;uint p=scratch.Load(4*(scanParent+i/256));uint v=scratch.Load(4*(scanOutput+i));scratch.Store(4*(scanOutput+i),v+p);}
[numthreads(THREADS,1,1)]void scatter_safe(uint3 g:SV_GroupID,uint3 lane:SV_GroupThreadID){uint i=item(g,lane.x);if(i>=n)return;uint flag=active.Load(4*i);if(flag==0)return;uint offset=scratch.Load(4*(scratchWords(capacity)+guard_words+i))+scratch.Load(4*(scanOutput+i/256));if(offset>=n){control.InterlockedAdd(0,1);return;}active.Store(4*(capacity+offset),i);}
[numthreads(THREADS,1,1)]void integrate(uint3 g:SV_GroupID,uint3 lane:SV_GroupThreadID){uint i=item(g,lane.x);if(i>=n)return;precise float x=asfloat(loadField(i,0)),y=asfloat(loadField(i,1)),vx=asfloat(loadField(i,2)),vy=asfloat(loadField(i,3));storeField(i,0,asuint(x+vx/64.0));storeField(i,1,asuint(y+vy/64.0));touch(1,i);}
[numthreads(THREADS,1,1)]void keys(uint3 g:SV_GroupID,uint3 lane:SV_GroupThreadID){uint i=item(g,lane.x);if(i>=n)return;int x=int(floor(asfloat(loadField(i,0))*1024.0)),y=int(floor(asfloat(loadField(i,1))*1024.0));result.Store(4*i,asuint(x)*0x9e3779b9u^asuint(y));touch(2,i);}
[numthreads(THREADS,1,1)]void update_motion(uint3 g:SV_GroupID,uint3 lane:SV_GroupThreadID){uint i=item(g,lane.x);if(i>=n)return;precise float vx=asfloat(loadField(i,2))+1.0/1024.0,vy=asfloat(loadField(i,3))-1.0/1024.0;storeField(i,2,asuint(vx));storeField(i,3,asuint(vy));precise float x=asfloat(loadField(i,0)),y=asfloat(loadField(i,1));storeField(i,0,asuint(x+vx/64.0));storeField(i,1,asuint(y+vy/64.0));touch(3,i);}
[numthreads(THREADS,1,1)]void gather(uint3 g:SV_GroupID,uint3 lane:SV_GroupThreadID){uint j=item(g,lane.x);if(j>=n||j>=active.Load(8*capacity))return;uint i=active.Load(4*(capacity+j));if(i>=n){control.InterlockedAdd(0,1);return;}precise float x=asfloat(loadField(i,0)),y=asfloat(loadField(i,1)),vx=asfloat(loadField(i,2)),vy=asfloat(loadField(i,3));storeField(i,0,asuint(x+vx/64.0));storeField(i,1,asuint(y+vy/64.0));touch(4,i);}
[numthreads(THREADS,1,1)]void full_state(uint3 g:SV_GroupID,uint3 lane:SV_GroupThreadID){uint i=item(g,lane.x);if(i>=n)return;uint h=2166136261u;for(uint f=0;f<FIELDS;f++)h=(h^loadField(i,f))*16777619u;result.Store(4*(capacity+i),h);touch(5,i);}
[numthreads(THREADS,1,1)]void full_state_vector(uint3 g:SV_GroupID,uint3 lane:SV_GroupThreadID){uint i=item(g,lane.x);if(i>=n)return;uint h=2166136261u;[unroll]for(uint f=0;f<FIELDS;f+=4){uint4 v;if(layout==0)v=data.Load4(address(layout,capacity,i,f));else v=uint4(loadField(i,f),loadField(i,f+1),loadField(i,f+2),loadField(i,f+3));h=(h^v.x)*16777619u;h=(h^v.y)*16777619u;h=(h^v.z)*16777619u;h=(h^v.w)*16777619u;}result.Store(4*(capacity+i),h);touch(5,i);}
[numthreads(THREADS,1,1)]void pack_render(uint3 g:SV_GroupID,uint3 lane:SV_GroupThreadID){uint i=item(g,lane.x);if(i>=n)return;result.Store4(4*(2*capacity+4*i),uint4(loadField(i,0),loadField(i,1),loadField(i,8),loadField(i,15)));touch(6,i);}
[numthreads(THREADS,1,1)]void consume_render(uint3 g:SV_GroupID,uint3 lane:SV_GroupThreadID){uint i=item(g,lane.x);if(i>=n)return;uint4 v=result.Load4(4*(2*capacity+4*i));result.Store(4*(6*capacity+i),v.x^((v.y<<7)|(v.y>>25))^v.z^v.w);touch(7,i);}
[numthreads(THREADS,1,1)]void convert(uint3 g:SV_GroupID,uint3 lane:SV_GroupThreadID){uint i=item(g,lane.x);if(i>=n)return;for(uint f=0;f<FIELDS;f++)storeField(i,f,inputData.Load(address(inputLayout,inputCapacity,i,f)));}
[numthreads(THREADS,1,1)]void grow_maps(uint3 g:SV_GroupID,uint3 lane:SV_GroupThreadID){uint i=item(g,lane.x);if(i>=capacity)return;uint mapped=0xffffffffu,generation=1,slot=0xffffffffu;if(i<inputCapacity){mapped=inputData.Load(8*i);generation=inputData.Load(8*i+4);}if(i<n)slot=inputData.Load(4*(2*inputCapacity+i));maps.Store(8*i,mapped);maps.Store(8*i+4,generation);maps.Store(4*(2*capacity+i),slot);}
[numthreads(THREADS,1,1)]void empty_active(uint3 g:SV_GroupID,uint3 lane:SV_GroupThreadID){if(item(g,lane.x)==0)active.Store(8*capacity,0);}
[numthreads(THREADS,1,1)]void clear_coverage(uint3 g:SV_GroupID,uint3 lane:SV_GroupThreadID){uint i=item(g,lane.x);if(i>=capacity)return;for(uint f=0;f<8;f++)visits.Store(4*(f*capacity+i),0);}
// Bounded ordered structural transaction. CPU prevalidates and reserves the
// whole command batch before submission; epoch must match exactly.
[numthreads(THREADS,1,1)]void mutate(uint3 g:SV_GroupID,uint3 lane:SV_GroupThreadID){
 if(item(g,lane.x)!=0)return;if(commandCount>COMMAND_CAPACITY||control.Load(8)!=epoch){control.InterlockedAdd(0,1);return;}
 uint count=control.Load(4);
 for(uint k=0;k<commandCount;k++){
  uint4 a=inputData.Load4(k*32),b=inputData.Load4(k*32+16);uint op=a.x,slot=a.y,gen=a.z,dense=a.w;
  if(slot>=capacity){control.InterlockedAdd(0,1);continue;}
  uint mapped=maps.Load(8*slot),generation=maps.Load(8*slot+4);
  if(op==1){if(mapped!=0xffffffffu||generation!=gen||dense!=count||count>=capacity){control.InterlockedAdd(0,1);continue;}for(uint f=0;f<FIELDS;f++)storeField(dense,f,seed(slot,f));maps.Store(8*slot,dense);maps.Store(4*(2*capacity+dense),slot);count++;}
  else if(op==2){if(mapped!=dense||generation!=gen||dense>=count||count==0){control.InterlockedAdd(0,1);continue;}uint last=count-1,moved=maps.Load(4*(2*capacity+last));if(dense!=last){for(uint f=0;f<FIELDS;f++)storeField(dense,f,loadField(last,f));maps.Store(4*(2*capacity+dense),moved);maps.Store(8*moved,dense);}maps.Store(8*slot,0xffffffffu);maps.Store(8*slot+4,b.x);maps.Store(4*(2*capacity+last),0xffffffffu);count--;}
  else if(op==3){bool valid=false;if(generation==gen&&mapped<count){valid=maps.Load(4*(2*capacity+mapped))==slot;}control.Store(4*(4+k),valid?mapped:0xffffffffu);}
 }
 control.Store(4,count);control.Store(8,epoch+1);
}
