// Same accumulated projected Gauss-Seidel constraints as reference/sim.hlsl.
// Binary64 transient accumulators fix the independently demonstrated f32
// residual cancellation. G1 state and the acceptance envelope remain f32.
struct Body {double vx,vy,omega,im,ii;uint sleep;};
#ifndef G5_BODY_CACHE
#define G5_BODY_CACHE 0
#endif
#ifndef G5_SYNC_PROBE
#define G5_SYNC_PROBE 0
#endif
#ifndef G5_PROFILE_COUNTS
#define G5_PROFILE_COUNTS 0
#endif
#if G5_PROFILE_COUNTS
// Per-invocation logical body accesses, not physical GPU transactions.
static uint g5Gets=0,g5Puts=0;
#endif
#if G5_BODY_CACHE
// Disjoint modes alias one 28 KiB arena: small islands retain cached masses;
// larger islands cache 1024 f64 velocity triples plus u32 sleep state, while
// immutable masses remain in G1 storage. Together with two residual arrays
// and the two scalar flags this is 30,728 bytes, below the 32 KiB API limit.
static const uint G5_CACHE_BODIES=1024;
groupshared uint g5State[7*1024];
double3 g5Velocity(uint local){uint at=6*local;return double3(asdouble(g5State[at],g5State[at+1]),asdouble(g5State[at+2],g5State[at+3]),asdouble(g5State[at+4],g5State[at+5]));}
void g5VelocityStore(uint local,double3 v){uint at=6*local,lo,hi;asuint(v.x,lo,hi);g5State[at]=lo;g5State[at+1]=hi;asuint(v.y,lo,hi);g5State[at+2]=lo;g5State[at+3]=hi;asuint(v.z,lo,hi);g5State[at+4]=lo;g5State[at+5]=hi;}
#else
groupshared double3 velocities[G3_LOCAL_BODIES];
groupshared uint sleepState[G3_LOCAL_BODIES];
groupshared float2 masses[G3_LOCAL_BODIES];
#endif
groupshared double residuals[128];
#ifndef G5_RELAXATION_POLICY
// Keep the qualified fixed policy in production: the adaptive candidate
// failed the bounded 256/1024 chain controls. Policies 2/3/4 are sweep-only opt-in.
#define G5_RELAXATION_POLICY 1
#endif
#ifndef G5_TRACE
#define G5_TRACE 0
#endif
#if G5_RELAXATION_POLICY >= 2
groupshared double absoluteResiduals[128];
#endif
groupshared uint localMode;
uint g5StorageMode(uint size){
#if G5_BODY_CACHE
 return size<=G3_LOCAL_BODIES?1:(size<=G5_CACHE_BODIES?2:0);
#else
 return size<=G3_LOCAL_BODIES?1:0;
#endif
}
bool g5LocalValid(uint local){
#if G5_BODY_CACHE
 return local<(localMode==1?G3_LOCAL_BODIES:G5_CACHE_BODIES);
#else
 return local<G3_LOCAL_BODIES;
#endif
}
Body bodyAt(uint i,uint local){Body b=(Body)0;if(i>=n)return b;
 if(localMode&&!g5LocalValid(local)){fail(64);return b;}
#if G5_PROFILE_COUNTS
 g5Gets++;
#endif
 if(localMode){
#if G5_BODY_CACHE
  double3 v=g5Velocity(local);b.sleep=g5State[(localMode==1?8*G3_LOCAL_BODIES:6*G5_CACHE_BODIES)+local];
  if(localMode==1){b.im=asfloat(g5State[6*G3_LOCAL_BODIES+2*local]);b.ii=asfloat(g5State[6*G3_LOCAL_BODIES+2*local+1]);}else{b.im=val(i,6);b.ii=val(i,7);}
#else
  double3 v=velocities[local];b.sleep=sleepState[local];b.im=masses[local].x;b.ii=masses[local].y;
#endif
  b.vx=v.x;b.vy=v.y;b.omega=v.z;
 }else{b.vx=md(AT(WORK_VX,i));b.vy=md(AT(WORK_VY,i));b.omega=md(AT(WORK_OMEGA,i));b.sleep=trial.Load(4*(13*capacity+i));b.im=val(i,6);b.ii=val(i,7);}return b;
}
void storeBody(uint i,uint local,Body b){
 if(localMode&&!g5LocalValid(local)){fail(64);return;}
#if G5_PROFILE_COUNTS
 g5Puts++;
#endif
 if(localMode){
#if G5_BODY_CACHE
  g5VelocityStore(local,double3(b.vx,b.vy,b.omega));g5State[(localMode==1?8*G3_LOCAL_BODIES:6*G5_CACHE_BODIES)+local]=b.sleep;
#else
  velocities[local]=double3(b.vx,b.vy,b.omega);sleepState[local]=b.sleep;
#endif
 }else{mdstore(AT(WORK_VX,i),b.vx);mdstore(AT(WORK_VY,i),b.vy);mdstore(AT(WORK_OMEGA,i),b.omega);trial.Store(4*(13*capacity+i),b.sleep);if(b.sleep==0)trial.Store(4*(14*capacity+i),1);}}
