// Scene-only extension. Constraint projection and convergence budgets unchanged.
#include "playground-layout.h"
uint arenaColumns(){return uint(ceil(sqrt(float(n))));}
float2 arenaSize(){uint columns=arenaColumns();return float2(columns,(n+columns-1)/columns)*PLAY_PITCH+2*PLAY_MARGIN;}
void initializePlayground(uint i){uint stable=slot(i),col=stable%arenaColumns(),row=stable/arenaColumns(),h=billiardsHash(stable/2u);
 float x=PLAY_MARGIN+float(col/2u)*(2*PLAY_PITCH)+float(col&1u)*(2*PLAY_RADIUS+PLAY_PAIR_GAP),y=PLAY_MARGIN+row*PLAY_PITCH;
 float vx=float(int(h&255u)-128)/1024.+((col&1u)?-.35:.35),vy=float(int((h>>8)&255u)-128)/1024.;
 float values[12]={x,y,vx,vy,0,0,1,512,PLAY_RADIUS,.75,vx*vx+vy*vy,0};for(uint f=0;f<12;f++)source.Store(4*(f*capacity+i),asuint(values[f]));source.Store(4*(12*capacity+i),0);source.Store(4*(13*capacity+i),0);source.Store(4*(14*capacity+i),1);
}
float2 playgroundImpulse(uint i){if(unused.Load(0)!=PLAY_COMMAND_MAGIC)return 0;uint id=unused.Load(4),generation=unused.Load(8),epoch=unused.Load(12),commandTick=unused.Load(28);float2 dv=asfloat(unused.Load2(16));
 // HLSL boolean expressions must not be relied on to short-circuit raw loads.
 if(id>=capacity){if(i==0)fail(128);return 0;}
 bool valid=maps.Load(8*id)<n&&maps.Load(8*id+4)==generation&&epoch==m.Load(G4_SOURCE_EPOCH_BYTE)&&commandTick==tick&&all(isfinite(dv))&&dot(dv,dv)<=PLAY_MAX_IMPULSE_DELTA_V*PLAY_MAX_IMPULSE_DELTA_V*1.00001;
 if(!valid){if(i==0)fail(128);return 0;}return slot(i)==id?dv:float2(0,0);
}
