// Billiards scene v1: actual 2D driven disks in independent physical tables.
// This only supplies geometry, initial conditions and declared external forces.
#include "billiards-layout.h"
uint billiardsHash(uint v){v^=18228u;v^=v>>16;v*=0x7feb352du;v^=v>>15;v*=0x846ca68bu;return v^(v>>16);}
uint billiardsColumns(uint population){uint tables=(population+15u)/16u;return tables<=1?1u:1u<<((firstbithigh(tables-1u)+2u)/2u);}
float4 billiardsBounds(uint i){uint tag=source.Load(4*(12*capacity+i));float2 origin=float2(tag&65535u,tag>>16)*4.0;return float4(origin,origin+float2(1.5,1.0));}
float4 physicalBounds(uint i){return fixture>=9u?billiardsBounds(i):float4(0,0,1,1);}
float2 billiardsAcceleration(uint stable){if((flags&1u)==0)return 0;uint table=stable/16u,local=stable%16u,h=billiardsHash(table),phase=(tick+(h&63u))/64u;float2 com=float2((phase&1u)?-.75:.75,((phase+(h>>6))&1u)?-.5:.5);if(fixture!=9u){uint pulse=(tick+(h>>12)%48u)/48u;com.x+=(((local&1u)^pulse)&1u)?-.5:.5;}return com;}
void initializeBilliard(uint i,uint columns){uint stable=slot(i),table=stable/16u,local=stable%16u,h=billiardsHash(table),col=table%columns,row=table/columns;float2 origin=float2(col,row)*4.0;float x=.125+.375*float(local%4u),y=.125+.25*float(local/4u),vx=.25,vy=((h>>4)&1u)?.125:-.125;
 if(fixture==9u){vx+=float(int((billiardsHash(stable)>>3)&3u)-1)*.03125;if(local==15u){x=1.5-.0625-1.0/512.0;vx=.5;}}
 else if(fixture==10u){uint pair=local/2u;x=.1875+.375*float(pair%4u)+((local&1u)?1.0:-1.0)*.078125;y=.25+.5*float(pair/4u);vx+=((local&1u)?-.375:.375);}
 else{x=.75+(float(local%4u)-1.5)*.140625;y=.5+(float(local/4u)-1.5)*.140625;uint subset=4u+4u*(h&3u);if(local<subset){vx+=(local%4u<2u?.375:-.375);vy+=(local/4u<2u?.25:-.25);}else{vx+=((local&1u)?.125:-.125);}}
 float values[12]={origin.x+x,origin.y+y,vx,vy,0,0,1,512,.0625,0,vx*vx+vy*vy,0};for(uint f=0;f<12;f++)source.Store(4*(f*capacity+i),asuint(values[f]));source.Store(4*(12*capacity+i),col|(row<<16));source.Store(4*(13*capacity+i),0);source.Store(4*(14*capacity+i),1);
}
