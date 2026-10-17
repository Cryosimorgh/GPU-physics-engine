// Playable mode only: SI units, solid-sphere horizontal rolling plus planar yaw.
#include "pool-layout.h"
uint poolBase(){return POOL_DATA(metaGuard());}
float material(uint field){return asfloat(m.Load(poolBase()+4*field));}
float2 rolling(uint i,uint first){return asfloat(uint2(m.Load(POOL_ROLL(poolBase(),first,i)),m.Load(POOL_ROLL(poolBase(),first+1,i))));}
void storeRolling(uint i,uint first,float2 v){m.Store(POOL_ROLL(poolBase(),first,i),asuint(v.x));m.Store(POOL_ROLL(poolBase(),first+1,i),asuint(v.y));}
void initializePool(uint i){
 if(i==0){float defaults[8]={POOL_BODY_RESTITUTION,POOL_RAIL_RESTITUTION,POOL_SLIDING_FRICTION,POOL_ROLLING_RESISTANCE,POOL_BALL_FRICTION,POOL_RAIL_FRICTION,POOL_GRAVITY,POOL_IMPACT_THRESHOLD};for(uint j=0;j<8;j++)m.Store(poolBase()+4*j,asuint(defaults[j]));}
 uint id=slot(i);float2 p=float2(POOL_CUE_X,POOL_CUE_Y);
 if(id){uint order[15]={1,9,2,3,8,10,11,4,12,5,6,13,7,14,15};uint row=0,k=0;for(uint q=0;q<15;q++)if(order[q]==id)k=q;while(k>row){k-=row+1;row++;}float pitch=2*POOL_RADIUS+POOL_RACK_GAP;p=float2(POOL_RACK_X+row*pitch*.8660254037844386,POOL_CUE_Y+(float(k)-row*.5)*pitch);}
 float values[12]={p.x,p.y,0,0,0,0,1.0/POOL_MASS,1.0/(.4*POOL_MASS*POOL_RADIUS*POOL_RADIUS),POOL_RADIUS,POOL_RAIL_RESTITUTION,0,0};
 for(uint f=0;f<12;f++)source.Store(4*(f*capacity+i),asuint(values[f]));source.Store(4*(12*capacity+i),0);source.Store(4*(13*capacity+i),1000);source.Store(4*(14*capacity+i),0);storeRolling(i,0,0);storeRolling(i,2,0);
}
float2 poolImpulse(uint i){
 if(unused.Load(0)!=PLAY_COMMAND_MAGIC)return 0;
 uint id=unused.Load(4);if(id>=16u){if(i==0)fail(128);return 0;}
 float2 dv=asfloat(unused.Load2(16));bool valid=id==0&&maps.Load(8*id)<n&&maps.Load(8*id+4)==unused.Load(8)&&unused.Load(12)==m.Load(G4_SOURCE_EPOCH_BYTE)&&unused.Load(28)==tick&&all(isfinite(dv))&&dot(dv,dv)<=PLAY_MAX_IMPULSE_DELTA_V*PLAY_MAX_IMPULSE_DELTA_V*1.00001;
 if(!valid){if(i==0)fail(128);return 0;}
 bool moving=false;if((unused.Load(24)&0x80000000u)==0)for(uint j=0;j<n;j++)moving=moving||src(j,2)!=0||src(j,3)!=0||src(j,5)!=0||any(rolling(j,0)!=0);
 if(i==0)m.Store(poolBase()+POOL_COMMAND_STATUS_OFFSET,moving?2:1);
 return !moving&&slot(i)==0?dv:float2(0,0);
}
// Coulomb slip force: dv=-mu*g*dt, d(R*omega)=+(5/2)*mu*g*dt.
// Stop exactly at no-slip; spend the remaining step on rolling resistance.
void poolCloth(uint i,inout float vx,inout float vy,inout float yaw){
 float2 v=float2(vx,vy),u=rolling(i,0),slip=v-u;float s=length(slip),time=dt();
 if(s>0&&material(2)>0){float a=material(2)*material(6),t=min(time,s/(3.5*a)),dv=a*t;float2 direction=slip/s;v-=direction*dv;u+=direction*(2.5*dv);time-=t;if(t<dt()){v=(v+u*0.4)/1.4;u=v;}}
 if(length(v-u)<1e-6&&time>0&&material(3)>0){float speed=length(v),dv=min(speed,material(3)*material(6)*time);if(speed>0)v*=max(0.,(speed-dv)/speed);u=v;}
 float spinStep=material(3)*material(6)*dt()/POOL_RADIUS;yaw=sign(yaw)*max(0.,abs(yaw)-spinStep);
 vx=v.x;vy=v.y;storeRolling(i,2,u);
}
double poolTarget(uint a,uint b,double nx,double ny,double gap){
 bool wall=b>=n;uint bit=wall?16u+b-n:slot(b);bool persistent=(source.Load(4*(12*capacity+a))&(1u<<bit))!=0;
 double vx=double(asfloat(m.Load(AT(FREE_VX,a)))),vy=double(asfloat(m.Load(AT(FREE_VY,a))));if(!wall){vx-=double(asfloat(m.Load(AT(FREE_VX,b))));vy-=double(asfloat(m.Load(AT(FREE_VY,b))));}
 double vn=vx*nx+vy*ny,target=-max(0.0,gap)/double(dt());
 if(!persistent&&vn < -double(material(7))&&vn < -max(0.0,gap)/double(dt()))target=max(target,-double(material(wall?1:0))*vn);
 return target;
}
float poolMu(uint b){return material(b>=n?5:4);}
float2 poolNextPosition(uint i){return asfloat(uint2(m.Load(poolBase()+POOL_POSITION_X_OFFSET+4*i),m.Load(poolBase()+POOL_POSITION_Y_OFFSET+4*i)));}
uint poolPersistent(uint i){uint mask=0;float2 p=poolNextPosition(i);for(uint j=0;j<n;j++)if(j!=i&&length(p-poolNextPosition(j))<=2*POOL_RADIUS+POOL_CONTACT_SLOP)mask|=1u<<slot(j);if(p.x<=POOL_RADIUS+POOL_CONTACT_SLOP)mask|=1u<<16;if(p.x>=POOL_TABLE_WIDTH-POOL_RADIUS-POOL_CONTACT_SLOP)mask|=1u<<17;if(p.y<=POOL_RADIUS+POOL_CONTACT_SLOP)mask|=1u<<18;if(p.y>=POOL_TABLE_HEIGHT-POOL_RADIUS-POOL_CONTACT_SLOP)mask|=1u<<19;return mask;}
// Global energy veto before publication. A failed tick never commits rolling state.
void poolEnergy(){double before=0,after=0;for(uint j=0;j<n;j++){double vx=asfloat(m.Load(AT(FREE_VX,j))),vy=asfloat(m.Load(AT(FREE_VY,j))),w=asfloat(m.Load(AT(FREE_OMEGA,j)));double2 u=double2(rolling(j,2));before+=.5*double(POOL_MASS)*(vx*vx+vy*vy)+.2*double(POOL_MASS)*((u.x*u.x+u.y*u.y)+double(POOL_RADIUS)*POOL_RADIUS*w*w);vx=val(j,2);vy=val(j,3);w=val(j,5);after+=.5*double(POOL_MASS)*(vx*vx+vy*vy)+.2*double(POOL_MASS)*((u.x*u.x+u.y*u.y)+double(POOL_RADIUS)*POOL_RADIUS*w*w);}if(after>before+256.0*double(U)*max(before,1e-12))fail(POOL_ENERGY_ERROR);}
