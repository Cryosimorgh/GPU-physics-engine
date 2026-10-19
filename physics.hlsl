// Adapter of the byte-preserved optimized solver's projected constraints.
// Positions remain fixed during discovery/solve; publication is transactional.
#include "physics-layout.h"
#include "execution-layout.h"
#include "physics-math.hlsl"
#include "physics-constants.hlsl"
RWByteAddressBuffer source:register(u0);
RWByteAddressBuffer trial:register(u1);
RWByteAddressBuffer maps:register(u2);
RWByteAddressBuffer spatial:register(u3);
RWByteAddressBuffer m:register(u4);
RWByteAddressBuffer c:register(u5);
RWByteAddressBuffer args:register(u6);
ByteAddressBuffer unused:register(t0);
static const uint NONE=0xffffffffu;
static const float U=0.00000011920928955078125;
#define AT(name,i) G3_##name(capacity,i)
#define CT(name,i) G3_##name(contact_capacity,i)
uint indexOf(uint3 group,uint lane){uint64_t v=(uint64_t(group.x)+uint64_t(stage>>16)*group.y)*256+lane;return v>0xffffffffu?NONE:uint(v);}
uint islandIndex(uint3 g){return kick_slot+g.x+65535u*g.y;}
uint phase(){return stage&255;}
uint metaGuard(){uint at=G3_METADATA_END(capacity);for(uint k=capacity;k>256;){k=(k+255)/256;at+=16*k;}return at;}
float dt(){return asfloat(dt_bits);}
bool stopped(){return m.Load(0)!=0||m.Load(4)!=0;}
void fail(uint bit){m.InterlockedOr(0,bit);uint old;m.InterlockedCompareExchange(68,0,tick+1,old);}
float src(uint i,uint field){return asfloat(source.Load(4*(field*capacity+i)));}
float val(uint i,uint field){return asfloat(trial.Load(4*(field*capacity+i)));}
uint slot(uint i){return source.Load(4*(15*capacity+i));}
void put(uint i,uint field,float v){trial.Store(4*(field*capacity+i),asuint(v));}
float cf(uint o,uint field){return asfloat(c.Load(o+4*field));}
void cp(uint o,uint field,float v){c.Store(o+4*field,asuint(v));}
double md(uint at){uint2 v=m.Load2(at);return asdouble(v.x,v.y);}
void mdstore(uint at,double value){uint low,high;asuint(value,low,high);m.Store2(at,uint2(low,high));}
double readLambda(uint o,bool tangent){uint k=o/G3_CONTACT_BYTES;uint2 v=c.Load2(tangent?CT(LAMBDA_T,k):CT(LAMBDA_N,k));return asdouble(v.x,v.y);}
void writeLambda(uint o,bool tangent,double value){uint low,high;asuint(value,low,high);uint k=o/G3_CONTACT_BYTES;c.Store2(tangent?CT(LAMBDA_T,k):CT(LAMBDA_N,k),uint2(low,high));cp(o,tangent?11:10,float(value));if(!isfinite(float(value)))fail(16);}
uint64_t get64(uint at){uint2 v=m.Load2(at);return uint64_t(v.x)|(uint64_t(v.y)<<32);}
void set64(uint at,uint64_t value){m.Store2(at,uint2(value,value>>32));}
uint rootOf(uint a){for(uint hop=0;hop<65536;hop++){if(a>=n){fail(64);return 0;}uint b=m.Load(AT(PARENT,a));if(a==b)return a;a=b;}fail(64);return 0;}
void unite(uint a,uint b){for(uint hop=0;hop<65536;hop++){a=rootOf(a);b=rootOf(b);if(a==b)return;uint hi=max(a,b),lo=min(a,b),old;m.InterlockedMin(AT(PARENT,hi),lo,old);if(old==hi)return;a=old;b=lo;}fail(64);}
void markWake(uint i){uint old;m.InterlockedOr(AT(SOLVER_FLAG,i),2,old);if((old&2)==0)m.InterlockedAdd(60,1);}
#include "measurement-schedule.hlsl"
#define physicalBounds benchmarkPhysicalBounds
#include "billiards.hlsl"
#undef physicalBounds
#include "playground.hlsl"
#include "pool.hlsl"
#include "pool-failure-diagnostic.hlsl"
float4 physicalBounds(uint i){return fixture==13u?float4(0,0,POOL_TABLE_WIDTH,POOL_TABLE_HEIGHT):fixture==12u?float4(0,0,arenaSize()):benchmarkPhysicalBounds(i);}
float force(uint s){if((flags&1)==0)return 0;if(fixture==7)return s%2==1?-128.0:0.0;uint size=fixture==4?8:fixture==5&&((s/1024)%16==0)?16:2;uint group=fixture==5?(s/1024)*512+(s%1024)/size:s/size;
 bool hot=fixture==1?group%100==0:fixture==2?group%10==0:fixture>=3&&fixture<=5;return hot?(s%size<size/2?128.0:-128.0):0;}