double tolerance(Body a,Body b,double target){return 32.0*double(U)*max(.001,max(abs(target),max(max(abs(a.vx),abs(a.vy)),max(abs(b.vx),abs(b.vy)))));}
double relative(uint o,bool tangent,bool rounded){uint packed=c.Load(o+60);Body a=bodyAt(c.Load(o),packed&65535),b=bodyAt(c.Load(o+4),packed>>16);if(rounded){a.vx=double(float(a.vx));a.vy=double(float(a.vy));a.omega=double(float(a.omega));b.vx=double(float(b.vx));b.vy=double(float(b.vy));b.omega=double(float(b.omega));}double nx=cf(o,3),ny=cf(o,4);return tangent?(a.vx-b.vx)*(-ny)+(a.vy-b.vy)*nx-a.omega*double(cf(o,6))-b.omega*double(cf(o,7)):(a.vx-b.vx)*nx+(a.vy-b.vy)*ny;}
void delta(uint o,double dl,double ft){uint i=c.Load(o),j=c.Load(o+4),packed=c.Load(o+60);double nx=cf(o,3),ny=cf(o,4),ix=nx*dl-ny*ft,iy=ny*dl+nx*ft;Body a=bodyAt(i,packed&65535);a.vx+=ix*a.im;a.vy+=iy*a.im;a.omega-=ft*double(cf(o,6))*a.ii;if(dl!=0||ft!=0){if(a.sleep>=sleep_frames)markWake(i);a.sleep=0;}storeBody(i,packed&65535,a);if(j<n){Body b=bodyAt(j,packed>>16);b.vx-=ix*b.im;b.vy-=iy*b.im;b.omega-=ft*double(cf(o,7))*b.ii;if(dl!=0||ft!=0){if(b.sleep>=sleep_frames)markWake(j);b.sleep=0;}storeBody(j,packed>>16,b);}}
// 0: unchanged PGS control; 1: historical >=64-body fixed SOR control;
// 2: original residual policy; 3: one budgeted restart; 4: residual-gated restart.
// Normal impulses remain projected; tangent updates use the same Coulomb bound.
void applyColor(uint r,uint col,uint lane,bool rebuild,double relaxation){uint base=uint(get64(AT(COLOR_BASE,r))),first=c.Load(CT(COLOR_START,base+col)),end=c.Load(CT(COLOR_START,base+col+1));for(uint begin=first;begin<end;begin+=128){if(begin+lane<end){uint o=CT(CONTACT,c.Load(CT(COLORED,begin+lane)));if(rebuild){double ln=readLambda(o,false),lt=readLambda(o,true);if(ln!=0||lt!=0)delta(o,ln,lt);}else{double kn=cf(o,8),ln=readLambda(o,false);if(kn>0){double next=max(0.0,ln+relaxation*(double(cf(o,5))-relative(o,false,false))/kn);if(next!=ln){writeLambda(o,false,next);delta(o,next-ln,0);}}double kt=cf(o,9);if(kt>0){double lt=readLambda(o,true),bound=contactMu(o)*readLambda(o,false),next=clamp(lt-relative(o,true,false)/kt,-bound,bound);if(next!=lt){writeLambda(o,true,next);delta(o,0,next-lt);}}c.Store(o+8,c.Load(o+8)+1);}}if(localMode==1)GroupMemoryBarrierWithGroupSync();else DeviceMemoryBarrierWithGroupSync();}}
double measure(uint r,uint lane,out double absoluteResidual){
 double ratio=0,raw=0;
 uint begin=uint(get64(AT(CONTACT_START,r))),end=begin+m.Load(AT(CONTACT_COUNT,r));
 for(uint ci=begin+lane;ci<end;ci+=128){
  uint o=CT(CONTACT,c.Load(CT(ROOT_CONTACTS,ci))),packed=c.Load(o+60);
  Body a=bodyAt(c.Load(o),packed&65535),b=bodyAt(c.Load(o+4),packed>>16);
  double tol=tolerance(a,b,double(cf(o,5))),kn=cf(o,8),ln=readLambda(o,false),q=relative(o,false,true)-double(cf(o,5)),res=normalResidual(q,kn,ln);
  ratio=max(ratio,res/tol);raw=max(raw,res);
  double kt=cf(o,9);
  if(kt>0){double lt=readLambda(o,true),resT=contactTangentResidual(o,relative(o,true,true),kt,ln,lt);ratio=max(ratio,resT/tol);raw=max(raw,resT);}
 }
 residuals[lane]=ratio;
#if G5_RELAXATION_POLICY >= 2
 absoluteResiduals[lane]=raw;
#endif
 GroupMemoryBarrierWithGroupSync();
 for(uint step=64;step>0;step/=2){
  if(lane<step){residuals[lane]=max(residuals[lane],residuals[lane+step]);
#if G5_RELAXATION_POLICY >= 2
   absoluteResiduals[lane]=max(absoluteResiduals[lane],absoluteResiduals[lane+step]);
#endif
  }
  GroupMemoryBarrierWithGroupSync();
 }
 absoluteResidual=0;
#if G5_RELAXATION_POLICY >= 2
 absoluteResidual=absoluteResiduals[0];
#endif
 return residuals[0];
}
// Diagnostic-only ABI v1: 66 unused 80-byte contact records per queue entry,
// after the actual contact count. No allocation or simulation header mutation.
// u32 magic/version/root/iteration; f64 raw/min/previous/contraction/omegaIn/
// omegaOut; u32 event/policy/reserved; f32 KKT ratio. Slots 64/65: final/restart.
// The harness checks complete trace coverage. Insufficient room omits trace,
// never contact work; all indices/byte offsets are checked in uint64 arithmetic.
void g5TraceDouble(uint at,double value){
#if G5_TRACE
 uint low,high;asuint(value,low,high);c.Store2(at,uint2(low,high));
#endif
}
void g5Trace(uint r,uint queue,uint window,uint completed,double raw,double minimum,double previous,double contraction,double before,double after,uint event,double ratio){
#if G5_TRACE
 uint64_t slot=uint64_t(m.Load(8))+66ull*uint64_t(queue)+uint64_t(window);
 if(window>65||slot>=uint64_t(contact_capacity)||80ull*slot+80ull>0xffffffffull)return;
 uint o=uint(80ull*slot);
 c.Store4(o,uint4(0x47355452,1,r,completed));
 g5TraceDouble(o+16,raw);g5TraceDouble(o+24,minimum);
 g5TraceDouble(o+32,previous);g5TraceDouble(o+40,contraction);
 g5TraceDouble(o+48,before);g5TraceDouble(o+56,after);
 c.Store4(o+64,uint4(event,G5_RELAXATION_POLICY,0,asuint(float(ratio))));
#endif
}
void g5InitializeMass(uint i,uint local){if(localMode==1){
 if(local>=G3_LOCAL_BODIES){fail(64);return;}
#if G5_BODY_CACHE
 g5State[6*G3_LOCAL_BODIES+2*local]=asuint(val(i,6));g5State[6*G3_LOCAL_BODIES+2*local+1]=asuint(val(i,7));
#else
 masses[local]=float2(val(i,6),val(i,7));
#endif
}}
void loadIsland(uint r,uint lane,bool freeState){uint start=uint(get64(AT(MEMBER_START,r))),size=m.Load(AT(SIZE,r));for(uint mi=lane;mi<size;mi+=128){uint i=m.Load(AT(MEMBERS,start+mi)),local=m.Load(AT(LOCAL,i));g5InitializeMass(i,local);Body b=(Body)0;b.im=val(i,6);b.ii=val(i,7);b.vx=freeState?double(asfloat(m.Load(AT(FREE_VX,i)))):md(AT(WORK_VX,i));b.vy=freeState?double(asfloat(m.Load(AT(FREE_VY,i)))):md(AT(WORK_VY,i));b.omega=freeState?double(asfloat(m.Load(AT(FREE_OMEGA,i)))):md(AT(WORK_OMEGA,i));b.sleep=freeState?m.Load(AT(FREE_SLEEP,i)):trial.Load(4*(13*capacity+i));storeBody(i,local,b);}if(localMode==1)GroupMemoryBarrierWithGroupSync();else DeviceMemoryBarrierWithGroupSync();}
void storeIsland(uint r,uint lane,bool mark){uint start=uint(get64(AT(MEMBER_START,r))),size=m.Load(AT(SIZE,r));for(uint mi=lane;mi<size;mi+=128){uint i=m.Load(AT(MEMBERS,start+mi));Body b=bodyAt(i,m.Load(AT(LOCAL,i)));if(localMode){mdstore(AT(WORK_VX,i),b.vx);mdstore(AT(WORK_VY,i),b.vy);mdstore(AT(WORK_OMEGA,i),b.omega);}put(i,2,float(b.vx));put(i,3,float(b.vy));put(i,5,float(b.omega));trial.Store(4*(13*capacity+i),b.sleep);if(b.sleep==0)trial.Store(4*(14*capacity+i),1);if(mark){uint old;m.InterlockedOr(AT(SOLVER_FLAG,i),1,old);if((old&1)==0)m.InterlockedAdd(32,1);}}DeviceMemoryBarrierWithGroupSync();}
// Diagnostic-only synthetic synchronization/reduction floor. It performs no
// impulse updates and MUST reject/roll back; its timing is not additive to the
// real solver, because memory pressure and barriers overlap in the real kernel.
void g5SyncReduction(uint lane){residuals[lane]=double(lane);GroupMemoryBarrierWithGroupSync();for(uint step=64;step>0;step/=2){if(lane<step)residuals[lane]=max(residuals[lane],residuals[lane+step]);GroupMemoryBarrierWithGroupSync();}if(lane==0&&m.Load(8)<contact_capacity)c.Store(CT(CONTACT,contact_capacity-1)+76,asuint(float(residuals[0])));}
void g5SyncColors(uint r,uint lane,uint colors){uint base=uint(get64(AT(COLOR_BASE,r)));for(uint col=0;col<colors;col++){uint first=c.Load(CT(COLOR_START,base+col)),end=c.Load(CT(COLOR_START,base+col+1));for(uint begin=first;begin<end;begin+=128)DeviceMemoryBarrierWithGroupSync();}}
double g5CounterSum(uint value,uint lane){residuals[lane]=double(value);GroupMemoryBarrierWithGroupSync();for(uint step=64;step>0;step/=2){if(lane<step)residuals[lane]+=residuals[lane+step];GroupMemoryBarrierWithGroupSync();}double result=residuals[0];GroupMemoryBarrierWithGroupSync();return result;}
void g5ProfileEnd(uint r,uint lane,uint completed,uint rebuilds,uint restarts){
#if G5_PROFILE_COUNTS
 uint gets=uint(g5CounterSum(g5Gets,lane)),puts=uint(g5CounterSum(g5Puts,lane));
 if(lane==0&&m.Load(16)==1&&m.Load(8)<contact_capacity){uint o=CT(CONTACT,contact_capacity-1);c.Store4(o,uint4(0x4735434e,1,localMode,n));c.Store4(o+16,uint4(gets,puts,rebuilds,restarts));c.Store4(o+32,uint4(completed,G5_RELAXATION_POLICY,G5_BODY_CACHE,G5_SYNC_PROBE));c.Store2(o+48,uint2(m.Load(AT(COLORS,r)),m.Load(8)));}
#endif
}
[numthreads(128,1,1)]void ph_ready(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){uint q=islandIndex(g),lane=l.x;if(q>=m.Load(16))return;if(lane==0)blocked=stopped()?1:0;GroupMemoryBarrierWithGroupSync();if(blocked)return;uint r=m.Load(AT(ROOTS,q));if(m.Load(AT(ROOT_DIRTY,r))==0)return;if(lane==0)localMode=g5StorageMode(m.Load(AT(SIZE,r)));GroupMemoryBarrierWithGroupSync();loadIsland(r,lane,true);for(uint col=0;col<m.Load(AT(COLORS,r));col++)applyColor(r,col,lane,true,1.0);double raw;double ratio=measure(r,lane,raw);storeIsland(r,lane,false);if(lane==0){m.Store(AT(RATIO,r),asuint(float(ratio)));if(!isfinite(float(ratio))){fail(16);return;}if(ratio>1){if((flags&G4_GUARDED_FLAG)!=0){uint64_t tokens=(128ull+uint64_t(m.Load(AT(SIZE,r)))+4ull*m.Load(AT(CONTACT_COUNT,r)))*uint64_t(iterations);uint budget=m.Load(G4_BUDGET_BYTE),previous;if(tokens>budget){fail(G4_ADMISSION_ERROR);return;}m.InterlockedAdd(G4_SPENT_BYTE,uint(tokens),previous);if(previous>budget-uint(tokens)){fail(G4_ADMISSION_ERROR);return;}}uint at;m.InterlockedAdd(20,1,at);if(at>=G3_ROOT_BOUND(n,flags)){fail(64);return;}m.Store(AT(QUEUE,at),r);m.InterlockedMax(72,at+1);}}}
[numthreads(128,1,1)]void ph_solve(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){
 uint q=islandIndex(g),lane=l.x;if(q>=m.Load(20))return;
 if(lane==0)blocked=stopped()?1:0;GroupMemoryBarrierWithGroupSync();if(blocked)return;
 uint r=m.Load(AT(QUEUE,q));
 if(lane==0){localMode=g5StorageMode(m.Load(AT(SIZE,r)));uint prior;m.InterlockedOr(AT(ROOT_DIRTY,r),2,prior);if(prior&2)fail(64);m.InterlockedAdd(36,1);}
 GroupMemoryBarrierWithGroupSync();loadIsland(r,lane,false);
 double ratio=0,raw=0,relaxation=1.0;
#if G5_PROFILE_COUNTS
 uint g5Rebuilds=0,g5Restarts=0;
#endif
#if G5_RELAXATION_POLICY == 1
 relaxation=m.Load(AT(SIZE,r))>=64?1.995:1.0;
#endif
#if G5_RELAXATION_POLICY >= 2
 // All lanes consume the same reduced scalar and make identical decisions.
 // Absolute residual avoids interpreting a shrinking velocity-scaled KKT
 // tolerance as stagnation. The normalized KKT test itself is unchanged.
 double previousWindow=0,windowMinimum=1.0e300;
 uint settlingWindows=0;
#if G5_RELAXATION_POLICY >= 3
 bool restarted=false;
#endif
#if G5_RELAXATION_POLICY == 4
 double lastContraction=1.0;
#endif
#endif
 uint it=0,colors=m.Load(AT(COLORS,r)),count=m.Load(AT(CONTACT_COUNT,r)),limit=min(iterations,max_work/max(1u,count));
#if G5_SYNC_PROBE
 for(it=0;it<limit;it++){g5SyncColors(r,lane,colors);DeviceMemoryBarrierWithGroupSync();g5SyncReduction(lane);if(((it+1)&7)==0||it+1==limit){DeviceMemoryBarrierWithGroupSync();g5SyncColors(r,lane,colors);DeviceMemoryBarrierWithGroupSync();g5SyncReduction(lane);}}
 storeIsland(r,lane,true);
 if(lane==0){m.Store(AT(ITERATIONS,r),it);m.InterlockedAdd(40,it);m.InterlockedMax(44,it);fail(2);}
 return;
#endif
 for(;it<limit;it++){
  for(uint col=0;col<colors;col++)applyColor(r,col,lane,false,relaxation);
  DeviceMemoryBarrierWithGroupSync();ratio=measure(r,lane,raw);
  if(ratio<=1||((it+1)&7)==0||it+1==limit){
#if G5_PROFILE_COUNTS
   g5Rebuilds++;
#endif
   loadIsland(r,lane,true);
   for(uint col=0;col<colors;col++)applyColor(r,col,lane,true,1.0);
   DeviceMemoryBarrierWithGroupSync();ratio=measure(r,lane,raw);
  }
  if(ratio<=1){it++;break;}
#if G5_RELAXATION_POLICY >= 2
  windowMinimum=min(windowMinimum,raw);
  if(((it+1)&63)==0){
   double before=relaxation,contraction=previousWindow>0?windowMinimum/previousWindow:0;
#if G5_RELAXATION_POLICY == 4
   if(previousWindow>0)lastContraction=contraction;
#endif
   uint event=0;
#if G5_RELAXATION_POLICY >= 3
   if(!restarted){
#endif
   if(previousWindow>0){
    if(settlingWindows>0){settlingWindows--;event=4;}
    else if(contraction>1.25){
     // Sustained worsening: halve the excess relaxation, eventually revert
     // to PGS. Window minima and hysteresis reject isolated rounded spikes.
     relaxation=relaxation<1.05?1.0:1.0+.5*(relaxation-1.0);
     settlingWindows=2;
     event=2;
    }else if(contraction>.8){
     // Slow contraction only: estimate a bounded starting SOR factor from
     // PGS contraction. Later poor windows increase it conservatively.
     if(relaxation==1.0){
      float rho=pow(clamp(float(contraction),0.0,1.0),1.0/64.0);
      relaxation=min(1.995,2.0/(1.0+sqrt(max(0.0,1.0-double(rho)))));
     }else relaxation=min(1.995,.5*(relaxation+1.995));
     settlingWindows=2;
     event=1;
    }
   }
#if G5_RELAXATION_POLICY >= 3
   }
#endif
   if(lane==0)g5Trace(r,q,it/64,it+1,raw,windowMinimum,previousWindow,contraction,before,relaxation,event,ratio);
   previousWindow=windowMinimum;windowMinimum=1.0e300;
  }
#if G5_RELAXATION_POLICY >= 3
  // One bounded fallback; no fixture, topology, size or residual tolerance
  // special case. Reserve 7/8 of this island's existing work/iteration budget
  // for a clean fixed-SOR attempt, rather than extending the limit. Clear only
  // this island's impulses, then reconstruct the immutable free velocities.
  bool restartDue=!restarted&&limit>=8&&it+1==limit/8;
#if G5_RELAXATION_POLICY == 4
  // Reuse the controller's poor-contraction threshold. A full window that
  // reduced the absolute projected residual by >20% keeps its useful state.
  // Decide only at the original budget checkpoint, preserving the same reserve
  // for a clean restart; a skipped restart never silently extends the limit.
  restartDue=restartDue&&lastContraction>=.8;
#endif
  if(restartDue){
#if G5_PROFILE_COUNTS
   g5Restarts++;
#endif
   uint start=uint(get64(AT(CONTACT_START,r))),end=start+count;
   for(uint ci=start+lane;ci<end;ci+=128){uint o=CT(CONTACT,c.Load(CT(ROOT_CONTACTS,ci)));writeLambda(o,false,0.0);writeLambda(o,true,0.0);}
   DeviceMemoryBarrierWithGroupSync();loadIsland(r,lane,true);
   if(lane==0)g5Trace(r,q,65,it+1,raw,raw,previousWindow,0,relaxation,1.995,8,ratio);
   relaxation=1.995;restarted=true;
  }
#endif
#endif
 }
 storeIsland(r,lane,true);
 g5ProfileEnd(r,lane,it,
#if G5_PROFILE_COUNTS
 g5Rebuilds,g5Restarts
#else
 0,0
#endif
 );
 if(lane==0){g5Trace(r,q,64,it,raw,raw,0,0,relaxation,relaxation,16,ratio);m.Store(AT(RATIO,r),asuint(float(ratio)));m.InterlockedAdd(AT(ITERATIONS,r),it);uint previous;m.InterlockedAdd(40,it,previous);if(previous>0xffffffffu-it)fail(64);m.InterlockedMax(44,it);if(fixture>=9u)m.InterlockedAdd(G4_ITERATION_HISTOGRAM_BYTE+4*(it==0?0:min(7u,1+firstbithigh(it))),1);if(!isfinite(float(ratio))||ratio>1)fail(2);}
}
