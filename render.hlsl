// Actual GPU SoA disk positions rendered as lit sphere impostors (2D physics).
ByteAddressBuffer bodies:register(t0);
ByteAddressBuffer state:register(t1);
ByteAddressBuffer entityMaps:register(t2);
RWByteAddressBuffer diagnostics:register(u0);
#include "viewer-cbuffer.hlsl"
#include "pool-layout.h"
#include "physics-layout.h"
// Shared generated metadata contract; no duplicate offsets.
#include "execution-layout.h"
uint colorHash(uint v){v^=v>>16;v*=0x7feb352du;v^=v>>15;v*=0x846ca68bu;return v^(v>>16);}
float scalar(uint i,uint field){return asfloat(bodies.Load(4*(field*entityCapacity+i)));}
struct BallVertex {float4 position:SV_Position;float2 circle:TEXCOORD0;nointerpolation uint stable:TEXCOORD1;};
BallVertex ball_vs(uint vertex:SV_VertexID,uint instance:SV_InstanceID){
 BallVertex o;float2 corners[6]={float2(-1,-1),float2(-1,1),float2(1,1),float2(-1,-1),float2(1,1),float2(1,-1)};
 uint i=instance*visualStride;o.stable=i<objectCount?bodies.Load(4*(15*entityCapacity+i)):0;
 float2 p=i<objectCount?float2(scalar(i,0),scalar(i,1)):float2(1e20,1e20);
 float radius=i<objectCount?scalar(i,8):0;
 float2 extent=max(float2(radius/halfWidth,radius/halfHeight),float2(2*minPixelRadius/max(1u,pixelWidth),2*minPixelRadius/max(1u,pixelHeight)));
 o.circle=corners[vertex]*((renderFlags&2u)!=0?1.25:1);o.position=float4((p-float2(cameraX,cameraY))/float2(halfWidth,halfHeight)+o.circle*extent,0,1);return o;
}
float3 ballColor(uint id){
 float3 palette[8]={float3(.94,.73,.08),float3(.12,.37,.85),float3(.85,.13,.12),float3(.42,.18,.65),float3(.95,.37,.07),float3(.10,.55,.30),float3(.52,.12,.19),float3(.06,.065,.075)};
 return id%16u==0u?float3(.93,.94,.92):palette[(id-1u)%8u];
}
float segmentDigit(uint number,float2 p){uint patterns[10]={63u,6u,91u,79u,102u,109u,125u,7u,127u,111u};uint pattern=patterns[number%10u];float2 centers[7]={float2(0,.8),float2(.45,.4),float2(.45,-.4),float2(0,-.8),float2(-.45,-.4),float2(-.45,.4),float2(0,0)};float value=0;for(uint k=0;k<7;k++)if(pattern&(1u<<k)){float2 q=abs(p-centers[k]);value=max(value,(k==0||k==3||k==6)?float(q.x<.42&&q.y<.12):float(q.x<.12&&q.y<.3));}return value;}
float4 ball_ps(BallVertex i):SV_Target{
 float d=dot(i.circle,i.circle);if(d>1){if((renderFlags&2u)!=0u){if(i.stable==selectedID&&d<1.20)return float4(.25,.96,.8,.9);float shadow=max(0.0,1.0-dot(i.circle-float2(.08,-.12),i.circle-float2(.08,-.12))/1.55);return float4(.005,.009,.015,shadow*.45);}discard;}float3 normal=float3(i.circle,sqrt(max(0,1-d)));float3 light=normalize(float3(-.45,.65,1));
 float3 base=ballColor(i.stable);if(i.stable%16u>=9u&&abs(i.circle.y)>.38)base=float3(.91,.92,.90);
 float diffuse=.18+.82*max(0,dot(normal,light));float specular=pow(max(0,dot(normal,normalize(light+float3(0,0,1)))),72);
 if((renderFlags&1u)!=0u&&i.stable%16u!=0u){float disk=dot(i.circle-float2(0,.03),i.circle-float2(0,.03));if(disk<.085)base=float3(.92,.93,.91);if(disk<.013)base=float3(.08,.085,.09);}
 if((renderFlags&8u)!=0u&&i.stable>0u){float2 p=i.circle;if(dot(p,p)<.18){base=float3(.96,.95,.88);float ink;if(i.stable<10u)ink=segmentDigit(i.stable,p*5);else ink=p.x<0?segmentDigit(1u,(p+float2(.16,0))*float2(6,5)):segmentDigit(i.stable-10u,(p-float2(.16,0))*float2(6,5));if(ink>0)base=float3(.03,.03,.035);}}return float4(base*diffuse+specular*.7,1);
}
struct BackgroundVertex{float4 position:SV_Position;float2 world:TEXCOORD0;};
BackgroundVertex felt_vs(uint id:SV_VertexID){BackgroundVertex v;float2 clip=float2(id==2u?3:-1,id==1u?3:-1);v.position=float4(clip,.9,1);v.world=float2(cameraX,cameraY)+clip*float2(halfWidth,halfHeight);return v;}
float4 felt_ps(BackgroundVertex i):SV_Target{
 if((renderFlags&8u)!=0u){float2 p=i.world;float edge=min(min(p.x,p.y),min(arenaWidth-p.x,arenaHeight-p.y));if(edge<-.07)return float4(.018,.028,.047,1);if(edge<-.025)return float4(.24,.105,.04,1);if(edge<0)return float4(.015,.13,.065,1);float weave=.97+.03*sin(p.x*450)*sin(p.y*450);return float4(float3(.02,.21,.115)*weave,1);}if((renderFlags&2u)!=0u){float2 p=i.world;float edge=min(min(p.x,p.y),min(arenaWidth-p.x,arenaHeight-p.y));if(edge<-.05)return float4(.018,.028,.047,1);if(edge<0)return float4(.10,.42,.45,1);float grid=.5+.5*cos(p.x*6.283)*cos(p.y*6.283);float glow=exp(-max(0.,edge)*3);return float4(float3(.028,.073,.105)+grid*.006+float3(.018,.07,.065)*glow,1);}
 int2 cell=int2(floor(i.world/4));float2 local=i.world-float2(cell)*4;uint table=cell.x>=0&&cell.y>=0?uint(cell.y)*tableColumns+uint(cell.x):0xffffffffu;
 if(cell.x<0||cell.y<0||uint(cell.x)>=tableColumns||table>=tableCount)return float4(.018,.028,.035,1);
 bool felt=local.x>=0&&local.x<=1.5&&local.y>=0&&local.y<=1;
 bool rail=local.x>=-.035&&local.x<=1.535&&local.y>=-.035&&local.y<=1.035;
 if(felt){float weave=.96+.04*sin(local.x*500)*sin(local.y*500);return float4(float3(.022,.20,.135)*weave,1);}
 return rail?float4(.21,.105,.045,1):float4(.018,.028,.035,1);
}
[numthreads(64,1,1)]void render_clear(uint lane:SV_GroupIndex){if(lane<64u)diagnostics.Store(4*lane,((renderFlags&2u)!=0&&lane==10u)?0xffffffffu:0);}
[numthreads(256,1,1)]void render_verify(uint3 group:SV_GroupID,uint lane:SV_GroupIndex){
 uint sample=group.x*256u+lane;if(sample>=instanceCount)return;uint i=sample*visualStride;if(i>=objectCount){diagnostics.InterlockedOr(0,1);return;}
 uint stable=bodies.Load(4*(15*entityCapacity+i));if(stable>=entityCapacity){diagnostics.InterlockedOr(0,2);return;}float2 p=float2(scalar(i,0),scalar(i,1));float radius=scalar(i,8);
 if(entityMaps.Load(8*stable)!=i||entityMaps.Load(8*stable+4)==0u||!all(isfinite(p))||!isfinite(radius)||radius<=0)diagnostics.InterlockedOr(0,2);
 diagnostics.InterlockedAdd(4,1);if(all(abs(p-float2(cameraX,cameraY))<=float2(halfWidth,halfHeight)+radius))diagnostics.InterlockedAdd(8,1);
 diagnostics.InterlockedXor(28,colorHash(stable)^colorHash(entityMaps.Load(8*stable+4)));
 if(sample==0u){if((renderFlags&8u)!=0u)diagnostics.Store(28,state.Load(poolCommandByte));uint generation=state.Load(G4_SOURCE_GENERATION_BYTE),physicsError=state.Load(0);diagnostics.Store(12,generation);diagnostics.Store(16,physicsError);diagnostics.Store(20,expectedGeneration);diagnostics.Store(24,attemptTick);if(!physicsError&&generation!=expectedGeneration)diagnostics.InterlockedOr(0,4);if(state.Load(G4_SOURCE_EPOCH_BYTE)!=expectedEpoch)diagnostics.InterlockedOr(0,8);diagnostics.Store(32,stable);for(uint word=0;word<G4_V_CAMERA_WORDS;word++)diagnostics.Store(64+4*word,cameraWord(word));}
 if(sample+1u==instanceCount)diagnostics.Store(36,stable);
}

[numthreads(256,1,1)]void play_pick(uint3 g:SV_GroupID,uint lane:SV_GroupIndex){uint i=g.x*256u+lane;if(i>=objectCount||(renderFlags&4u)==0)return;float2 p=float2(scalar(i,0),scalar(i,1))-float2(pickX,pickY);float r=scalar(i,8);if(dot(p,p)<=r*r)diagnostics.InterlockedMin(40,i);}
[numthreads(1,1,1)]void play_pick_resolve(){uint i=diagnostics.Load(40);if((renderFlags&4u)==0){i=selectedID<objectCount?entityMaps.Load(8*selectedID):0xffffffffu;diagnostics.Store(40,i);}if(i<objectCount){uint stable=bodies.Load(4*(15*entityCapacity+i));diagnostics.Store(40,stable);diagnostics.Store(44,entityMaps.Load(8*stable+4));diagnostics.Store4(48,uint4(asuint(scalar(i,0)),asuint(scalar(i,1)),asuint(scalar(i,2)),asuint(scalar(i,3))));}}