[numthreads(256,1,1)]void ph_scene(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){uint i=indexOf(g,l.x);if(i>=n)return;if(fixture==13u){initializePool(i);return;}if(fixture==12u){initializePlayground(i);return;}if(fixture>=9u){initializeBilliard(i,billiardsColumns(capacity));return;}uint s=slot(i),size=fixture==0?1:fixture==4?8:fixture==5&&((s/1024)%16==0)?16:2;
 uint group=fixture==5?(s/1024)*512+(s%1024)/size:s/size,local=s%size,groups=fixture==5?(n+1)/2:(n+size-1)/size,cols=1;while(uint64_t(cols)*cols<groups)cols*=2;
 float x=float(group%cols)*4,y=float(group/cols)*4,r=0.0625,vx=0,vy=0,im=1;
 bool hot=fixture==1?group%100==0:fixture==2?group%10==0:fixture>=3&&fixture<=5;
 if(fixture==0){vx=.125;vy=.0625;}
 else if(fixture>=4&&fixture<=5){x+=(float(local)-float(size-1)*.5)*.125;}
 else if(hot){x+=local==0?-.06640625:.06640625;vx=local==0?.5:-.5;}
 else {x+=local==0?-.25:.25;vx=.125;vy=.0625;}
 if(fixture==6){vx=0;vy=0;if(s<2){x=s==0?-.06640625:.06640625;y=0;if(s==0)vx=1;}}
 if(fixture==7){x=float(s)*.125;y=0;im=s%2==0?0:1;vx=s%2==0?0:-.5;vy=0;}
 if(fixture==8){x=y=vx=vy=im=0;}
 float fields[12]={x,y,vx,vy,0,0,im,im*512,r,0,vx*vx+vy*vy,0};for(uint f=0;f<12;f++)source.Store(4*(f*capacity+i),asuint(fields[f]));
 source.Store(4*(12*capacity+i),0);source.Store(4*(13*capacity+i),fixture==6&&s!=0?1000:0);source.Store(4*(14*capacity+i),fixture==6&&s!=0?0:1);
}
[numthreads(256,1,1)]void ph_guards(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){uint i=indexOf(g,l.x);
#if G6_POOL_FAILURE_DIAGNOSTICS
 if(fixture==13u&&i<POOL_FAILURE_DIAGNOSTIC_BYTES/4)m.Store(poolBase()+POOL_FAILURE_DIAGNOSTIC_OFFSET+4*i,0);
#endif
 if(i<64){if(fixture==13u)m.Store(poolBase()+POOL_GUARD_OFFSET+4*i,0xbaadc0de);trial.Store(64*capacity+4*i,0xbaadc0de);m.Store(metaGuard()+4*i,0xbaadc0de);c.Store(G3_ARENA_END(contact_capacity)+4*i,0xbaadc0de);args.Store(G3_ARGS_END(n,flags)+4*i,0xbaadc0de);}if(i==0){m.Store(0,0);m.Store(68,0);m.Store(G4_SOURCE_GENERATION_BYTE,0);m.Store(G4_SOURCE_TICK_BYTE,NONE);m.Store(G4_SOURCE_EPOCH_BYTE,1);}}
