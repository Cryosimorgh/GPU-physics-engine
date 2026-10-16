#include "layout.hlsl"
ByteAddressBuffer source:register(t0);
RWByteAddressBuffer output:register(u0);
struct Vertex {float4 position:SV_Position;};
Vertex vs(uint i:SV_VertexID){Vertex v;v.position=float4(2,2,0,1);if(i>=n)return v;
 uint x=source.Load(address(layout,capacity,i,0)),y=source.Load(address(layout,capacity,i,1)),r=source.Load(address(layout,capacity,i,8)),id=source.Load(address(layout,capacity,i,15));
 output.Store(4*i,x^((y<<7)|(y>>25))^r^id);uint old;output.InterlockedAdd(4*(capacity+i),1,old);
 // Clipped points isolate actual vertex-stage consumption. No pixel shader,
 // render target, swap chain or presentation feature is implemented here.
 v.position=float4(2+asfloat(x),2+asfloat(y),0,1);return v;}
