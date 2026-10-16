// G2 spatial contract v1. 2D linear swept disks, dt=1, cell edge=4.
#include "layout.hlsl"
#include "spatial-layout.h"
#include "physics-layout.h"
#include "execution-layout.h"
#include "physics-math.hlsl"
RWByteAddressBuffer data:register(u0);
RWByteAddressBuffer maps:register(u1);
RWByteAddressBuffer active:register(u2);
RWByteAddressBuffer keys:register(u3);
RWByteAddressBuffer A:register(u4);
RWByteAddressBuffer B:register(u5);
RWByteAddressBuffer m:register(u6);
ByteAddressBuffer unused:register(t0);
// constants: n,capacity,design,stride,fixture,shift,T,groups,
// scanCount,input,output,parent,pairCapacity,outputByte,scanBase,maxVisits.
#define design layout
#define fixture verify
#define shift (stage&G2_DISPATCH_STAGE_MASK)
#define tableSize inputLayout
#define groups inputCapacity
#define pairCapacity commandCount
#define outputByte epoch
#define scanBase unused0
#define maxVisits unused1
uint groupIndex(uint3 g){return g.x+(stage>>G2_DISPATCH_WIDTH_SHIFT)*g.y;}
uint logicalIndex(uint3 g,uint l,uint width){uint64_t wide=(uint64_t(g.x)+uint64_t(width)*g.y)*256+l;return wide>0xffffffffu?0xffffffffu:uint(wide);}
uint idx(uint3 g,uint l){return logicalIndex(g,l,stage>>G2_DISPATCH_WIDTH_SHIFT);}
float f(uint i,uint field){return asfloat(data.Load(4*(field*capacity+i)));}
uint id(uint i){return data.Load(4*(15*capacity+i));}
void fail(uint bit){m.InterlockedOr(0,bit);m.InterlockedOr(G2_STICKY_ERROR_BYTE,bit);m.InterlockedAnd(16,0);}
uint64_t get64(uint p){uint2 v=m.Load2(p);return uint64_t(v.x)|(uint64_t(v.y)<<32);}
void put64(uint p,uint64_t v){m.Store2(p,uint2(uint(v),uint(v>>32)));}
uint countByte(uint i){return G2_COUNT(i);}
uint offsetByte(uint i){return G2_OFFSET(capacity,i);}
uint contactCountByte(uint i){return G2_CONTACT_COUNT(capacity,i);}
uint contactOffsetByte(uint i){return G2_CONTACT_OFFSET(capacity,i);}
uint contactBase(){return outputByte+G2_PAIR_BYTES*pairCapacity;}
uint coverageByte(uint pass,uint i){return G2_COVERAGE(capacity,pass,i);}
void touch(uint pass,uint i){m.InterlockedAdd(coverageByte(pass,i),1);}
bool valid(double x){return x==x&&x<=3.402823466e38&&x>=-3.402823466e38;}
bool cell(double x,out int v){double edge=(shift&G4_FINE_CELL_FLAG)!=0?1.0/double(G4_FINE_CELL_RECIPROCAL):double(G2_CELL_EDGE);double d=x/edge;v=0;if(d < -2147483647.0||d >=2147483647.0)return false;v=int(d);if(double(v)>d)v--;return true;}
uint hash(int2 k){uint x=asuint(k.x)*0x9e3779b9u,y=asuint(k.y)*0x85ebca6bu;x^=x>>16;y^=y>>13;return (x^y)&(tableSize-1);}
int2 key(uint i){return asint(keys.Load2(G2_KEY_BYTES*i));}
bool eq(int2 a,int2 b){return all(a==b);}
bool less(int2 a,int2 b){return a.y<b.y||(a.y==b.y&&a.x<b.x);}
uint findHash(int2 k,bool insert,uint i){uint h=hash(k);for(uint p=0;p<min(tableSize,maxVisits);p++){uint rep;if(insert)A.InterlockedCompareExchange(G2_HASH_SLOT_BYTES*h,0xffffffffu,i,rep);else rep=A.Load(G2_HASH_SLOT_BYTES*h);if(rep==0xffffffffu){if(!insert)return 0xffffffffu;return h;}if(eq(key(rep),k))return h;h=(h+1)&(tableSize-1);}fail(16);return 0xffffffffu;}
uint lowerKey(int2 k){uint lo=0,hi=n;while(lo<hi){uint mid=lo+(hi-lo)/2;if(less(key(A.Load(4*mid)),k))lo=mid+1;else hi=mid;}return lo;}
double reachSpeed(double vx,double vy){return (shift&8192)!=0?dsqrt(vx*vx+vy*vy):abs(vx)+abs(vy);}
bool physicsStop(){return (shift&2048)!=0&&(active.Load(G3_ERROR_BYTE)!=0||active.Load(G3_DONE_BYTE)!=0);}
bool activeObject(uint i){return (shift&2048)!=0?data.Load(4*(14*capacity+i))!=0:active.Load(4*i)!=0;}
bool pair(uint i,uint j,out bool contact){
 if((shift&2048)!=0){
  precise float dx=f(i,0)-f(j,0),dy=f(i,1)-f(j,1),d2=dx*dx+dy*dy,d=sqrt(d2),gap=d-f(i,8)-f(j,8),nx=d2==0?-1:dx/d,ny=d2==0?0:dy/d;
  precise float vn=(f(i,2)-f(j,2))*nx+(f(i,3)-f(j,3))*ny,target=-gap/asfloat(fixture);
  contact=gap<=0||vn<target;
  if((shift&G4_PRECISE_CONTACT_POLICY_FLAG)!=0){double2 p=double2(f(i,0),f(i,1))-double2(f(j,0),f(j,1));double distance=dsqrt(p.x*p.x+p.y*p.y),separation=distance-double(f(i,8))-double(f(j,8));double2 normal=distance==0?double2(-1,0):p/distance;double vn64=(double(f(i,2))-double(f(j,2)))*normal.x+(double(f(i,3))-double(f(j,3)))*normal.y;contact=separation<=0||vn64 < -separation/double(asfloat(fixture));}
  double2 vi=double2(f(i,2),f(i,3)),vj=double2(f(j,2),f(j,3));double reach=(double(f(i,8))+double(f(j,8))+double(asfloat(fixture))*(reachSpeed(vi.x,vi.y)+reachSpeed(vj.x,vj.y)))*(1.0+64.0*0.00000011920928955078125);
  double2 delta=double2(f(i,0),f(i,1))-double2(f(j,0),f(j,1));return (delta.x*delta.x+delta.y*delta.y)<=reach*reach;
 }

 double2 p=double2(f(i,0),f(i,1)),q=double2(f(j,0),f(j,1));
 double2 v=double2(f(i,2),f(i,3)),w=double2(f(j,2),f(j,3));double r=double(f(i,8))+double(f(j,8));
 if((shift&256)!=0&&all(v==0)&&all(w==0)){double2 d=p-q;contact=d.x*d.x+d.y*d.y<=r*r;return abs(d.x)<=r&&abs(d.y)<=r;}
 double2 amin=min(p,p+v)-double(f(i,8)),amax=max(p,p+v)+double(f(i,8));
 double2 bmin=min(q,q+w)-double(f(j,8)),bmax=max(q,q+w)+double(f(j,8));
 double2 delta=p-q,dv=v-w;double vv=dv.x*dv.x+dv.y*dv.y,t=vv>0?min(1.0,max(0.0,-(delta.x*dv.x+delta.y*dv.y)/vv)):0.0;double2 d=delta+t*dv;contact=d.x*d.x+d.y*d.y<=r*r;
 return all(amin<=bmax)&&all(bmin<=amax);
}
[numthreads(256,1,1)]void sp_fixture(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){if(physicsStop())return;
 uint i=idx(g,l.x);if(i>=n)return;uint s=id(i),size=fixture==0?1:fixture==1?2:fixture==2?8:((s/1024)%16==0?16:2);
 uint group=fixture==3?(s/1024)*512+(s%1024)/size:s/size,local=s%size;float x=float(group%16384)*16-131072,y=float(group/16384)*16-8192;
 if(fixture==0){x+=0.5;}else x+=float(local)*0.125;
 float vx=0,vy=0,r=0.5;
 if(fixture==4){x=float(s%32)*0.75-12;y=float(s/32)*0.75-12;vx=float(int(s%7)-3)*2;vy=float(int(s%5)-2)*2;r=0.25;}
 if(fixture==5){x=s%2==0?-8:8;y=float(s/2)*16;vx=s%2==0?16:-16;r=0.25;}
 if(fixture==6){uint row=s/2;x=(row%3==0?-4.5:(row%3==1?3.5:-0.5))+float(s%2);y=float(row)*16;}
 if(fixture==7){x=s%2==0?-8589934080.0:8589934080.0;y=float(s/2)*16;r=512;}
 if(fixture==8){x=0;y=0;}
 if(fixture==9){x=asfloat(0x7fc00000);}
 if(fixture==10){x=0;y=float(s)*16;vx=1e9;}
 if(fixture==11){x=s%2==0?-8589934080.0:8589934080.0;y=float(s/2)*16;r=0.5;}
 if(fixture==12){x=1e20;}
 if(fixture==13){r=-1;}
 if(fixture==14){vx=asfloat(0x7f800000);}
 if(fixture==15){x=-4;y=float(s/2)*16;r=0;}
 if(fixture>=16){uint distribution=fixture%16,level=fixture/16-1;size=distribution==2?8:(distribution==3&&((s/1024)%16==0)?16:2);group=distribution==3?(s/1024)*512+(s%1024)/size:s/size;local=s%size;bool hot=level==3||(level==1&&group%100==0)||(level==2&&group%10==0);float spacing=distribution==0?128:32;x=float(group%16384)*spacing-131072+float(local)*(hot?0.125:1.5);y=float(group/16384)*spacing-8192;}
 data.Store(4*i,asuint(x));data.Store(4*(capacity+i),asuint(y));data.Store(4*(2*capacity+i),asuint(vx));data.Store(4*(3*capacity+i),asuint(vy));data.Store(4*(8*capacity+i),asuint(r));
}
[numthreads(256,1,1)]void sp_clear(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){if(physicsStop())return;uint i=idx(g,l.x);if(i<64&&4*i!=G2_STICKY_ERROR_BYTE)m.Store(4*i,i==0?m.Load(G2_STICKY_ERROR_BYTE):0);if(i<capacity){put64(countByte(i),0);put64(offsetByte(i),0);put64(contactCountByte(i),0);put64(contactOffsetByte(i),0);for(uint p=0;p<4;p++)m.Store(coverageByte(p,i),0);m.Store(G2_PARENT(capacity,i),i);m.Store(G2_SIZE(capacity,i),0);m.Store(G2_DEGREE(capacity,i),0);}if(design==1&&i<tableSize)A.Store4(G2_HASH_SLOT_BYTES*i,uint4(0xffffffffu,0,0,0));}
uint2 keyOne(uint i){touch(0,i);if(i==0){m.Store(32,0xbaadc0deu);m.Store(48,G2_TAG);m.Store3(88,uint3(G2_CONTACT_COUNT(capacity,n-1),G2_CONTACT_OFFSET(capacity,n-1),contactBase()));m.Store4(52,uint4(G2_COUNT(n-1),G2_OFFSET(capacity,n-1),G2_COVERAGE(capacity,3,n-1),G2_SCAN_BASE(capacity)));}double x=f(i,0),y=f(i,1),vx=f(i,2),vy=f(i,3),r=f(i,8);int cx=0,cy=0;
 bool good=valid(x)&&valid(y)&&valid(vx)&&valid(vy)&&valid(r)&&r>=0&&cell(x,cx)&&cell(y,cy);if(!good){fail(1);}
 keys.Store4(G2_KEY_BYTES*i,uint4(asuint(cx),asuint(cy),0,0));if(design==0)A.Store(4*i,i);
 double radial=(r+double(asfloat(fixture))*reachSpeed(vx,vy))*(1.0+64.0*0.00000011920928955078125);float ex=(shift&2048)!=0?float(radial):float(r+abs(vx)),ey=(shift&2048)!=0?float(radial):float(r+abs(vy));if(!good||!isfinite(ex)||!isfinite(ey)){fail(1);return uint2(0,0);}return uint2(asuint(ex)+1,asuint(ey)+1);
}
groupshared uint2 maxExtent[256];
[numthreads(256,1,1)]void sp_keys(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){if(physicsStop())return;uint i=idx(g,l.x),lane=l.x;if(i==0)m.Store(G4_SPATIAL_CELL_POLICY_BYTE,(shift&G4_FINE_CELL_FLAG)!=0?1u:0u);uint2 extent=0;if(i<n)extent=keyOne(i);
 if((shift&256)==0){if(i<n){m.InterlockedMax(40,extent.x);m.InterlockedMax(44,extent.y);}return;}
 maxExtent[lane]=extent;GroupMemoryBarrierWithGroupSync();for(uint step=128;step>0;step/=2){if(lane<step)maxExtent[lane]=max(maxExtent[lane],maxExtent[lane+step]);GroupMemoryBarrierWithGroupSync();}if(lane==0&&(groupIndex(g))<groups){m.InterlockedMax(40,maxExtent[0].x);m.InterlockedMax(44,maxExtent[0].y);}
}
[numthreads(256,1,1)]void sp_hash(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){if(physicsStop())return;uint i=idx(g,l.x);if(i>=n||m.Load(0))return;uint h=findHash(key(i),true,i);if(h!=0xffffffffu){keys.Store(G2_KEY_BYTES*i+8,h);A.InterlockedAdd(G2_HASH_SLOT_BYTES*h+4,1);}}
[numthreads(256,1,1)]void sp_hash_counts(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){if(physicsStop())return;uint i=idx(g,l.x);if(i<tableSize)put64(scanInput+8*i,A.Load(G2_HASH_SLOT_BYTES*i+4));}
groupshared uint64_t sums[256];
[numthreads(256,1,1)]void sp_scan(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){if(physicsStop())return;uint i=idx(g,l.x),lane=l.x,group=groupIndex(g);uint64_t value=i<scanCount?get64(scanInput+8*i):0;sums[lane]=value;GroupMemoryBarrierWithGroupSync();for(uint step=1;step<256;step*=2){uint64_t v=lane>=step?sums[lane-step]:0;GroupMemoryBarrierWithGroupSync();sums[lane]+=v;GroupMemoryBarrierWithGroupSync();}if(i<scanCount)put64(scanOutput+8*i,sums[lane]-value);if(lane==255&&group<(scanCount+255)/256){if(scanParent!=0xffffffffu)put64(scanParent+8*group,sums[lane]);else put64((shift&G2_CONTACT_SCAN_FLAG)!=0?G2_CONTACT_TOTAL_BYTE:8,sums[lane]);}}
[numthreads(256,1,1)]void sp_add(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){if(physicsStop())return;uint i=idx(g,l.x);if(i<scanCount)put64(scanOutput+8*i,get64(scanOutput+8*i)+get64(scanParent+8*(i/256)));}
[numthreads(256,1,1)]void sp_hash_offsets(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){if(physicsStop())return;uint i=idx(g,l.x);if(i<tableSize)A.Store(G2_HASH_SLOT_BYTES*i+8,uint(get64(scanOutput+8*i)));}
[numthreads(256,1,1)]void sp_hash_scatter(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){if(physicsStop())return;uint i=idx(g,l.x);if(i>=n||m.Load(0))return;uint h=keys.Load(G2_KEY_BYTES*i+8),rank;A.InterlockedAdd(G2_HASH_SLOT_BYTES*h+12,1,rank);uint dst=A.Load(G2_HASH_SLOT_BYTES*h+8)+rank;if(dst>=n){fail(32);return;}B.Store(4*dst,i);touch(1,i);}
groupshared uint order[256];groupshared uint sortedId[256];
uint digit(uint i){uint2 k=asuint(key(i))^0x80000000u;uint bit=shift&63;return (bit<32?k.x>>bit:k.y>>(bit-32))&15;}
[numthreads(256,1,1)]void sp_radix_local(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){if(physicsStop())return;uint i=idx(g,l.x),lane=l.x,group=groupIndex(g);uint v=i<n?A.Load(4*i):0xffffffffu;uint d=i<n?digit(v):16;order[lane]=d*256+lane;sortedId[lane]=v;GroupMemoryBarrierWithGroupSync();
 for(uint width=2;width<=256;width*=2)for(uint step=width/2;step>0;step/=2){uint partner=lane^step;uint a=order[lane],b=order[partner],iv=sortedId[partner];bool ascending=(lane&width)==0;bool swap=(partner>lane)==ascending?a>b:a<b;GroupMemoryBarrierWithGroupSync();if(swap){order[lane]=b;sortedId[lane]=iv;}GroupMemoryBarrierWithGroupSync();}
 if(i<n)B.Store(4*i,sortedId[lane]);if(lane<16&&group<groups){uint lo=0,hi=256;while(lo<hi){uint mid=(lo+hi)/2;if(order[mid]/256<lane)lo=mid+1;else hi=mid;}uint start=lo;hi=256;while(lo<hi){uint mid=(lo+hi)/2;if(order[mid]/256<=lane)lo=mid+1;else hi=mid;}put64(scanInput+8*(lane*groups+group),lo-start);}}