[numthreads(256,1,1)]void ph_clear(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){if(m.Load(0)!=0)return;uint i=indexOf(g,l.x);if(i<64&&i!=0&&i!=17&&4*i!=G4_SOURCE_GENERATION_BYTE&&4*i!=G4_SOURCE_TICK_BYTE&&4*i!=G4_SOURCE_EPOCH_BYTE)m.Store(4*i,i==10&&(flags&16)!=0?NONE:0);if(i<capacity){m.Store(AT(PARENT,i),i);m.Store(AT(SIZE,i),0);m.Store(AT(CONTACT_COUNT,i),0);m.Store(AT(DEGREE,i),0);m.Store(AT(PREPARE_COVERAGE,i),0);m.Store(AT(PUBLISH_COVERAGE,i),0);m.Store(AT(SOLVER_FLAG,i),0);m.Store(AT(HEAD,i),NONE);m.Store(AT(ITERATIONS,i),0);m.Store(AT(RATIO,i),0);m.Store(AT(COLORS,i),0);}if(i<8)args.Store(4*i,0);if(fixture==13u&&i==0){m.Store(poolBase()+POOL_COMMAND_STATUS_OFFSET,0);m.Store(poolBase()+POOL_DIAGNOSTIC_OFFSET,0);}}
[numthreads(256,1,1)]void ph_execution_config(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){if(indexOf(g,l.x)==0&&!m.Load(0)){m.Store(G4_BUDGET_BYTE,sp_output);m.Store(G4_MODE_BYTE,sp_contacts);}}
[numthreads(256,1,1)]void ph_retry_admission(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){if(indexOf(g,l.x)==0&&m.Load(0)==G4_ADMISSION_ERROR&&m.Load(52)==0){m.Store(0,0);m.Store(68,0);}}
[numthreads(256,1,1)]void ph_prepare(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){if(m.Load(0)!=0)return;uint i=indexOf(g,l.x);if(i>=n)return;m.InterlockedAdd(AT(PREPARE_COVERAGE,i),1);if(i==0){m.Store4(80,uint4(G3_TAG,G3_METADATA_END(capacity),G3_ARENA_END(contact_capacity),G3_PARENT(capacity,n-1)));m.Store4(96,uint4(contact_capacity?G3_COLOR_CURSOR(contact_capacity,2*contact_capacity-1):0,metaGuard(),n,capacity));m.Store4(112,uint4(G3_CONTACT_BYTES,dt_bits,flags,tick));}
 float2 acceleration=fixture>=12u?float2(0,0):fixture>=9u?billiardsAcceleration(slot(i)):float2(force(slot(i)),0);float vx=src(i,2)+acceleration.x*dt(),vy=src(i,3)+acceleration.y*dt(),omega=src(i,5);if(fixture==12u){float2 impulse=playgroundImpulse(i);vx+=impulse.x;vy+=impulse.y;}if(fixture==13u){float2 impulse=poolImpulse(i);vx+=impulse.x;vy+=impulse.y;poolCloth(i,vx,vy,omega);}if(slot(i)==kick_slot&&tick==0)vx+=1;
 uint oldsleep=source.Load(4*(13*capacity+i));uint stable=slot(i);if(stable>=capacity){fail(128);return;}if(maps.Load(8*stable)!=i||maps.Load(8*stable+4)==0){fail(128);return;}if(oldsleep>1000||!isfinite(src(i,10))||!isfinite(src(i,11)))fail(16);if(src(i,11)<0)fail(8);bool awake=oldsleep<sleep_frames||vx!=0||vy!=0||omega!=0;
 if(!isfinite(vx)||!isfinite(vy)||!isfinite(omega)||!isfinite(src(i,0))||!isfinite(src(i,1))||!isfinite(src(i,4))||!isfinite(src(i,6))||!isfinite(src(i,7))||!isfinite(src(i,8))||!isfinite(src(i,9))||src(i,6)<0||src(i,7)<0||src(i,8)<=0||src(i,8)>=.5||src(i,9)<0||src(i,9)>1)fail(16);
 if(fixture>=9u&&fixture<=11u){uint table=stable/16u,columns=billiardsColumns(capacity),expected=(table%columns)|((table/columns)<<16);if(source.Load(4*(12*capacity+i))!=expected||src(i,8)!=BILLIARDS_RADIUS||src(i,6)!=BILLIARDS_INVERSE_MASS||src(i,7)!=BILLIARDS_INVERSE_INERTIA||src(i,9)!=BILLIARDS_WALL_RESTITUTION||max(abs(vx),abs(vy))>BILLIARDS_MAXIMUM_QUALIFIED_SPEED)fail(16);}
 if(oldsleep>=sleep_frames&&awake)markWake(i);
 uint sleep=awake&&oldsleep>=sleep_frames?0:oldsleep;m.Store(AT(FREE_SLEEP,i),sleep);m.Store(AT(FREE_VX,i),asuint(vx));m.Store(AT(FREE_VY,i),asuint(vy));m.Store(AT(FREE_OMEGA,i),asuint(omega));put(i,2,vx);put(i,3,vy);put(i,5,omega);trial.Store(4*(13*capacity+i),sleep);trial.Store(4*(14*capacity+i),awake?1:0);if(awake)m.InterlockedAdd(56,1);
}
bool exists(uint a,uint b){uint k=m.Load(AT(HEAD,a));for(uint hop=0;hop<65536;hop++){if(k==NONE)return false;if(k>=m.Load(8)||k>=contact_capacity){fail(64);return true;}uint o=CT(CONTACT,k),x=c.Load(o),y=c.Load(o+4);if(x==a&&y==b)return true;k=x==a?c.Load(o+56):c.Load(CT(NEXT_B,k));}fail(64);return true;}
void append(uint a,uint b){if(exists(a,b))return;if(phase()==8){fail(4);return;}
 float ax=val(a,0),ay=val(a,1),ra=val(a,8);bool wall=b>=n;uint w=b-n;
 precise float dx=0,dy=0,d2=0,d=0,gap,nx,ny,target;
 if(!wall){dx=ax-val(b,0);dy=ay-val(b,1);d2=dx*dx+dy*dy;d=sqrt(d2);gap=d-ra-val(b,8);nx=d2==0?-1:dx/d;ny=d2==0?0:dy/d;target=-gap/dt();if(fixture>=9u){double dx64=double(ax)-double(val(b,0)),dy64=double(ay)-double(val(b,1)),distance=dsqrt(dx64*dx64+dy64*dy64),separation=distance-double(ra)-double(val(b,8));d=float(distance);gap=float(separation);nx=distance==0?-1:float(dx64/distance);ny=distance==0?0:float(dy64/distance);target=float(-separation/double(dt()));}}
 else {float4 bounds=physicalBounds(a);gap=w==0?ax-bounds.x-ra:w==1?bounds.z-ra-ax:w==2?ay-bounds.y-ra:bounds.w-ra-ay;nx=w==0?1:w==1?-1:0;ny=w==2?1:w==3?-1:0;precise float v0=asfloat(m.Load(AT(FREE_VX,a)))*nx+asfloat(m.Load(AT(FREE_VY,a)))*ny;target=v0< -gap/dt()?max(-gap/dt(),-val(a,9)*v0):-gap/dt();}
 if(fixture==13u)target=float(poolTarget(a,b,double(nx),double(ny),double(gap)));
 uint k;m.InterlockedAdd(8,1,k);if(k>=contact_capacity){fail(1);return;}m.InterlockedAdd(12,1);m.InterlockedOr(AT(DIRTY,a),1);if(!wall)m.InterlockedOr(AT(DIRTY,b),1);
 uint o=CT(CONTACT,k);precise float aa=wall?ra:d*ra/(ra+val(b,8)),ab=wall?0:d*val(b,8)/(ra+val(b,8)),kn=val(a,6)+(wall?0:val(b,6)),kt=((!wall&&(flags&2)!=0)||(fixture==13u&&wall))?kn+val(a,7)*aa*aa+(wall?0:val(b,7)*ab*ab):0;
 c.Store3(o,uint3(a,b,0));cp(o,3,nx);cp(o,4,ny);cp(o,5,target);cp(o,6,aa);cp(o,7,ab);cp(o,8,kn);cp(o,9,kt);writeLambda(o,false,0);writeLambda(o,true,0);cp(o,12,gap);c.Store3(o+52,uint3(0,NONE,0));uint sa=slot(a),sb=wall?NONE-w:slot(b);c.Store4(o+64,uint4(sa,maps.Load(8*sa+4),sb,wall?0:maps.Load(8*sb+4)));
}
[numthreads(256,1,1)]void ph_round(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){uint i=indexOf(g,l.x);if(stopped())return;if(i==0){m.Store(12,0);m.Store(16,0);m.Store(20,0);m.InterlockedAdd(48,1);}if(i<n&&fixture>=9u&&fixture<=11u&&max(abs(val(i,2)),abs(val(i,3)))>BILLIARDS_MAXIMUM_QUALIFIED_SPEED){fail(16);return;}if(i<capacity){m.Store(AT(DIRTY,i),0);m.Store(AT(ROOT_DIRTY,i),0);}}
[numthreads(256,1,1)]void ph_append(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){uint i=indexOf(g,l.x);if(stopped())return;if(spatial.Load(0)!=0){if(i==0)fail(1|(spatial.Load(0)<<16));return;}uint64_t count=uint64_t(spatial.Load(80))|(uint64_t(spatial.Load(84))<<32);if(i>=count)return;uint pi=spatial.Load(sp_contacts+4*i);if(count>pair_capacity||pi>=pair_capacity||uint64_t(pi)>=(uint64_t(spatial.Load(8))|(uint64_t(spatial.Load(12))<<32))){fail(1);return;}uint o=sp_output+20*pi;uint4 h=spatial.Load4(o);if(h.x>=capacity||h.z>=capacity){fail(128);return;}uint a=maps.Load(8*h.x),b=maps.Load(8*h.z);if(a>=n||b>=n||maps.Load(8*h.x+4)!=h.y||maps.Load(8*h.z+4)!=h.w||slot(a)!=h.x||slot(b)!=h.z){fail(128);return;}append(a,b);}
[numthreads(256,1,1)]void ph_walls(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){uint i=indexOf(g,l.x);if(i>=n||stopped()||(flags&4)==0||trial.Load(4*(14*capacity+i))==0)return;float4 bounds=physicalBounds(i);for(uint w=0;w<4;w++){precise float gap=w==0?val(i,0)-bounds.x-val(i,8):w==1?bounds.z-val(i,8)-val(i,0):w==2?val(i,1)-bounds.y-val(i,8):bounds.w-val(i,8)-val(i,1),nx=w==0?1:w==1?-1:0,ny=w==2?1:w==3?-1:0,v0=asfloat(m.Load(AT(FREE_VX,i)))*nx+asfloat(m.Load(AT(FREE_VY,i)))*ny,target=v0< -gap/dt()?max(-gap/dt(),-val(i,9)*v0):-gap/dt();float tolerance=phase()==8?32*U*max(.001,max(abs(target),max(abs(val(i,2)),abs(val(i,3))))):0;if(fixture==13u)target=float(poolTarget(i,n+w,double(nx),double(ny),double(gap)));if((phase()!=8&&gap<=0)||val(i,2)*nx+val(i,3)*ny<target-tolerance)append(i,n+w);}}
[numthreads(256,1,1)]void ph_admit_round(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){if(indexOf(g,l.x)!=0)return;if(m.Load(0))return;
#if G5_DETERMINISTIC_MEASURE
 if(!g5MeasureAllowed())return;
#endif
 if(m.Load(12)==0){m.Store(4,1);return;}m.Store(24,0);m.Store(28,0);
#if G5_DETERMINISTIC_MEASURE
 if(phase()!=0){fail(64);return;}g5CanonicalContacts();
#endif
 if(phase()==8)fail(4);}
