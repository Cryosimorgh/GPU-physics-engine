// Independent CPU binary64 oracle. It never participates in GPU stage control.
#include "physics.h"
#include "physics-layout.h"
#include "billiards-layout.h"
#include "execution-layout.h"
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <math.h>
#include <float.h>
#define U (0x1p-23)
#define NONE UINT32_MAX
static int compare_cell_keys(const void *a,const void *b){uint64_t x,y;memcpy(&x,a,8);memcpy(&y,b,8);return (x>y)-(x<y);}
static uint32_t billiards_hash_cpu(uint32_t v){v^=18228u;v^=v>>16;v*=0x7feb352du;v^=v>>15;v*=0x846ca68bu;return v^(v>>16);}
typedef struct Verify {const PhysicsConfig *cfg;uint32_t *s,*t,*m,*c,*args,*parent,*sizes,*degree;unsigned char *seen,*scatter;uint64_t cap,C,scan_end;const uint32_t *slots,*gens,*dense;PhysicsVerification *v;} Verify;
static float word(uint32_t u){float f;memcpy(&f,&u,4);return f;}
static float f(Verify *v,int trial,uint32_t i,int field){return word((trial?v->t:v->s)[(uint64_t)field*v->cap+i]);}
static double impulse(Verify *v,const uint32_t *rec,int tangent){uint64_t k=(uint64_t)(rec-v->c)/20,at=tangent?G3_LAMBDA_T((uint64_t)v->cfg->contacts,k):G3_LAMBDA_N((uint64_t)v->cfg->contacts,k);double x;memcpy(&x,(char*)v->c+at,8);return x;}
static uint32_t slot(Verify *v,uint32_t i){return v->slots?v->slots[i]:i;}
static uint32_t gen(Verify *v,uint32_t i){return v->gens?v->gens[i]:1;}
static uint64_t wide(Verify *v,uint64_t at){uint64_t value;memcpy(&value,(char*)v->m+at,8);return value;}
static uint32_t meta(Verify *v,uint64_t at){return v->m[at/4];}
static uint32_t root(Verify *v,uint32_t i){while(v->parent[i]!=i){v->parent[i]=v->parent[v->parent[i]];i=v->parent[i];}return i;}
static double gamma64(uint32_t k){double ku=(double)k*U;return ku<1?ku/(1-ku):INFINITY;}
static double max2(double x,double y){return x>y?x:y;}
static double ulp32(float x){uint32_t bits;float a=fabsf(x);memcpy(&bits,&a,4);return (double)word(bits+1)-a;}
// Independent exact all-body initial-state oracle for rendering-only controls.
// Called outside frame timing, never between physics GPU stages.
int ph_verify_initial(Physics *p,const PhysicsConfig *cfg,const uint32_t *slots,uint64_t *checked){
 const void *data=NULL;uint64_t bytes=0;*checked=0;
 if(cfg->fixture<9||!ph_read(p,0,&data,&bytes)||bytes!=64ull*cfg->capacity)return 0;
 const uint32_t *words=data;uint32_t columns=1;while((uint64_t)columns*columns<(cfg->capacity+15)/16)columns*=2;
 int ok=1;
 for(uint32_t i=0;i<cfg->n&&ok;i++){
  uint32_t stable=slots?slots[i]:i,table=stable/16,local=stable%16,h=billiards_hash_cpu(table);
  double x=.125+.375*(local%4),y=.125+.25*(local/4),vx=.25,vy=(h>>4)&1?.125:-.125;
  if(cfg->fixture==9){vx+=((int)((billiards_hash_cpu(stable)>>3)&3)-1)*.03125;if(local==15){x=1.5-.0625-1./512;vx=.5;}}
  else if(cfg->fixture==10){uint32_t pair=local/2;x=.1875+.375*(pair%4)+(local&1?1:-1)*.078125;y=.25+.5*(pair/4);vx+=local&1?-.375:.375;}
  else{x=.75+((int)(local%4)-1.5)*.140625;y=.5+((int)(local/4)-1.5)*.140625;if(local<4+4*(h&3)){vx+=local%4<2?.375:-.375;vy+=local/4<2?.25:-.25;}else vx+=local&1?.125:-.125;}
  uint32_t col=table%columns,row=table/columns;
  float expected[12]={(float)(4.*col+x),(float)(4.*row+y),(float)vx,(float)vy,0,0,1,512,.0625f,0,(float)(vx*vx+vy*vy),0};
  for(uint32_t k=0;k<12;k++){uint32_t value;memcpy(&value,&expected[k],4);if(words[(uint64_t)k*cfg->capacity+i]!=value){fprintf(stderr,"initial mismatch body %u field %u\n",i,k);ok=0;break;}}
  if(words[12ull*cfg->capacity+i]!=(col|(row<<16))||words[13ull*cfg->capacity+i]!=0||words[14ull*cfg->capacity+i]!=1||words[15ull*cfg->capacity+i]!=stable)ok=0;
  if(ok)(*checked)++;
 }
 return ph_unmap(p)&&ok;
}
static int bit(unsigned char *seen,uint64_t index,int insert){unsigned char b=(unsigned char)(1u<<(index%8));int old=(seen[index/8]&b)!=0;if(insert)seen[index/8]|=b;return old;}
static uint64_t pair_index(Verify *v,uint32_t a,uint32_t b){if(b>=v->cfg->n)return (v->cfg->n<=4096?v->cap*v->cap:16*v->cap)+4ull*slot(v,a)+b-v->cfg->n;uint32_t x=slot(v,a),y=slot(v,b);if(v->cfg->n<=4096)return (uint64_t)x*v->cap+y;return (uint64_t)x*16+y-x-1;}
typedef struct Geometry {double nx,ny,gap,target,aa,ab,kn,kt;} Geometry;
static void physical_bounds(Verify *v,uint32_t a,double out[4]){out[0]=out[1]=0;out[2]=out[3]=1;if(v->cfg->fixture>=9){uint32_t tag=v->s[12*v->cap+a];out[0]=(tag&65535u)*4.;out[1]=(tag>>16)*4.;out[2]=out[0]+1.5;out[3]=out[1]+1.;}}
static Geometry geometry(Verify *v,uint32_t a,uint32_t b){Geometry g={0};double x=f(v,1,a,0),y=f(v,1,a,1),ra=f(v,1,a,8),dt=v->cfg->dt;uint32_t n=v->cfg->n;if(b>=n){uint32_t w=b-n;double bounds[4];physical_bounds(v,a,bounds);g.gap=w==0?x-bounds[0]-ra:w==1?bounds[2]-ra-x:w==2?y-bounds[1]-ra:bounds[3]-ra-y;g.nx=w==0?1:w==1?-1:0;g.ny=w==2?1:w==3?-1:0;double v0=word(meta(v,G3_FREE_VX(v->cap,a)))*g.nx+word(meta(v,G3_FREE_VY(v->cap,a)))*g.ny;g.target=v0 < -g.gap/dt?max2(-g.gap/dt,-f(v,1,a,9)*v0):-g.gap/dt;g.aa=ra;g.kn=f(v,1,a,6);return g;}double dx=x-f(v,1,b,0),dy=y-f(v,1,b,1),d=hypot(dx,dy),rb=f(v,1,b,8);g.nx=d==0?-1:dx/d;g.ny=d==0?0:dy/d;g.gap=d-ra-rb;g.target=-g.gap/dt;g.aa=d*ra/(ra+rb);g.ab=d*rb/(ra+rb);g.kn=(double)f(v,1,a,6)+f(v,1,b,6);g.kt=(v->cfg->flags&2)?g.kn+f(v,1,a,7)*g.aa*g.aa+f(v,1,b,7)*g.ab*g.ab:0;return g;}
static int eligible(Verify *v,uint32_t a,uint32_t b,int free_velocity){uint32_t n=v->cfg->n;int awakeA=free_velocity?(meta(v,G3_FREE_SLEEP(v->cap,a))<v->cfg->sleep_frames||word(meta(v,G3_FREE_VX(v->cap,a)))!=0||word(meta(v,G3_FREE_VY(v->cap,a)))!=0||word(meta(v,G3_FREE_OMEGA(v->cap,a)))!=0):v->t[14*v->cap+a]!=0;int awakeB=b<n?(free_velocity?(meta(v,G3_FREE_SLEEP(v->cap,b))<v->cfg->sleep_frames||word(meta(v,G3_FREE_VX(v->cap,b)))!=0||word(meta(v,G3_FREE_VY(v->cap,b)))!=0||word(meta(v,G3_FREE_OMEGA(v->cap,b)))!=0):v->t[14*v->cap+b]!=0):0;if(!awakeA&&!awakeB)return 0;if(v->cfg->fixture>=9&&b<n){Geometry g=geometry(v,a,b);double avx=free_velocity?word(meta(v,G3_FREE_VX(v->cap,a))):f(v,1,a,2),avy=free_velocity?word(meta(v,G3_FREE_VY(v->cap,a))):f(v,1,a,3),bvx=free_velocity?word(meta(v,G3_FREE_VX(v->cap,b))):f(v,1,b,2),bvy=free_velocity?word(meta(v,G3_FREE_VY(v->cap,b))):f(v,1,b,3);return g.gap<=0||(avx-bvx)*g.nx+(avy-bvy)*g.ny<g.target;}
 // Match the frozen f32 plane model, independently enumerating all pairs.
 float dx=f(v,1,a,0)-(b<n?f(v,1,b,0):0),dy=f(v,1,a,1)-(b<n?f(v,1,b,1):0);volatile float dx2=dx*dx,dy2=dy*dy;float d2=dx2+dy2,d=sqrtf(d2),gap=d-f(v,1,a,8)-(b<n?f(v,1,b,8):0),nx=d2==0?-1:dx/d,ny=d2==0?0:dy/d;float avx=free_velocity?word(meta(v,G3_FREE_VX(v->cap,a))):f(v,1,a,2),avy=free_velocity?word(meta(v,G3_FREE_VY(v->cap,a))):f(v,1,a,3),bvx=b<n?(free_velocity?word(meta(v,G3_FREE_VX(v->cap,b))):f(v,1,b,2)):0,bvy=b<n?(free_velocity?word(meta(v,G3_FREE_VY(v->cap,b))):f(v,1,b,3)):0;float target=-gap/v->cfg->dt;if(b>=n){uint32_t w=b-n;double bounds[4];physical_bounds(v,a,bounds);gap=w==0?f(v,1,a,0)-(float)bounds[0]-f(v,1,a,8):w==1?(float)bounds[2]-f(v,1,a,8)-f(v,1,a,0):w==2?f(v,1,a,1)-(float)bounds[1]-f(v,1,a,8):(float)bounds[3]-f(v,1,a,8)-f(v,1,a,1);nx=w==0?1:w==1?-1:0;ny=w==2?1:w==3?-1:0;float v0=word(meta(v,G3_FREE_VX(v->cap,a)))*nx+word(meta(v,G3_FREE_VY(v->cap,a)))*ny;target=v0 < -gap/v->cfg->dt?fmaxf(-gap/v->cfg->dt,-f(v,1,a,9)*v0):-gap/v->cfg->dt;}volatile float px=(avx-bvx)*nx,py=(avy-bvy)*ny;float vn=px+py;return gap<=0||vn<target;}
