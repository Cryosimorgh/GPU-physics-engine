// Small native telemetry overlay. CPU uploads only bounded text pixels, never
// entity state. Pixels describe the last CPU-verified completed generation.
#include "execution-layout.h"
#include "hud-digits.h"
ByteAddressBuffer completedState:register(t1);
ByteAddressBuffer glyphPixels:register(t3);
#include "viewer-cbuffer.hlsl"
struct V{float4 p:SV_Position;nointerpolation float4 color:COLOR;};
V hud_vs(uint vertex:SV_VertexID,uint instance:SV_InstanceID){
 uint2 packed=glyphPixels.Load2(G4_V_HUD_PIXEL_STRIDE*instance);float2 corner[6]={float2(0,0),float2(0,1),float2(1,1),float2(0,0),float2(1,1),float2(1,0)};
 float2 origin=float2(packed.x&65535,packed.x>>16),size=2;bool visible=true;float4 color=float4(float3(packed.y&255,(packed.y>>8)&255,(packed.y>>16)&255)/255,1);
 if((packed.x&0xffff0000u)==G4_HUD_GPU_MARKER&&packed.x!=0xffffffffu){uint digit=(packed.x>>4)&15u,bit=packed.x&15u,kind=(packed.x>>8)&1u;uint value=completedState.Load(kind==0?G4_SOURCE_GENERATION_BYTE:0);uint divisors[10]={1000000000u,100000000u,10000000u,1000000u,100000u,10000u,1000u,100u,10u,1u};uint font[10]=G4_HUD_DIGIT_BITS;visible=(font[(value/divisors[digit])%10u]&(1u<<bit))!=0;origin=float2((kind==0?72:488)+8*digit+2*(bit%3),18+2*(bit/3));if(kind!=0)color=value?float4(1,.25,.25,1):float4(.35,.9,.45,1);}

 if(packed.x==0xffffffffu){origin=0;size=float2(pixelWidth,94);}
 float2 pixel=origin+corner[vertex]*size;V o;o.p=float4(pixel.x*2/pixelWidth-1,1-pixel.y*2/pixelHeight,0,1);
 o.color=color;if(!visible)o.p=float4(2,2,0,1);return o;
}
float4 hud_ps(V v):SV_Target{return v.color;}