[numthreads(256,1,1)]void ph_graph_clear(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){uint i=indexOf(g,l.x);if(i>=capacity||stopped())return;m.Store(AT(PARENT,i),i);m.Store(AT(SIZE,i),0);m.Store(AT(CONTACT_COUNT,i),0);m.Store(AT(MEMBER_CURSOR,i),0);m.Store(AT(CONTACT_CURSOR,i),0);m.Store(AT(DEGREE,i),0);m.Store(AT(HEAD,i),NONE);for(uint k=0;k<4;k++)m.Store(AT(MASKS,i)+4*k,0);}
[numthreads(256,1,1)]void ph_union(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){uint i=indexOf(g,l.x);if(i>=m.Load(8)||stopped())return;uint o=CT(CONTACT,i),a=c.Load(o),b=c.Load(o+4);m.InterlockedAdd(AT(DEGREE,a),1);if(b<n){m.InterlockedAdd(AT(DEGREE,b),1);unite(a,b);}}
[numthreads(256,1,1)]void ph_compress(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){uint i=indexOf(g,l.x);if(i>=n||stopped()||m.Load(AT(DEGREE,i))==0)return;uint r=rootOf(i);m.Store(AT(PARENT,i),r);m.InterlockedAdd(AT(SIZE,r),1);if(m.Load(AT(DIRTY,i)))m.InterlockedOr(AT(ROOT_DIRTY,r),1);}
[numthreads(256,1,1)]void ph_contact_counts(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){uint i=indexOf(g,l.x);if(i>=m.Load(8)||stopped())return;uint o=CT(CONTACT,i),a=c.Load(o),b=c.Load(o+4),r=m.Load(AT(PARENT,a)),prev;m.InterlockedAdd(AT(CONTACT_COUNT,r),1);m.InterlockedExchange(AT(HEAD,a),i,prev);c.Store(o+56,prev);if(b<n){m.InterlockedExchange(AT(HEAD,b),i,prev);c.Store(CT(NEXT_B,i),prev);}}
groupshared uint64_t sums[256];
[numthreads(256,1,1)]void ph_scan(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){if(stopped())return;uint i=indexOf(g,l.x),lane=l.x,group=g.x+(stage>>16)*g.y;uint64_t value=i<sp_output?((stage&256)!=0?uint64_t(m.Load(sp_contacts+4*i)):get64(sp_contacts+8*i)):0;sums[lane]=value;GroupMemoryBarrierWithGroupSync();for(uint step=1;step<256;step*=2){uint64_t v=lane>=step?sums[lane-step]:0;GroupMemoryBarrierWithGroupSync();sums[lane]+=v;GroupMemoryBarrierWithGroupSync();}if(i<sp_output)set64(tick+8*i,sums[lane]-value);if(lane==255&&group<(sp_output+255)/256&&iterations!=NONE)set64(iterations+8*group,sums[lane]);}
[numthreads(256,1,1)]void ph_add(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){if(stopped())return;uint i=indexOf(g,l.x);if(i<sp_output)set64(tick+8*i,get64(tick+8*i)+get64(iterations+8*(i/256)));}
[numthreads(256,1,1)]void ph_members(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){uint i=indexOf(g,l.x);if(i>=n||stopped())return;
#if G5_DETERMINISTIC_MEASURE
 if(i==0)g5CanonicalMembers();return;
#endif
if(m.Load(AT(DEGREE,i))){uint r=m.Load(AT(PARENT,i)),rank;m.InterlockedAdd(AT(MEMBER_CURSOR,r),1,rank);uint64_t dst=get64(AT(MEMBER_START,r))+rank;if(dst>=n){fail(64);return;}m.Store(AT(MEMBERS,uint(dst)),i);m.Store(AT(LOCAL,i),rank);}uint size=m.Load(AT(SIZE,i));if(size){if(size>max_bodies||m.Load(AT(CONTACT_COUNT,i))>max_work){fail(1);return;}uint q;m.InterlockedAdd(16,1,q);if(q>=G3_ROOT_BOUND(n,flags)){fail(64);return;}m.Store(AT(ROOTS,q),i);m.InterlockedAdd(24,1);m.InterlockedMax(28,size);}}
[numthreads(256,1,1)]void ph_contact_scatter(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){uint i=indexOf(g,l.x);if(i>=m.Load(8)||stopped())return;uint o=CT(CONTACT,i),a=c.Load(o),b=c.Load(o+4),r=m.Load(AT(PARENT,a)),rank;
#if G5_DETERMINISTIC_MEASURE
 rank=i;if(i==0)m.Store(AT(CONTACT_CURSOR,r),m.Load(8));
#else
 m.InterlockedAdd(AT(CONTACT_CURSOR,r),1,rank);
#endif
uint64_t dst=get64(AT(CONTACT_START,r))+rank;if(dst>=contact_capacity){fail(64);return;}c.Store(CT(ROOT_CONTACTS,uint(dst)),i);c.Store(o+60,m.Load(AT(LOCAL,a))|((b<n?m.Load(AT(LOCAL,b)):65535)<<16));}
[numthreads(256,1,1)]void ph_args(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){uint i=indexOf(g,l.x);if(i>=G3_ARGS_CHUNKS(n,flags))return;uint graph=stopped()?0:m.Load(16),solve=stopped()?0:m.Load(20),base=i*G3_SOLVER_CHUNK_GROUPS,count=solve>base?min(G3_SOLVER_CHUNK_GROUPS,solve-base):0;args.Store3(G3_INDIRECT_HEADER_BYTES+G3_INDIRECT_STRIDE_BYTES*i,uint3(count,1,1));if(i==0){args.Store3(0,uint3(min(65535u,graph),max(1u,(graph+65534)/65535),1));args.Store(G4_INDIRECT_COUNT_BYTE,((flags&G4_GUARDED_FLAG)!=0&&solve!=0)?1:0);args.Store3(G4_INDIRECT_DISPATCH_BYTE,uint3((flags&G4_GUARDED_FLAG)!=0?min(65535u,solve):0,max(1u,(solve+65534u)/65535u),1));}}
groupshared uint blocked;
[numthreads(128,1,1)]void ph_color(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){uint q=islandIndex(g);if(q>=m.Load(16))return;if(l.x==0)blocked=stopped()?1:0;GroupMemoryBarrierWithGroupSync();if(blocked)return;uint r=m.Load(AT(ROOTS,q));if(m.Load(AT(ROOT_DIRTY,r))==0)return;if(l.x==0){uint start=uint(get64(AT(CONTACT_START,r))),length=m.Load(AT(CONTACT_COUNT,r)),colors=0;for(uint ci=0;ci<length;ci++){uint k=c.Load(CT(ROOT_CONTACTS,start+ci)),o=CT(CONTACT,k),a=c.Load(o),b=c.Load(o+4),col=NONE;for(uint word=0;word<4;word++){uint used=m.Load(AT(MASKS,a)+4*word);if(b<n)used|=m.Load(AT(MASKS,b)+4*word);if(~used){col=32*word+firstbitlow(~used);break;}}if(col>=128){fail(1);return;}uint bit=1u<<(col&31);m.InterlockedOr(AT(MASKS,a)+4*(col/32),bit);if(b<n)m.InterlockedOr(AT(MASKS,b)+4*(col/32),bit);c.Store(o+52,col);colors=max(colors,col+1);}m.Store(AT(COLORS,r),colors);}}
[numthreads(256,1,1)]void ph_color_counts(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){uint i=indexOf(g,l.x);if(i<n&&!stopped())set64(AT(COLOR_ELEMENTS,i),m.Load(AT(SIZE,i))?m.Load(AT(COLORS,i))+1:0);}
[numthreads(128,1,1)]void ph_color_ranges(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){uint q=islandIndex(g);if(q>=m.Load(16))return;if(l.x==0)blocked=stopped()?1:0;GroupMemoryBarrierWithGroupSync();if(blocked)return;
#if G5_DETERMINISTIC_MEASURE
 if(l.x==0)g5CanonicalColorRanges(m.Load(AT(ROOTS,q)));return;
#endif
uint r=m.Load(AT(ROOTS,q)),base=uint(get64(AT(COLOR_BASE,r))),colors=m.Load(AT(COLORS,r)),start=uint(get64(AT(CONTACT_START,r))),length=m.Load(AT(CONTACT_COUNT,r));if(base+colors+1>2*contact_capacity){if(l.x==0)fail(1);return;}for(uint col=l.x;col<=colors;col+=128)c.Store(CT(COLOR_CURSOR,base+col),0);DeviceMemoryBarrierWithGroupSync();for(uint ci=l.x;ci<length;ci+=128){uint k=c.Load(CT(ROOT_CONTACTS,start+ci));c.InterlockedAdd(CT(COLOR_CURSOR,base+c.Load(CT(CONTACT,k)+52)),1);}DeviceMemoryBarrierWithGroupSync();if(l.x==0){uint prefix=start;for(uint col=0;col<colors;col++){uint length=c.Load(CT(COLOR_CURSOR,base+col));c.Store(CT(COLOR_START,base+col),prefix);c.Store(CT(COLOR_CURSOR,base+col),prefix);prefix+=length;}c.Store(CT(COLOR_START,base+colors),prefix);}DeviceMemoryBarrierWithGroupSync();for(uint ci=l.x;ci<length;ci+=128){uint k=c.Load(CT(ROOT_CONTACTS,start+ci)),col=c.Load(CT(CONTACT,k)+52),at;c.InterlockedAdd(CT(COLOR_CURSOR,base+col),1,at);if(at>=contact_capacity){fail(64);return;}c.Store(CT(COLORED,at),k);}}