static int penetration(Verify *v,uint32_t a,uint32_t b){double dx=(double)f(v,0,a,0)-f(v,0,b,0),dy=(double)f(v,0,a,1)-f(v,0,b,1),d=hypot(dx,dy),pen=max2(0,f(v,0,a,8)+f(v,0,b,8)-d),scale=max2(.001,max2(max2(fabs(f(v,0,a,2)),fabs(f(v,0,a,3))),max2(fabs(f(v,0,b,2)),fabs(f(v,0,b,3))))),bound=(ulp32(f(v,0,a,0))+ulp32(f(v,0,a,1))+ulp32(f(v,0,b,0))+ulp32(f(v,0,b,1)))*.5+8*U*(d+f(v,0,a,8)+f(v,0,b,8))+44*U*scale*v->cfg->dt;if(pen/(bound>0?bound:DBL_MIN)>v->v->penetration_ratio)v->v->penetration_ratio=pen/(bound>0?bound:DBL_MIN);return pen<=bound;}
static int required(Verify *v,uint32_t a,uint32_t b){if(b<v->cfg->n&&slot(v,a)>slot(v,b)){uint32_t tmp=a;a=b;b=tmp;}int needed=eligible(v,a,b,1)||eligible(v,a,b,0);if(needed){v->v->mandatory_pairs++;if(!bit(v->seen,pair_index(v,a,b),0)){fprintf(stderr,"CPU missing mandatory pair %u %u\n",a,b);return 0;}}return b>=v->cfg->n||penetration(v,a,b);}
static int fixture_group(Verify *v,uint32_t s,uint32_t *size,uint32_t *group){uint32_t fixture=v->cfg->fixture;if(fixture>=9){*size=16;*group=s/16;return 1;}*size=fixture==0?1:fixture==4?8:fixture==5&&((s/1024)%16==0)?16:2;*group=fixture==5?(s/1024)*512+(s%1024)/ *size:s/ *size;return 1;}
static float advance32(float initial,float delta,uint32_t ticks){for(uint32_t t=0;t<ticks;t++){volatile float next=initial+delta;initial=next;}return initial;}
static int certificate(Verify *v,uint32_t ticks){if(v->cfg->fixture>=9){uint32_t columns=1;while((uint64_t)columns*columns<(v->cap+15)/16)columns*=2;for(uint32_t i=0;i<v->cfg->n;i++){uint32_t table=slot(v,i)/16,tag=v->s[12*v->cap+i],expected=(table%columns)|((table/columns)<<16);if(tag!=expected||f(v,0,i,8)!=BILLIARDS_RADIUS||f(v,0,i,6)!=1||f(v,0,i,7)!=512||f(v,0,i,9)!=0)return 0;double bounds[4];physical_bounds(v,i,bounds);for(int trial=0;trial<=1;trial++){if(f(v,trial,i,0)<bounds[0]+.0625-ulp32(f(v,trial,i,0))||f(v,trial,i,0)>bounds[2]-.0625+ulp32(f(v,trial,i,0))||f(v,trial,i,1)<bounds[1]+.0625-ulp32(f(v,trial,i,1))||f(v,trial,i,1)>bounds[3]-.0625+ulp32(f(v,trial,i,1)))return 0;if(hypot(f(v,trial,i,2),f(v,trial,i,3))*v->cfg->dt+f(v,trial,i,8)>=.25)return 0;}}return 1;}if(v->cfg->fixture>6||ticks>220||v->cfg->dt!=1.f/128)return 0;uint32_t n=v->cfg->n;
 for(uint32_t i=0;i<n;i++){uint32_t size,group;fixture_group(v,slot(v,i),&size,&group);uint32_t cols=1,groups=v->cfg->fixture==5?(n+1)/2:(n+size-1)/size;while((uint64_t)cols*cols<groups)cols*=2;double cx=(group%cols)*4.,cy=(group/cols)*4.;if(v->cfg->fixture==6&&slot(v,i)<2)cx=cy=0;
  // Full-object certificate: a group stays inside its 2.5-wide box. Distinct
  // group centers are four units apart. Reach below .5 cannot bridge them.
  if(fabs(f(v,1,i,0)-cx)>1.25||fabs(f(v,1,i,1)-cy)>1.25||fabs(f(v,0,i,0)-cx)>1.25||fabs(f(v,0,i,1)-cy)>1.25)return 0;
  double speed=hypot(f(v,1,i,2),f(v,1,i,3)),freeSpeed=hypot(word(meta(v,G3_FREE_VX(v->cap,i))),word(meta(v,G3_FREE_VY(v->cap,i))));if(f(v,1,i,8)+v->cfg->dt*max2(speed,freeSpeed)>=.5)return 0;
  // Independent exact ballistic/pair trajectories at the qualified dyadic dt.
  int hot=v->cfg->fixture==1?group%100==0:v->cfg->fixture==2?group%10==0:v->cfg->fixture==3;
  if(v->cfg->fixture==0||((v->cfg->fixture==1||v->cfg->fixture==2||v->cfg->fixture==3)&&!hot)){
   float x=advance32((float)(cx+(size==1?0:(slot(v,i)%2==0?-.25:.25))),.125f*v->cfg->dt,ticks),y=advance32((float)cy,.0625f*v->cfg->dt,ticks);if(f(v,0,i,0)!=x||f(v,0,i,1)!=y||f(v,0,i,2)!=.125f||f(v,0,i,3)!=.0625f)return 0;
  }else if(hot){float x=(float)(cx+(slot(v,i)%2==0?-.0625:.0625)),vx=ticks==1?(slot(v,i)%2==0?.5f:-.5f):0;if(f(v,0,i,0)!=x||f(v,0,i,1)!=(float)cy||f(v,0,i,2)!=vx||f(v,0,i,3)!=0)return 0;}
 }
 return 1;
}
static void *snapshot(Physics *p,int which,uint64_t *bytes){const void *data=NULL;if(!ph_read(p,which,&data,bytes))return NULL;void *copy=malloc((size_t)*bytes);if(copy)memcpy(copy,data,(size_t)*bytes);if(!ph_unmap(p)){free(copy);return NULL;}return copy;}
int ph_verify(Physics *p,const PhysicsConfig *cfg,uint32_t ticks,const uint32_t *slots,const uint32_t *gens,const uint32_t *dense,PhysicsVerification *result){uint64_t *occupancy_keys=NULL;uint64_t moving=0,wall_count=0,positive_body=0,positive_wall=0;Verify v={0};v.cfg=cfg;v.cap=cfg->capacity;v.slots=slots;v.gens=gens;v.dense=dense;v.v=result;memset(result,0,sizeof(*result));uint64_t bytes[5];int ok=0;v.s=snapshot(p,0,&bytes[0]);v.t=snapshot(p,1,&bytes[1]);v.m=snapshot(p,2,&bytes[2]);v.c=snapshot(p,3,&bytes[3]);v.args=snapshot(p,4,&bytes[4]);if(!v.s||!v.t||!v.m||!v.c||!v.args)goto done;
 v.scan_end=G3_METADATA_END(v.cap);for(uint64_t k=v.cap;k>256;){k=(k+255)/256;v.scan_end+=16*k;}if(bytes[0]!=64*v.cap||bytes[1]!=64*v.cap+256||bytes[2]!=v.scan_end+256||bytes[3]!=G3_ARENA_END((uint64_t)cfg->contacts)+256||bytes[4]!=G3_ARGS_END((uint64_t)cfg->n,cfg->flags)+G3_GUARD_BYTES)goto done;
 for(int j=0;j<64;j++){if(v.t[16*v.cap+j]!=0xbaadc0de||v.m[v.scan_end/4+j]!=0xbaadc0de||v.c[G3_ARENA_END((uint64_t)cfg->contacts)/4+j]!=0xbaadc0de||v.args[G3_ARGS_END((uint64_t)cfg->n,cfg->flags)/4+j]!=0xbaadc0de)goto done;result->guards+=4;}
 if(v.m[0]!=0){ok=1;goto done;}v.C=v.m[2];if(v.C>cfg->contacts||v.m[13]!=cfg->n||v.m[20]!=G3_TAG||v.m[21]!=G3_METADATA_END(v.cap)||v.m[22]!=G3_ARENA_END((uint64_t)cfg->contacts)||v.m[23]!=G3_PARENT(v.cap,cfg->n-1)||v.m[24]!=(cfg->contacts?G3_COLOR_CURSOR((uint64_t)cfg->contacts,2ull*cfg->contacts-1):0)||v.m[25]!=v.scan_end||v.m[26]!=cfg->n||v.m[27]!=cfg->capacity||v.m[28]!=80)goto done;
 v.parent=malloc((size_t)v.cap*4);v.sizes=calloc((size_t)v.cap,4);v.degree=calloc((size_t)v.cap,4);uint64_t bits=(cfg->n<=4096?v.cap*v.cap:16*v.cap)+4*v.cap;v.seen=calloc((size_t)((bits+7)/8),1);v.scatter=calloc((size_t)((2*v.C+7)/8+1),1);if(!v.parent||!v.sizes||!v.degree||!v.seen||!v.scatter)goto done;for(uint32_t i=0;i<v.cap;i++)v.parent[i]=i;if(cfg->fixture>=9){occupancy_keys=malloc((size_t)cfg->n*8);if(!occupancy_keys)goto done;}
 for(uint32_t i=0;i<cfg->n;i++){
  if(v.s[15*v.cap+i]!=slot(&v,i)||v.t[15*v.cap+i]!=slot(&v,i)||meta(&v,G3_PREPARE_COVERAGE(v.cap,i))!=1||meta(&v,G3_PUBLISH_COVERAGE(v.cap,i))!=1)goto done;
  for(int field=0;field<12;field++)if(!isfinite(f(&v,0,i,field))||!isfinite(f(&v,1,i,field)))goto done;
  for(int field=6;field<=9;field++)if(v.s[field*v.cap+i]!=v.t[field*v.cap+i])goto done;
  if(v.s[12*v.cap+i]!=v.t[12*v.cap+i])goto done;if(cfg->fixture>=9){double inv_edge=ph_cell_mode_value(p)?G4_FINE_CELL_RECIPROCAL:.25;
    double cx=floor((double)f(&v,1,i,0)*inv_edge),cy=floor((double)f(&v,1,i,1)*inv_edge);
    if(cx < -2147483647.||cx>=2147483647.||cy < -2147483647.||cy>=2147483647.)goto done;
    occupancy_keys[i]=((uint64_t)(uint32_t)(int32_t)cx<<32)|(uint32_t)(int32_t)cy;if(f(&v,0,i,0)!=f(&v,1,i,0)||f(&v,0,i,1)!=f(&v,1,i,1))moving++;}
  for(int axis=0;axis<3;axis++){int xfield=axis==2?4:axis,vfield=axis==2?5:axis+2;volatile float step=f(&v,1,i,vfield)*cfg->dt;double bounds[4];physical_bounds(&v,i,bounds);float want=f(&v,1,i,xfield)+step;if(axis<2&&(cfg->flags&4))want=fminf((float)bounds[axis+2]-f(&v,1,i,8),fmaxf((float)bounds[axis]+f(&v,1,i,8),want));if(f(&v,0,i,xfield)!=want||f(&v,0,i,vfield)!=f(&v,1,i,vfield))goto done;}
  double bounds[4];physical_bounds(&v,i,bounds);if((cfg->flags&4)&&(f(&v,0,i,0)<bounds[0]+f(&v,0,i,8)-ulp32(f(&v,0,i,0))||f(&v,0,i,0)>bounds[2]-f(&v,0,i,8)+ulp32(f(&v,0,i,0))||f(&v,0,i,1)<bounds[1]+f(&v,0,i,8)-ulp32(f(&v,0,i,1))||f(&v,0,i,1)>bounds[3]-f(&v,0,i,8)+ulp32(f(&v,0,i,1))))goto done;
  double im=f(&v,1,i,6),ii=f(&v,1,i,7);if(im>0&&ii>0){double vx=word(meta(&v,G3_FREE_VX(v.cap,i))),vy=word(meta(&v,G3_FREE_VY(v.cap,i))),w=word(meta(&v,G3_FREE_OMEGA(v.cap,i)));result->energy_before+=(vx*vx+vy*vy)/(2*im)+w*w/(2*ii);vx=f(&v,0,i,2);vy=f(&v,0,i,3);w=f(&v,0,i,5);result->energy_after+=(vx*vx+vy*vy)/(2*im)+w*w/(2*ii);}result->objects++;
 }
 for(uint64_t k=0;k<v.C;k++){
  uint32_t *rec=v.c+20*k,a=rec[0],b=rec[1];if(a>=cfg->n||b>=cfg->n+4||a==b)goto done;if(b>=cfg->n)wall_count++;if(impulse(&v,rec,0)>0){if(b<cfg->n)positive_body++;else positive_wall++;}uint32_t sa=slot(&v,a),sb=b<cfg->n?slot(&v,b):NONE-(b-cfg->n);if(b<cfg->n&&sa>=sb)goto done;if(rec[16]!=sa||rec[17]!=gen(&v,sa)||rec[18]!=sb||rec[19]!=(b<cfg->n?gen(&v,sb):0))goto done;if(b<cfg->n&&cfg->n>4096&&(sb-sa>16))goto done;if(bit(v.seen,pair_index(&v,a,b),1))goto done;
  Geometry g=geometry(&v,a,b);double avx=f(&v,0,a,2),avy=f(&v,0,a,3),ao=f(&v,0,a,5),bvx=b<cfg->n?f(&v,0,b,2):0,bvy=b<cfg->n?f(&v,0,b,3):0,bo=b<cfg->n?f(&v,0,b,5):0,ln=impulse(&v,rec,0),lt=impulse(&v,rec,1),q=(avx-bvx)*g.nx+(avy-bvy)*g.ny-g.target,vt=(avx-bvx)*(-g.ny)+(avy-bvy)*g.nx-ao*g.aa-bo*g.ab,scale=max2(.001,max2(fabs(g.target),max2(max2(fabs(avx),fabs(avy)),max2(fabs(bvx),fabs(bvy))))),tol=44*U*scale+8*U*(fabs(ao*g.aa)+fabs(bo*g.ab)),rn=g.kn>0?(q>=0?fmin(q,max2(0,ln)*g.kn):-q):max2(0,-q),rt=g.kt>0?(vt>=0?fmin(vt,max2(0,lt+.25*ln)*g.kt):fmin(-vt,max2(0,.25*ln-lt)*g.kt)):fabs(lt);
  if(!isfinite(ln)||!isfinite(lt)||ln<0||fabs(lt)>.25*ln+2*U*max2(ln,1e-20)||rn>tol||rt>tol){fprintf(stderr,"CPU KKT %llu: %.9g %.9g tolerance %.9g\n",(unsigned long long)k,rn,rt,tol);goto done;}double ratio=max2(rn,rt)/max2(tol,DBL_MIN);if(ratio>result->residual_ratio)result->residual_ratio=ratio;
  if(rec[13]>=128)goto done;v.degree[a]++;if(b<cfg->n){v.degree[b]++;uint32_t ra=root(&v,a),rb=root(&v,b);v.parent[ra>rb?ra:rb]=ra<rb?ra:rb;}result->contacts++;
 }
 for(uint32_t i=0;i<cfg->n;i++)if(v.degree[i])v.sizes[root(&v,i)]++;
 uint64_t runningM=0,runningC=0,runningColors=0;
 for(uint32_t i=0;i<cfg->n;i++){
  uint32_t ri=root(&v,i),degree=v.degree[i];if(meta(&v,G3_PARENT(v.cap,i))!=ri||meta(&v,G3_DEGREE(v.cap,i))!=degree||meta(&v,G3_SIZE(v.cap,i))!=v.sizes[i])goto done;
  if(v.C&&(wide(&v,G3_MEMBER_START(v.cap,i))!=runningM||wide(&v,G3_CONTACT_START(v.cap,i))!=runningC||wide(&v,G3_COLOR_BASE(v.cap,i))!=runningColors))goto done;runningM+=v.sizes[i];runningC+=meta(&v,G3_CONTACT_COUNT(v.cap,i));if(v.sizes[i]){runningColors+=meta(&v,G3_COLORS(v.cap,i))+1;result->islands++;if(v.sizes[i]>result->largest)result->largest=v.sizes[i];}
  uint32_t masks[4]={0},seenDegree=0,k=meta(&v,G3_HEAD(v.cap,i));double change[3]={0},absolute[3]={0};while(k!=NONE){if(k>=v.C||seenDegree++>=degree)goto done;uint32_t *rec=v.c+20ull*k,a=rec[0],b=rec[1],col=rec[13];if(a!=i&&b!=i)goto done;if(masks[col/32]&(1u<<(col%32)))goto done;masks[col/32]|=1u<<(col%32);Geometry g=geometry(&v,a,b);double ln=impulse(&v,rec,0),lt=impulse(&v,rec,1),ix=g.nx*ln-g.ny*lt,iy=g.ny*ln+g.nx*lt,sign=i==a?1:-1,arm=i==a?g.aa:g.ab,dv[3]={sign*ix*f(&v,1,i,6),sign*iy*f(&v,1,i,6),-lt*arm*f(&v,1,i,7)};for(int axis=0;axis<3;axis++){change[axis]+=dv[axis];absolute[axis]+=fabs(dv[axis]);}k=i==a?rec[14]:v.c[G3_NEXT_B((uint64_t)cfg->contacts,k)/4];}if(seenDegree!=degree)goto done;
  for(int axis=0;axis<3;axis++){int field=axis==2?5:axis+2;uint64_t at=axis==0?G3_FREE_VX(v.cap,i):axis==1?G3_FREE_VY(v.cap,i):G3_FREE_OMEGA(v.cap,i);double free=word(meta(&v,at)),end=f(&v,0,i,field),bound=gamma64(32*(degree?degree:1))*(fabs(free)+absolute[axis])+4*U*max2(1e-6,fabs(end));if(fabs(end-free-change[axis])>bound){fprintf(stderr,"CPU impulse reconstruction %u axis %d\n",i,axis);goto done;}}
  if(meta(&v,G3_SOLVER_FLAG(v.cap,i))&1){if(!degree)goto done;result->solver_bodies++;}
 }
 if(runningC!=v.C||runningColors>2*v.C||result->islands!=v.m[6]||result->largest!=v.m[7]||result->solver_bodies!=v.m[8])goto done;
 for(uint32_t r=0;r<cfg->n;r++)if(v.sizes[r]){
  uint64_t ms=wide(&v,G3_MEMBER_START(v.cap,r)),cs=wide(&v,G3_CONTACT_START(v.cap,r)),cb=wide(&v,G3_COLOR_BASE(v.cap,r));uint32_t len=meta(&v,G3_CONTACT_COUNT(v.cap,r)),colors=meta(&v,G3_COLORS(v.cap,r));if(ms+v.sizes[r]>cfg->n||cs+len>v.C||cb+colors+1>2*v.C)goto done;
  for(uint32_t k=0;k<v.sizes[r];k++){uint32_t b=meta(&v,G3_MEMBERS(v.cap,ms+k));if(b>=cfg->n||root(&v,b)!=r||meta(&v,G3_LOCAL(v.cap,b))!=k)goto done;}
  for(uint32_t k=0;k<len;k++){uint32_t ci=v.c[G3_ROOT_CONTACTS((uint64_t)cfg->contacts,cs+k)/4];if(ci>=v.C||root(&v,v.c[20ull*ci])!=r||bit(v.scatter,ci,1))goto done;}
  for(uint32_t col=0;col<colors;col++){uint32_t first=v.c[G3_COLOR_START((uint64_t)cfg->contacts,cb+col)/4],end=v.c[G3_COLOR_START((uint64_t)cfg->contacts,cb+col+1)/4];if(first<cs||end<first||end>cs+len)goto done;for(uint32_t j=first;j<end;j++){uint32_t ci=v.c[G3_COLORED((uint64_t)cfg->contacts,j)/4];if(ci>=v.C||v.c[20ull*ci+13]!=col||root(&v,v.c[20ull*ci])!=r||bit(v.scatter,v.C+ci,1))goto done;}}
  double e0=0,e1=0,p0[3]={0},p1[3]={0},absolute=0,drift=0,drift_bound=0;int positive=1,wall=0,nonpenetrating=1,drift_valid=1;double ox=f(&v,1,r,0),oy=f(&v,1,r,1);
  for(uint32_t k=0;k<v.sizes[r];k++){uint32_t i=meta(&v,G3_MEMBERS(v.cap,ms+k));double im=f(&v,1,i,6),ii=f(&v,1,i,7),vx=word(meta(&v,G3_FREE_VX(v.cap,i))),vy=word(meta(&v,G3_FREE_VY(v.cap,i))),w=word(meta(&v,G3_FREE_OMEGA(v.cap,i))),ex=f(&v,0,i,2),ey=f(&v,0,i,3),ew=f(&v,0,i,5);if(im<=0||ii<=0){positive=0;continue;}e0+=(vx*vx+vy*vy)/(2*im)+w*w/(2*ii);e1+=(ex*ex+ey*ey)/(2*im)+ew*ew/(2*ii);p0[0]+=vx/im;p0[1]+=vy/im;p0[2]+=((f(&v,1,i,0)-ox)*vy-(f(&v,1,i,1)-oy)*vx)/im+w/ii;p1[0]+=ex/im;p1[1]+=ey/im;// Impulses act at trial positions. Drift is a separate float32 operation.
   // Its exact angular change is cross(round(x+v*dt)-x-v*dt,v)/im.
   // Two round-to-nearest operations give half-ULP(product)+half-ULP(sum).
   double sx=f(&v,0,i,0),sy=f(&v,0,i,1),dx=sx-f(&v,1,i,0)-ex*cfg->dt,dy=sy-f(&v,1,i,1)-ey*cfg->dt;
   double bx=.5*(ulp32((float)(ex*cfg->dt))+ulp32((float)sx)),by=.5*(ulp32((float)(ey*cfg->dt))+ulp32((float)sy));
   if(fabs(dx)>bx||fabs(dy)>by)drift_valid=0;
   drift+=(dx*ey-dy*ex)/im;drift_bound+=(bx*fabs(ey)+by*fabs(ex))/im;
   p1[2]+=((f(&v,1,i,0)-ox)*ey-(f(&v,1,i,1)-oy)*ex)/im+ew/ii;absolute+=fabs(ex/im)+fabs(ey/im)+fabs(ew/ii);}
  for(uint32_t k=0;k<len;k++){uint32_t ci=v.c[G3_ROOT_CONTACTS((uint64_t)cfg->contacts,cs+k)/4],*rec=v.c+20ull*ci,a=rec[0],b=rec[1];Geometry g=geometry(&v,a,b);if(b>=cfg->n)wall=1;if(word(rec[12])<0)nonpenetrating=0;double ln=impulse(&v,rec,0),lt=impulse(&v,rec,1),ix=g.nx*ln-g.ny*lt,iy=g.ny*ln+g.nx*lt;absolute+=(fabs(ix)+fabs(iy))*f(&v,1,a,6)+fabs(lt*g.aa*f(&v,1,a,7));if(b<cfg->n)absolute+=(fabs(ix)+fabs(iy))*f(&v,1,b,6)+fabs(lt*g.ab*f(&v,1,b,7));}
  if(positive&&!wall){if(!drift_valid)goto done;if(fabs(drift)>drift_bound+DBL_EPSILON*max2(1.,drift_bound))goto done;
   if(fabs(drift)>result->angular_drift_error)result->angular_drift_error=fabs(drift);
   if(drift_bound>result->angular_rounding_bound)result->angular_rounding_bound=drift_bound;
   double bound=gamma64(32*(len?len:1))*(absolute+1e-8);for(int k=0;k<3;k++){double error=fabs(p1[k]-p0[k]);if(error>bound){fprintf(stderr,"CPU momentum root %u axis %d error %.9g bound %.9g\n",r,k,error,bound);goto done;}if(error>result->momentum_error)result->momentum_error=error;}}
  if(positive&&!wall&&nonpenetrating&&(cfg->flags&2)==0&&e1>e0+gamma64(64*(len?len:1))*max2(1e-20,max2(e0,e1)))goto done;
 }
 if(cfg->fixture>=9){uint32_t stats[3];if(!ph_spatial_diagnostics(p,stats)||stats[0]!=positive_body||stats[1]!=positive_wall||stats[2]!=ph_cell_mode_value(p))goto done;uint64_t occ[8]={0},islands[8]={0},dispatches=0,iter_low=0,iter_high=0;uint32_t maximum=0;qsort(occupancy_keys,cfg->n,8,compare_cell_keys);for(uint64_t first=0;first<cfg->n;){uint64_t end=first+1;while(end<cfg->n&&occupancy_keys[end]==occupancy_keys[first])end++;uint32_t count=(uint32_t)(end-first),bin=0;for(uint32_t k=count;k>1;k>>=1)bin++;occ[bin<7?bin:7]++;if(count>maximum)maximum=count;first=end;}for(uint32_t i=0;i<cfg->n;i++)if(v.sizes[i]){uint32_t bin=0;for(uint32_t k=v.sizes[i];k>1;k>>=1)bin++;islands[bin<7?bin:7]++;}for(uint32_t b=0;b<8;b++){if(occ[b]!=meta(&v,G4_OCCUPANCY_HISTOGRAM_BYTE+4*b)||islands[b]!=meta(&v,G4_ISLAND_HISTOGRAM_BYTE+4*b))goto done;uint64_t count=meta(&v,G4_ITERATION_HISTOGRAM_BYTE+4*b);dispatches+=count;iter_low+=count*(b?1u<<(b-1):0);iter_high+=count*(b==7?cfg->iterations:b?(1u<<b)-1:0);}if(dispatches!=v.m[9]||v.m[10]<iter_low||v.m[10]>iter_high||maximum!=meta(&v,G4_OCCUPANCY_MAX_BYTE)||moving!=meta(&v,G4_MOVING_COUNT_BYTE)||wall_count!=meta(&v,G4_WALL_CONTACTS_BYTE)||meta(&v,G4_SOURCE_GENERATION_BYTE)==0||meta(&v,G4_SOURCE_TICK_BYTE)!=ticks-1)goto done;}
 if(cfg->n>4096&&!certificate(&v,ticks)){fprintf(stderr,"Large fixture certificate failed\n");goto done;}
 for(uint32_t a=0;a<cfg->n;a++){
  uint32_t limit=cfg->n;if(cfg->n>4096){uint32_t size,group;fixture_group(&v,slot(&v,a),&size,&group);(void)group;limit=(slot(&v,a)/size+1)*size;if(limit>v.cap)limit=(uint32_t)v.cap;}
  if(cfg->n<=4096){for(uint32_t b=a+1;b<limit;b++)if(!required(&v,a,b))goto done;}
  else for(uint32_t sb=slot(&v,a)+1;sb<limit;sb++){uint32_t b=dense?dense[sb]:sb;if(b<cfg->n&&!required(&v,a,b))goto done;}
  if(cfg->flags&4)for(uint32_t w=0;w<4;w++)if(!required(&v,a,cfg->n+w))goto done;
 }
 ok=1;
done:if(!ok)fprintf(stderr,"Independent G3 CPU verification failed after objects=%llu contacts=%llu\n",(unsigned long long)result->objects,(unsigned long long)result->contacts);free(occupancy_keys);free(v.s);free(v.t);free(v.m);free(v.c);free(v.args);free(v.parent);free(v.sizes);free(v.degree);free(v.seen);free(v.scatter);return ok;
}