[numthreads(256,1,1)]void sp_radix_scatter(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){if(physicsStop())return;uint i=idx(g,l.x),lane=l.x,group=groupIndex(g);uint v=i<n?B.Load(4*i):0xffffffffu;uint d=i<n?digit(v):16;order[lane]=d;GroupMemoryBarrierWithGroupSync();if(i>=n)return;uint lo=0,hi=lane;while(lo<hi){uint mid=(lo+hi)/2;if(order[mid]<d)lo=mid+1;else hi=mid;}uint dst=uint(get64(scanOutput+8*(d*groups+group)))+lane-lo;if(dst>=n){fail(32);return;}A.Store(4*dst,v);}
[numthreads(256,1,1)]void sp_ranges(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){if(physicsStop())return;uint i=idx(g,l.x);if(i>=n||m.Load(0))return;touch(1,A.Load(4*i));int2 k=key(A.Load(4*i));if(i>0&&eq(key(A.Load(4*(i-1))),k))return;uint lo=i+1,hi=n;while(lo<hi){uint mid=lo+(hi-lo)/2;if(eq(key(A.Load(4*mid)),k))lo=mid+1;else hi=mid;}keys.Store2(G2_KEY_BYTES*A.Load(4*i)+8,uint2(i,lo-i));}
void search(uint i,bool emit){if(!activeObject(i))return;double2 p=double2(f(i,0),f(i,1)),v=double2(f(i,2),f(i,3));double r=f(i,8);double2 ext=double2(asfloat(m.Load(40)),asfloat(m.Load(44)));int2 low,high;
 double2 lo=min(p,p+v)-r-ext,hi=max(p,p+v)+r+ext;if((shift&2048)!=0){double radial=(r+double(asfloat(fixture))*reachSpeed(v.x,v.y))*(1.0+64.0*0.00000011920928955078125);lo=p-radial-ext;hi=p+radial+ext;}
 if(!cell(lo.x,low.x)||!cell(lo.y,low.y)||!cell(hi.x,high.x)||!cell(hi.y,high.y)){fail(2);return;}
 uint64_t dx=uint64_t(int64_t(high.x)-int64_t(low.x)+1),dy=uint64_t(int64_t(high.y)-int64_t(low.y)+1);if(dx>maxVisits||dy>maxVisits||dx*dy>maxVisits){fail(4);return;}
 uint64_t count=0,base=emit?get64(offsetByte(i)):0,contactOffset=emit?get64(contactOffsetByte(i)):0;uint visits=0,truth=0;
 for(int64_t y=low.y;y<=int64_t(high.y);y++)for(int64_t x=low.x;x<=int64_t(high.x);x++){int2 k=int2(x,y);uint start=0,len=0;
  if(design==1){uint h=findHash(k,false,0);if(h!=0xffffffffu){start=A.Load(G2_HASH_SLOT_BYTES*h+8);len=A.Load(G2_HASH_SLOT_BYTES*h+4);}}else{uint at=lowerKey(k);if(at<n){uint rep=A.Load(4*at);if(eq(key(rep),k)){uint2 rge=keys.Load2(G2_KEY_BYTES*rep+8);start=rge.x;len=rge.y;}}}
  if(len>maxVisits-visits){fail(8);return;}visits+=len;
  for(uint t=0;t<len;t++){uint j=design==1?B.Load(4*(start+t)):A.Load(4*(start+t));if(j==i)continue;uint si=id(i),sj=id(j);if(activeObject(j)&&si>sj)continue;bool contact;if(!pair(i,j,contact))continue;
   if(emit){uint64_t dst=base+count;if(dst>=pairCapacity){fail(64);return;}uint a=min(si,sj),b=max(si,sj);uint at=outputByte+G2_PAIR_BYTES*uint(dst);m.Store4(at,uint4(a,maps.Load(8*a+4),b,maps.Load(8*b+4)));m.Store(at+16,uint(contact));if(contact){uint64_t ci=contactOffset+truth;if(ci>=pairCapacity){fail(64);return;}m.Store(contactBase()+G2_CONTACT_INDEX_BYTES*uint(ci),uint(dst));}}truth+=uint(contact);
   count++;
  }
 }
 if(emit){if(count!=get64(countByte(i))||uint64_t(truth)!=get64(contactCountByte(i))){fail(128);return;}}else{put64(countByte(i),count);put64(contactCountByte(i),truth);}
}
[numthreads(256,1,1)]void sp_count(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){if(physicsStop())return;uint i=idx(g,l.x);if(i>=n||m.Load(0))return;touch(2,i);search(i,false);}
[numthreads(256,1,1)]void sp_admit(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){if(physicsStop())return;if(idx(g,l.x))return;uint64_t total=get64(8);uint64_t contacts=get64(G2_CONTACT_TOTAL_BYTE);if(total>pairCapacity||contacts>pairCapacity)fail(256);if(contacts>total)fail(8192);m.Store(16,m.Load(0)==0?1:0);}
[numthreads(256,1,1)]void sp_emit(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){if(physicsStop())return;uint i=idx(g,l.x);if(i>=n||m.Load(0))return;touch(3,i);search(i,true);}
[numthreads(256,1,1)]void sp_guards(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){if(physicsStop())return;uint i=idx(g,l.x);if(i<64){keys.Store(scanCount+4*i,0xbaadc0deu);A.Store(scanInput+4*i,0xbaadc0deu);B.Store(scanOutput+4*i,0xbaadc0deu);m.Store(scanParent+4*i,0xbaadc0deu);}if(i==0)m.Store(G2_STICKY_ERROR_BYTE,0);}
[numthreads(256,1,1)]void sp_synthetic_counts(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){if(physicsStop())return;uint i=idx(g,l.x);if(i<n){put64(countByte(i),uint64_t(0xffffffffu)+i);put64(contactCountByte(i),uint64_t(0xfffffffeu)+i);}}
// Contact-graph telemetry required by the frozen G2 ledger. No solver.
uint rootOf(uint a){for(uint hop=0;hop<maxVisits;hop++){if(a>=capacity){fail(512);return 0;}uint b=m.Load(G2_PARENT(capacity,a));if(b==a)return a;a=b;}fail(512);return a;}
[numthreads(256,1,1)]void sp_union(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){if(physicsStop())return;uint i=idx(g,l.x);if(m.Load(0)||uint64_t(i)>=get64(G2_CONTACT_TOTAL_BYTE))return;uint pi=m.Load(contactBase()+G2_CONTACT_INDEX_BYTES*i);if(uint64_t(pi)>=get64(8)){fail(64);return;}uint at=outputByte+G2_PAIR_BYTES*pi;if(m.Load(at+16)==0){fail(8192);return;}uint a=m.Load(at),b=m.Load(at+8);m.InterlockedOr(G2_DEGREE(capacity,a),1);m.InterlockedOr(G2_DEGREE(capacity,b),1);
 for(uint hop=0;hop<maxVisits;hop++){a=rootOf(a);b=rootOf(b);if(a==b)return;uint hi=max(a,b),lo=min(a,b),old;m.InterlockedMin(G2_PARENT(capacity,hi),lo,old);if(old==hi)return;a=old;b=lo;}fail(512);
}
[numthreads(256,1,1)]void sp_compress(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){if(physicsStop())return;uint i=idx(g,l.x);if(i>=capacity||m.Load(0))return;if(m.Load(G2_DEGREE(capacity,i))==0)return;uint root=rootOf(i);m.Store(G2_PARENT(capacity,i),root);m.InterlockedAdd(G2_SIZE(capacity,root),1);m.InterlockedAdd(72,1);}
[numthreads(256,1,1)]void sp_graph_stats(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){if(physicsStop())return;uint i=idx(g,l.x);if(m.Load(0)){if(i==0)m.Store(16,0);return;}if(i>=capacity)return;uint size=m.Load(G2_SIZE(capacity,i));if(size){m.InterlockedAdd(28,1);m.InterlockedMax(36,size);}}
[numthreads(256,1,1)]void sp_validate(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){if(physicsStop())return;uint i=idx(g,l.x);if(m.Load(0))return;if(i<n){for(uint pass=0;pass<4;pass++)if(m.Load(coverageByte(pass,i))!=1)fail(1024);if((shift&512)!=0&&unused.Load(4*(capacity+i))!=1)fail(1024);}if(i<64){uint a=design==1?G2_HASH_SLOT_BYTES*tableSize:4*capacity;if(keys.Load(G2_KEY_BYTES*capacity+4*i)!=0xbaadc0deu||A.Load(a+4*i)!=0xbaadc0deu||B.Load(4*capacity+4*i)!=0xbaadc0deu||m.Load(contactBase()+G2_CONTACT_INDEX_BYTES*pairCapacity+4*i)!=0xbaadc0deu)fail(2048);}}
[numthreads(256,1,1)]void sp_poison(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){if(physicsStop())return;if(idx(g,l.x)==0){if(shift==1)keys.Store(G2_KEY_BYTES*capacity,0);else fail(4096);}}
[numthreads(256,1,1)]void sp_mapping(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){if(physicsStop())return;uint i=idx(g,l.x);if(i>=6)return;uint x=0,y=0,width=1,lane=0;if(i==0){x=65534;width=65535;lane=255;}if(i==1){x=65534;y=256;width=65535;lane=255;}if(i==2){x=65280;y=256;width=65281;lane=255;}if(i==3){x=32767;y=511;width=32768;lane=254;}if(i==4){y=512;width=32768;}uint64_t wide=(uint64_t(x)+uint64_t(width)*y)*256+lane;m.Store4(80+16*i,uint4(logicalIndex(uint3(x,y,0),lane,width),uint(wide),uint(wide>>32),0x1deac0deu));}

// G4 occupancy instrumentation reads the chosen, already-built G2 cell data.
[numthreads(256,1,1)]void sp_g4_occupancy(uint3 g:SV_GroupID,uint3 l:SV_GroupThreadID){uint i=idx(g,l.x);if((shift&2048u)==0||active.Load(G3_ERROR_BYTE)!=0)return;uint count=0;if(design==1u){if(i>=tableSize)return;count=A.Load(G2_HASH_SLOT_BYTES*i+4);}else{if(i>=n)return;uint representative=A.Load(4*i);if(i>0&&eq(key(A.Load(4*(i-1))),key(representative)))return;count=keys.Load(G2_KEY_BYTES*representative+12);}if(count){active.InterlockedAdd(G4_OCCUPANCY_HISTOGRAM_BYTE+4*min(7u,firstbithigh(count)),1);active.InterlockedMax(G4_OCCUPANCY_MAX_BYTE,count);}}