// The following projection/rebuild/measure equations adapt legacy sim.hlsl.
double contactMu(uint o){return fixture==13u?double(poolMu(c.Load(o+4))):.25;}
double contactTangentResidual(uint o,double vt,double kt,double ln,double lt){if(fixture!=13u)return tangentResidual(vt,kt,ln,lt);double bound=contactMu(o)*ln;return kt>0?(vt>=0?min(vt,max(0.0,lt+bound)*kt):min(-vt,max(0.0,bound-lt)*kt)):abs(lt);}
#include "projected_solver.hlsl"

float ulp(float x){uint bits=asuint(abs(x));return asfloat(bits+1)-abs(x);}
double gamma(uint k){return double(k)*double(U)/(1.0-double(k)*double(U));}
// Independent binary64 coefficients: no stored Jacobian/target is trusted.
void geometry(uint a,uint b,out double nx,out double ny,out double gap,out double target,out double aa,out double ab,out double kn,out double kt){double x=double(val(a,0)),y=double(val(a,1)),ra=double(val(a,8));bool wall=b>=n;double d=0;if(wall){uint w=b-n;float4 bounds=physicalBounds(a);gap=w==0?x-double(bounds.x)-ra:w==1?double(bounds.z)-ra-x:w==2?y-double(bounds.y)-ra:double(bounds.w)-ra-y;nx=w==0?1:w==1?-1:0;ny=w==2?1:w==3?-1:0;double v0=double(asfloat(m.Load(AT(FREE_VX,a))))*nx+double(asfloat(m.Load(AT(FREE_VY,a))))*ny;target=v0 < -gap/double(dt())?max(-gap/double(dt()),-double(val(a,9))*v0):-gap/double(dt());aa=ra;ab=0;kn=double(val(a,6));kt=0;}else{double dx=x-double(val(b,0)),dy=y-double(val(b,1));d=dsqrt(dx*dx+dy*dy);gap=d-ra-double(val(b,8));nx=d==0?-1:dx/d;ny=d==0?0:dy/d;target=-gap/double(dt());aa=d*ra/(ra+double(val(b,8)));ab=d*double(val(b,8))/(ra+double(val(b,8)));kn=double(val(a,6))+double(val(b,6));kt=(flags&2)!=0?kn+double(val(a,7))*aa*aa+double(val(b,7))*ab*ab:0;}if(fixture==13u){target=poolTarget(a,b,nx,ny,gap);if(wall)kt=kn+double(val(a,7))*aa*aa;}}
void checkContact(uint k,out uint3 stats){stats=0;if(k>=m.Load(8)||m.Load(0))return;uint o=CT(CONTACT,k),a=c.Load(o),b=c.Load(o+4);double nx,ny,gap,target,aa,ab,kn,kt;geometry(a,b,nx,ny,gap,target,aa,ab,kn,kt);double avx=val(a,2),avy=val(a,3),ao=val(a,5),bvx=b<n?val(b,2):0,bvy=b<n?val(b,3):0,bo=b<n?val(b,5):0,ln=readLambda(o,false),lt=readLambda(o,true),q=(avx-bvx)*nx+(avy-bvy)*ny-target,vt=(avx-bvx)*(-ny)+(avy-bvy)*nx-ao*aa-bo*ab,scale=max(.001,max(abs(target),max(max(abs(avx),abs(avy)),max(abs(bvx),abs(bvy))))),tol=44.0*double(U)*scale+8.0*double(U)*(abs(ao*aa)+abs(bo*ab)),rn=normalResidual(q,kn,ln),rt=contactTangentResidual(o,vt,kt,ln,lt);if(!(rn<=tol&&rt<=tol&&ln>=0&&abs(lt)<=contactMu(o)*ln+2.0*double(U)*max(ln,1e-20))){if(fixture==13u)m.InterlockedOr(poolBase()+POOL_DIAGNOSTIC_OFFSET,1);
 if(!(rn<=tol))poolFault(1,a,b,k,0,rn,tol,q,kn,0,0);
 else if(!(rt<=tol))poolFault(2,a,b,k,0,rt,tol,vt,kt,0,0);
 else if(!(ln>=0))poolFault(3,a,b,k,0,ln,0,lt,tol,0,0);
 else poolFault(4,a,b,k,0,abs(lt),contactMu(o)*ln+2.0*double(U)*max(ln,1e-20),ln,contactMu(o),0,0);
 fail(32);}if(b<n&&m.Load(AT(PARENT,a))!=m.Load(AT(PARENT,b)))fail(64);m.InterlockedMax(64,asuint(float(max(rn,rt)/max(tol,1e-30))));if(fixture>=9u)stats=uint3(b>=n?1u:0u,ln>0&&b<n?1u:0u,ln>0&&b>=n?1u:0u);}
groupshared uint3 g4ContactStats[256];
[numthreads(256,1,1)]void ph_check_contacts(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){
 uint k=indexOf(g,l.x);uint3 stats;
 if(fixture<9u){checkContact(k,stats);return;}
 // The count is immutable throughout this dispatch. This is a uniform group
 // exit; individual error returns remain inside checkContact, before reduction.
 if(indexOf(g,0)>=m.Load(8))return;
 checkContact(k,stats);g4ContactStats[l.x]=stats;GroupMemoryBarrierWithGroupSync();
 for(uint step=128;step>0;step/=2){if(l.x<step)g4ContactStats[l.x]+=g4ContactStats[l.x+step];GroupMemoryBarrierWithGroupSync();}
 if(l.x==0){uint3 total=g4ContactStats[0];if(total.x)m.InterlockedAdd(G4_WALL_CONTACTS_BYTE,total.x);if(total.y)spatial.InterlockedAdd(G4_POSITIVE_BODY_CONTACTS_BYTE,total.y);if(total.z)spatial.InterlockedAdd(G4_POSITIVE_WALL_CONTACTS_BYTE,total.z);}
}
[numthreads(256,1,1)]void ph_check_bodies(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){uint i=indexOf(g,l.x);if(i>=n||m.Load(0))return;if(fixture==13u&&i==0)poolEnergy();if(i==0&&m.Load(G4_SOURCE_GENERATION_BYTE)==NONE){fail(64);return;}double3 change=0,absolute=0;uint degree=0,k=m.Load(AT(HEAD,i));for(uint hop=0;k!=NONE&&hop<65536;hop++){if(k>=m.Load(8)||k>=contact_capacity){fail(64);return;}uint o=CT(CONTACT,k),a=c.Load(o),b=c.Load(o+4);double nx,ny,gap,target,aa,ab,kn,kt;geometry(a,b,nx,ny,gap,target,aa,ab,kn,kt);double ln=readLambda(o,false),lt=readLambda(o,true),ix=nx*ln-ny*lt,iy=ny*ln+nx*lt,sign=i==a?1:-1,arm=i==a?aa:ab;double3 dv=double3(sign*ix*double(val(i,6)),sign*iy*double(val(i,6)),-lt*arm*double(val(i,7)));change+=dv;absolute+=abs(dv);degree++;k=i==a?c.Load(o+56):c.Load(CT(NEXT_B,k));}if(k!=NONE){fail(64);return;}double3 free=double3(asfloat(m.Load(AT(FREE_VX,i))),asfloat(m.Load(AT(FREE_VY,i))),asfloat(m.Load(AT(FREE_OMEGA,i)))),result=double3(val(i,2),val(i,3),val(i,5)),bound=gamma(32*max(1u,degree))*(abs(free)+absolute)+4.0*double(U)*max(1e-6,abs(result));if(any(abs(result-free-change)>bound)){if(fixture==13u)m.InterlockedOr(poolBase()+POOL_DIAGNOSTIC_OFFSET,2);
 uint axis=abs(result.x-free.x-change.x)>bound.x?0:abs(result.y-free.y-change.y)>bound.y?1:2;
 poolFault(5,i,NONE,NONE,axis,abs(result[axis]-free[axis]-change[axis]),bound[axis],result[axis]-free[axis],change[axis],degree,0);fail(32);}if(degree==0&&(m.Load(AT(SOLVER_FLAG,i))&1)!=0)fail(64);if(m.Load(AT(PREPARE_COVERAGE,i))!=1)fail(256);float x=val(i,0)+val(i,2)*dt(),y=val(i,1)+val(i,3)*dt(),angle=val(i,4)+val(i,5)*dt();float activityEnergy=val(i,2)*val(i,2)+val(i,3)*val(i,3)+val(i,5)*val(i,5)*val(i,8)*val(i,8);if(!isfinite(x)||!isfinite(y)||!isfinite(angle)||!isfinite(activityEnergy))fail(16);if(fixture>=9u){float4 bounds=physicalBounds(i);float px=(flags&4u)!=0?clamp(x,bounds.x+val(i,8),bounds.z-val(i,8)):x,py=(flags&4u)!=0?clamp(y,bounds.y+val(i,8),bounds.w-val(i,8)):y;if(px!=val(i,0)||py!=val(i,1))m.InterlockedAdd(G4_MOVING_COUNT_BYTE,1);uint size=m.Load(AT(SIZE,i));if(size){m.InterlockedAdd(G4_ISLAND_HISTOGRAM_BYTE+4*min(7u,firstbithigh(size)),1);}}}
// Pool-only split positional stabilization. Does not modify velocities, impulse
// accumulators, or the frozen positions used by the contact oracle.
[numthreads(1,1,1)]void ph_pool_positions(){
 if(fixture!=13u||m.Load(0))return;double2 p[16],original[16];
 for(uint i=0;i<16;i++){float2 next=float2(val(i,0),val(i,1))+float2(val(i,2),val(i,3))*dt();p[i]=double2(next);original[i]=p[i];}
 
#if G6_POOL_FAILURE_DIAGNOSTICS
 double diagnosticMax=0;uint diagnosticA=NONE,diagnosticB=NONE;
#endif
 bool converged=false;for(uint iteration=0;iteration<64;iteration++){double maximum=0;
#if G6_POOL_FAILURE_DIAGNOSTICS
 diagnosticMax=0;diagnosticA=diagnosticB=NONE;
#endif

  for(uint i=0;i<16;i++)for(uint j=0;j<i;j++){double2 delta=p[i]-p[j];double squared=delta.x*delta.x+delta.y*delta.y,radius=double(val(i,8))+double(val(j,8));
   // Strict separation only: 16 binary64 epsilons cover rounded products/sum.
   // Near-boundary and overlapping pairs retain the original sqrt/correction.
   if(squared>radius*radius*1.0000000000000035527136788005009)continue;
   double distance=dsqrt(squared),penetration=radius-distance;maximum=max(maximum,penetration);
#if G6_POOL_FAILURE_DIAGNOSTICS
 if(penetration>diagnosticMax){diagnosticMax=penetration;diagnosticA=i;diagnosticB=j;}
#endif
 if(penetration>0){if(distance==0){poolFault(6,i,j,NONE,iteration,distance,0,p[i].x,p[i].y,asuint(float(p[j].x)),asuint(float(p[j].y)));fail(32);return;}double2 normal=delta/distance;double move=(penetration+4.0*double(U)*radius)*.5;p[i]+=normal*move;p[j]-=normal*move;}}
  if((flags&4u)!=0)for(uint i=0;i<16;i++)p[i]=clamp(p[i],double2(val(i,8),val(i,8)),double2(double(POOL_TABLE_WIDTH)-val(i,8),double(POOL_TABLE_HEIGHT)-val(i,8)));
#if G6_POOL_FAILURE_DIAGNOSTICS
  diagnosticMax=maximum;
#endif
  if(maximum<=1e-10){converged=true;break;}
 }
 if(!converged){
#if G6_POOL_FAILURE_DIAGNOSTICS
 poolFault(7,diagnosticA,diagnosticB,NONE,64,diagnosticMax,1e-10,diagnosticA<16?p[diagnosticA].x:0,diagnosticA<16?p[diagnosticA].y:0,0,0);
#endif
 fail(32);return;}
 for(uint i=0;i<16;i++){double2 delta=p[i]-original[i];if(max(abs(delta.x),abs(delta.y))>64.0*double(U)*double(POOL_TABLE_WIDTH)){poolFault(8,i,NONE,NONE,0,max(abs(delta.x),abs(delta.y)),64.0*double(U)*double(POOL_TABLE_WIDTH),delta.x,delta.y,asuint(float(p[i].x)),asuint(float(p[i].y)));fail(32);return;}m.Store(poolBase()+POOL_POSITION_X_OFFSET+4*i,asuint(float(p[i].x)));m.Store(poolBase()+POOL_POSITION_Y_OFFSET+4*i,asuint(float(p[i].y)));}
}
[numthreads(256,1,1)]void ph_check_pairs(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){uint k=indexOf(g,l.x);if(m.Load(0))return;uint64_t P=uint64_t(spatial.Load(8))|(uint64_t(spatial.Load(12))<<32);if(P>pair_capacity){fail(1);return;}if(k>=P)return;uint4 h=spatial.Load4(sp_output+20*k);if(h.x>=capacity||h.z>=capacity){fail(128);return;}uint a=maps.Load(8*h.x),b=maps.Load(8*h.z);if(a>=n||b>=n||maps.Load(8*h.x+4)!=h.y||maps.Load(8*h.z+4)!=h.w){fail(128);return;}float ax=val(a,0)+val(a,2)*dt(),ay=val(a,1)+val(a,3)*dt(),bx=val(b,0)+val(b,2)*dt(),by=val(b,1)+val(b,3)*dt();if(fixture==13u){float2 pa=poolNextPosition(a),pb=poolNextPosition(b);ax=pa.x;ay=pa.y;bx=pb.x;by=pb.y;}double dx=double(ax)-double(bx),dy=double(ay)-double(by),d=dsqrt(dx*dx+dy*dy),pen=max(0.0,double(val(a,8))+double(val(b,8))-d),scale=max(.001,max(max(abs(double(val(a,2))),abs(double(val(a,3)))),max(abs(double(val(b,2))),abs(double(val(b,3)))))),bound=(double(ulp(ax))+double(ulp(ay))+double(ulp(bx))+double(ulp(by)))*.5+8.0*double(U)*(d+double(val(a,8))+double(val(b,8)))+44.0*double(U)*scale*double(dt());if(pen>bound){poolFault(9,a,b,k,0,pen,bound,d,scale,asuint(ax),asuint(ay));if(fixture==13u){m.InterlockedOr(poolBase()+POOL_DIAGNOSTIC_OFFSET,4);m.Store4(poolBase()+296,uint4(a,b,asuint(float(pen)),asuint(float(bound))));}fail(32);}}
[numthreads(256,1,1)]void ph_check_guards(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){uint i=indexOf(g,l.x);if(i<64){if(fixture==13u&&m.Load(poolBase()+POOL_GUARD_OFFSET+4*i)!=0xbaadc0de)fail(512);if(trial.Load(64*capacity+4*i)!=0xbaadc0de||m.Load(metaGuard()+4*i)!=0xbaadc0de||c.Load(G3_ARENA_END(contact_capacity)+4*i)!=0xbaadc0de||args.Load(G3_ARGS_END(n,flags)+4*i)!=0xbaadc0de)fail(512);}if(i==0&&m.Load(4)==0&&m.Load(0)==0)fail(4);}
[numthreads(256,1,1)]void ph_publish(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){uint i=indexOf(g,l.x);if(i>=n||m.Load(0))return;if(i==0){m.InterlockedAdd(G4_SOURCE_GENERATION_BYTE,1);m.Store(G4_SOURCE_TICK_BYTE,tick);}float vx=val(i,2),vy=val(i,3),omega=val(i,5),x=val(i,0)+vx*dt(),y=val(i,1)+vy*dt(),angle=val(i,4)+omega*dt(),speed=vx*vx+vy*vy+omega*omega*val(i,8)*val(i,8);if(fixture==13u){float2 pos=poolNextPosition(i);x=pos.x;y=pos.y;}if((flags&4)!=0){float4 bounds=physicalBounds(i);x=clamp(x,bounds.x+val(i,8),bounds.z-val(i,8));y=clamp(y,bounds.y+val(i,8),bounds.w-val(i,8));}uint sleep=trial.Load(4*(13*capacity+i));sleep=speed<1e-8?(sleep>=1000u?1000u:sleep+1):0;source.Store(4*i,asuint(x));source.Store(4*(capacity+i),asuint(y));source.Store(4*(2*capacity+i),asuint(vx));source.Store(4*(3*capacity+i),asuint(vy));source.Store(4*(4*capacity+i),asuint(angle));source.Store(4*(5*capacity+i),asuint(omega));source.Store(4*(10*capacity+i),asuint(speed));source.Store(4*(11*capacity+i),m.Load(AT(DEGREE,i))?m.Load(AT(RATIO,m.Load(AT(PARENT,i)))):0);if(fixture==13u){source.Store(4*(12*capacity+i),poolPersistent(i));storeRolling(i,0,rolling(i,2));}source.Store(4*(13*capacity+i),sleep);source.Store(4*(14*capacity+i),sleep<sleep_frames||vx!=0||vy!=0||omega!=0?1:0);m.InterlockedAdd(AT(PUBLISH_COVERAGE,i),1);m.InterlockedAdd(52,1);}

[numthreads(256,1,1)]void ph_scene_one(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){if(indexOf(g,l.x)==0&&kick_slot<n&&fixture>=9u)initializeBilliard(kick_slot,billiardsColumns(capacity));}
[numthreads(256,1,1)]void ph_source_epoch(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){if(indexOf(g,l.x)==0)m.Store(G4_SOURCE_EPOCH_BYTE,sp_output);}
