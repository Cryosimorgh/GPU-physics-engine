#include "asset_path.h"
#include "spatial.h"
#include "execution-layout.h"
#include "spatial-layout.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <limits.h>
enum {FIXTURE=18,CLEAR,KEYS,HASH,HASH_COUNTS,SCAN,ADD,HASH_OFFSETS,HASH_SCATTER,RADIX_LOCAL,RADIX_SCATTER,RANGES,COUNT,ADMIT,EMIT,GUARDS,SYNTHETIC,UNION,COMPRESS,GRAPH_STATS,VALIDATE,POISON,MAPPING};
static const char *names[]={"sp_fixture","sp_clear","sp_keys","sp_hash","sp_hash_counts","sp_scan","sp_add","sp_hash_offsets","sp_hash_scatter","sp_radix_local","sp_radix_scatter","sp_ranges","sp_count","sp_admit","sp_emit","sp_guards","sp_synthetic_counts","sp_union","sp_compress","sp_graph_stats","sp_validate","sp_poison","sp_mapping","sp_g4_occupancy"};
static int last_error;
int sp_error(void){return last_error;}
struct Spatial {StorageDevice *d;uint64_t h[8],reference[8],owned[5],bytes[5],committed[5],total;uint32_t k[16],n,cap,T,G,M,input,output,tail,out,design,fixture,stride,dispatch_extent,fast_static,physics_policy;double allocation_us;};
static int add(uint64_t a,uint64_t b,uint64_t *v){if(a>UINT64_MAX-b)return 0;*v=a+b;return 1;}
static int mul(uint64_t a,uint64_t b,uint64_t *v){if(b&&a>UINT64_MAX/b)return 0;*v=a*b;return 1;}
static int dimension(uint64_t x){return x&&x<=UINT32_MAX;}
void sp_dispatch_extent(Spatial *s,uint32_t count){s->dispatch_extent=count;}
void sp_fast_static(Spatial *s,int enable){s->fast_static=enable?256:0;}
int sp_math_tests(void){uint64_t v;uint32_t x,y;if(s_dispatch_shape(UINT32_MAX,0,&x,&y)||!s_dispatch_shape(0xffff0000u,0,&x,&y)||x!=65535||y!=256||s_dispatch_shape(0xffff0001u,0,&x,&y)||!s_dispatch_shape(UINT32_MAX,1,&x,&y)||x!=65281||y!=257||s_dispatch_shape(0,1,&x,&y))return 0;return !add(UINT64_MAX,1,&v)&&!mul(UINT64_MAX,2,&v)&&mul(UINT32_MAX,UINT32_MAX,&v)&&v==18446744065119617025ull&&!dimension(4294967296ull)&&dimension(UINT32_MAX)&&G2_PAIR_BYTES==20&&G2_SCAN_BASE(32)==2176;}
static int bind(Spatial *s){return s_bind(s->d,s->h,s->k);}
static int dispatch(Spatial *s,int pass,uint32_t n){uint32_t x,y;if(!s_dispatch_shape(n?n:1,s->fast_static!=0,&x,&y))return 0;s->k[5]=(s->k[5]&G2_DISPATCH_STAGE_MASK)|(x<<G2_DISPATCH_WIDTH_SHIFT);return bind(s)&&s_dispatch_grid(s->d,pass,x,y);}
static int scan(Spatial *s,uint32_t count,uint32_t input,uint32_t output){uint32_t ns[8],is[8],os[8],depth=0,tail=s->tail;ns[0]=count;is[0]=input;os[0]=output;
 while(ns[depth]>256){uint32_t next=(ns[depth]+255)/256;depth++;if(depth>=8)return 0;ns[depth]=next;is[depth]=tail;tail+=8*next;os[depth]=tail;tail+=8*next;}
 if(tail>s->out)return 0;
 for(uint32_t j=0;j<=depth;j++){s->k[8]=ns[j];s->k[9]=is[j];s->k[10]=os[j];s->k[11]=j<depth?is[j+1]:UINT32_MAX;if(!dispatch(s,SCAN,ns[j]))return 0;}
 for(uint32_t j=depth;j-->0;){s->k[8]=ns[j];s->k[10]=os[j];s->k[11]=os[j+1];if(!dispatch(s,ADD,ns[j]))return 0;}s->k[10]=output;return 1;}
static int scanContacts(Spatial *s){s->k[5]|=G2_CONTACT_SCAN_FLAG;int ok=scan(s,s->n,G2_CONTACT_COUNT(s->cap,0),G2_CONTACT_OFFSET(s->cap,0));s->k[5]&=~G2_CONTACT_SCAN_FLAG;return ok;}
void sp_close(Spatial *s){if(!s)return;for(int i=0;i<5;i++)if(s->owned[i]&&!s_retire(s->d,s->owned[i]))abort();s_collect(s->d);free(s);}
Spatial *sp_open(StorageDevice *d,const uint64_t *base,uint32_t n,uint32_t cap,uint32_t design,uint32_t fixture,uint32_t stride,uint32_t pairs,uint32_t visits,uint64_t budget){
 last_error=1;if(!n||n>cap||design>1||!visits||cap>UINT32_MAX/64)return NULL;
 if(!s_spatial_features(d)){last_error=5;return NULL;}
 Spatial *s=calloc(1,sizeof(*s));if(!s)return NULL;s->d=d;s->n=n;s->cap=cap;s->design=design;s->fixture=fixture;s->stride=stride;s->G=(n+255)/256;s->T=1;while(s->T<(uint64_t)n*2){if(s->T>UINT32_MAX/2)goto fail;s->T*=2;}
 s->M=design?s->T:16*s->G;if(s->M<n)s->M=n;
 uint64_t input,output,tail,out,b,tmp;if(!mul(cap,G2_COUNT_BYTES+G2_OFFSET_BYTES+G2_COVERAGE_BYTES_PER_ENTITY+G2_GRAPH_BYTES_PER_ENTITY+G2_CONTACT_COUNT_BYTES+G2_CONTACT_OFFSET_BYTES,&input)||!add(input,G2_HEADER_BYTES,&input)||!mul(s->M,8,&tmp)||!add(input,tmp,&output)||!add(output,tmp,&tail))goto fail;out=tail;for(uint64_t k=s->M;k>256;){k=(k+255)/256;if(!mul(k,16,&tmp)||!add(out,tmp,&out))goto fail;}
 if(!dimension(out)||!mul(pairs,G2_PAIR_BYTES+G2_CONTACT_INDEX_BYTES,&b)||!add(out,b,&b)||!add(b,256,&b)||!dimension(b))goto fail;
 s->input=(uint32_t)input;s->output=(uint32_t)output;s->tail=(uint32_t)tail;s->out=(uint32_t)out;
 if(!mul(cap,G2_KEY_BYTES,&tmp)||!add(tmp,G2_GUARD_BYTES,&s->bytes[0])||!mul(design?s->T:cap,design?G2_HASH_SLOT_BYTES:4,&tmp)||!add(tmp,G2_GUARD_BYTES,&s->bytes[1])||!mul(cap,4,&tmp)||!add(tmp,G2_GUARD_BYTES,&s->bytes[2]))goto fail;s->bytes[3]=b;s->bytes[4]=b;
 for(int i=0;i<4;i++)if(s->bytes[i]>s->bytes[4])s->bytes[4]=s->bytes[i];
 for(int i=0;i<5;i++){if(!dimension(s->bytes[i]))goto fail;s->committed[i]=s_allocation(d,s->bytes[i],i==4?2:0);if(s->committed[i]==UINT64_MAX||!add(s->total,s->committed[i],&s->total))goto fail;}
 if(!s_admit(d,s->total,budget)){last_error=2;goto fail;}
 last_error=3;double start=s_clock();for(int i=0;i<5;i++){s->owned[i]=s_new(d,s->bytes[i],i==4?2:0,"G2 spatial owner");if(!s->owned[i])goto fail;}s->allocation_us=s_clock()-start;last_error=4;
 for(int i=0;i<3;i++)s->h[i]=base[i];for(int i=0;i<4;i++)s->h[i+3]=s->owned[i];s->h[7]=base[8];
 for(int i=0;i<7;i++)s->reference[i]=base[i];s->reference[7]=base[8];
 uint32_t k[]={n,cap,design,stride,fixture,0,s->T,s->G,0,0,0,0,pairs,s->out,s->input,visits};memcpy(s->k,k,sizeof(k));
 for(int i=0;i<24;i++){char path[128];snprintf(path,sizeof(path),"%s.dxil",names[i]);FILE *f=bench_asset_open(path);if(!f)goto fail;fseek(f,0,SEEK_END);long len=ftell(f);if(len<=0||len>16*1024*1024){fclose(f);goto fail;}rewind(f);void *p=malloc(len);if(!p){fclose(f);goto fail;}int ok=fread(p,1,len,f)==(size_t)len;fclose(f);ok=ok&&s_load(d,i==23?79:18+i,p,len);free(p);if(!ok)goto fail;}
 if(!s_begin(d))goto fail;s->k[8]=(uint32_t)s->bytes[0]-256;s->k[9]=(uint32_t)s->bytes[1]-256;s->k[10]=(uint32_t)s->bytes[2]-256;s->k[11]=(uint32_t)s->bytes[3]-256;
 if(!dispatch(s,GUARDS,64)||!s_submit(d,0)||!s_wait(d))abort();return s;
fail:sp_close(s);return NULL;
}
int sp_fixture(Spatial *s){return s_begin(s->d)&&dispatch(s,FIXTURE,s->n)&&s_submit(s->d,0)&&s_wait(s->d);}
SpatialOutput sp_output(Spatial *s){return (SpatialOutput){s->owned[3],8,0,16,s->out,G2_PAIR_BYTES,s->k[12],G2_CONTACT_TOTAL_BYTE,s->out+G2_PAIR_BYTES*s->k[12],G2_CONTACT_INDEX_BYTES};}
void sp_physics(Spatial *s,uint64_t trial,uint64_t control,float dt,uint32_t policy){s->physics_policy=policy;s->h[0]=trial;s->h[2]=control;memcpy(&s->k[4],&dt,4);}
int sp_record_physics(Spatial *s){s->k[5]=256|2048|s->physics_policy;
 if(!dispatch(s,CLEAR,s->design?s->T:s->cap)||!dispatch(s,KEYS,s->n))return 0;
 if(s->design){s->k[9]=s->input;if(!dispatch(s,HASH,s->n)||!dispatch(s,HASH_COUNTS,s->T)||!scan(s,s->T,s->input,s->output)||!dispatch(s,HASH_OFFSETS,s->T)||!dispatch(s,HASH_SCATTER,s->n))return 0;}
 else for(uint32_t bit=0;bit<64;bit+=4){s->k[5]=bit|2048|s->physics_policy;s->k[9]=s->input;if(!dispatch(s,RADIX_LOCAL,s->n)||!scan(s,16*s->G,s->input,s->output)||!dispatch(s,RADIX_SCATTER,s->n))return 0;}
 s->k[5]=256|2048|s->physics_policy;if(!s->design&&!dispatch(s,RANGES,s->n))return 0;
 return dispatch(s,COUNT,s->n)&&scan(s,s->n,G2_COUNT(0),G2_OFFSET(s->cap,0))&&scanContacts(s)&&dispatch(s,ADMIT,1)&&dispatch(s,EMIT,s->n)&&dispatch(s,VALIDATE,s->n);
}
int sp_inject(Spatial *s,int guard){s->k[5]=guard?1:0;return s_begin(s->d)&&dispatch(s,POISON,1)&&s_submit(s->d,0)&&s_wait(s->d);}
int sp_fence_test(Spatial *s){Memory before,after;if(!s_memory(s->d,&before)||!s_delay(s->d)||!s_begin(s->d)||!dispatch(s,CLEAR,256)||!s_transition(s->d,s->owned[0],1)||!s_copy(s->d,s->owned[4],s->owned[0],s->bytes[0])||!s_transition(s->d,s->owned[0],0)||!s_submit(s->d,0))return 0;for(int i=0;i<5;i++)if(!s_retire(s->d,s->owned[i]))return 0;if(s_collect(s->d)!=0||s_retired_bytes(s->d)!=s->total||s_begin(s->d)!=0)return 0;if(!s_unblock(s->d)||!s_wait(s->d)||s_collect(s->d)!=5||!s_memory(s->d,&after)||before.committed-after.committed!=s->total)return 0;memset(s->owned,0,sizeof(s->owned));return 1;}
static int run(Spatial *s,SpatialResult *r,int zero_reference){double start=s_clock();s->k[5]=s->fast_static|(zero_reference?512:0);if(!s_begin(s->d)||!s_stamp(s->d,0))return 0;
 if(zero_reference){uint32_t k[16]={s->n,s->cap,1,s->stride,1};if(!s_bind(s->d,s->reference,k)||!s_dispatch(s->d,17,s->cap)||!s_dispatch(s->d,5,s->n)||!s_transition(s->d,s->reference[4],3))return 0;s->h[7]=s->reference[4];}
 if(!dispatch(s,CLEAR,s->design?s->T:s->cap)||!s_stamp(s->d,1)||!dispatch(s,KEYS,s->dispatch_extent?s->dispatch_extent:s->n)||!s_stamp(s->d,2))return 0;
 if(s->design){if(!dispatch(s,HASH,s->n)||!s_stamp(s->d,3))return 0;s->k[9]=s->input;if(!dispatch(s,HASH_COUNTS,s->T)||!scan(s,s->T,s->input,s->output)||!dispatch(s,HASH_OFFSETS,s->T)||!dispatch(s,HASH_SCATTER,s->n))return 0;}
 else {for(uint32_t bit=0;bit<64;bit+=4){s->k[5]=bit;s->k[9]=s->input;if(!dispatch(s,RADIX_LOCAL,s->n)||!scan(s,16*s->G,s->input,s->output)||!dispatch(s,RADIX_SCATTER,s->n))return 0;}if(!s_stamp(s->d,3)||!dispatch(s,RANGES,s->n))return 0;}
 s->k[5]=s->fast_static|(zero_reference?512:0);if(!s_stamp(s->d,4)||!dispatch(s,COUNT,s->n)||!s_stamp(s->d,5)||!scan(s,s->n,G2_COUNT(0),G2_OFFSET(s->cap,0))||!scanContacts(s)||!dispatch(s,ADMIT,1)||!s_stamp(s->d,6)||!dispatch(s,EMIT,s->n)||!s_stamp(s->d,7)||!dispatch(s,UNION,s->k[12])||!s_stamp(s->d,8)||!dispatch(s,COMPRESS,s->cap)||!s_stamp(s->d,9)||!dispatch(s,GRAPH_STATS,s->cap)||!s_stamp(s->d,10)||!dispatch(s,VALIDATE,s->n))return 0;if(zero_reference){if(!s_transition(s->d,s->reference[4],0))return 0;s->h[7]=s->reference[7];}if(!s_stamp(s->d,11)||!s_submit(s->d,12))return 0;
 r->cpu_us=s_clock()-start;if(!s_wait(s->d))return 0;double times[32];if(!s_times(s->d,times))return 0;for(int i=0;i<11;i++)r->stages[i]=times[i+1]-times[i];r->stages[11]=times[11]-times[0];r->allocation_us=s->allocation_us;return s_errors(s->d)==0;
}
int sp_run(Spatial *s,SpatialResult *r){return run(s,r,0);}
// Frozen IDX-04 control: driver independently verifies zero velocities before
// invoking the existing G1 integrator. Production spatial entry is read-only.
int sp_run_zero_reference(Spatial *s,SpatialResult *r){return run(s,r,1);}
static void *readBuffer(Spatial *s,int which){uint64_t bytes=s->bytes[which];if(!s_begin(s->d)||!s_transition(s->d,s->owned[which],1)||!s_copy(s->d,s->owned[4],s->owned[which],bytes)||!s_transition(s->d,s->owned[which],0)||!s_submit(s->d,0)||!s_wait(s->d))return NULL;return s_map(s->d,s->owned[4],bytes);}
static int unmap(Spatial *s){return s_unmap(s->d,s->owned[4],0);}
int sp_mapping_test(Spatial *s){if(!s_begin(s->d)||!bind(s)||s_dispatch(s->d,KEYS,UINT32_MAX)!=0||!dispatch(s,MAPPING,6)||!s_submit(s->d,0)||!s_wait(s->d))return 0;uint32_t *p=readBuffer(s,3);if(!p)return 0;uint32_t x[]={65534,65534,65280,32767,0,0},y[]={0,256,256,511,512,0},width[]={65535,65535,65281,32768,32768,1},lane[]={255,255,255,254,0,0};for(int i=0;i<6;i++){uint64_t value=((uint64_t)x[i]+(uint64_t)width[i]*y[i])*256+lane[i];uint32_t index=value>UINT32_MAX?UINT32_MAX:(uint32_t)value;if(p[20+4*i]!=index||p[21+4*i]!=(uint32_t)value||p[22+4*i]!=(uint32_t)(value>>32)||p[23+4*i]!=0x1deac0deu)return 0;}return unmap(s);}
int sp_scan_test(Spatial *s){if(!s_begin(s->d)||!dispatch(s,CLEAR,s->cap)||!dispatch(s,SYNTHETIC,s->n)||!scan(s,s->n,G2_COUNT(0),G2_OFFSET(s->cap,0))||!scanContacts(s)||!dispatch(s,ADMIT,1)||!s_submit(s->d,0)||!s_wait(s->d))return 0;uint32_t *p=readBuffer(s,3);if(!p)return 0;uint64_t total,contacts;memcpy(&total,p+2,8);memcpy(&contacts,(char*)p+G2_CONTACT_TOTAL_BYTE,8);uint64_t want=(uint64_t)s->n*UINT32_MAX+(uint64_t)s->n*(s->n-1)/2;if(total!=want||contacts!=want-s->n||p[0]!=256||p[4]!=0)return 0;for(uint32_t i=0;i<s->n;i++){uint64_t value,cv;memcpy(&value,(char*)p+G2_OFFSET((uint64_t)s->cap,i),8);memcpy(&cv,(char*)p+G2_CONTACT_OFFSET((uint64_t)s->cap,i),8);if(value!=(uint64_t)i*UINT32_MAX+(uint64_t)i*(i-1)/2||cv!=value-i)return 0;}return unmap(s);}
typedef struct Body {double x,y,vx,vy,r;} Body;
static Body body(uint32_t id,uint32_t fixture){uint32_t size=fixture==0?1:fixture==1?2:fixture==2?8:((id/1024)%16==0?16:2);uint32_t group=fixture==3?(id/1024)*512+(id%1024)/size:id/size,local=id%size;Body b={(double)(group%16384)*16-131072,(double)(group/16384)*16-8192,0,0,.5};if(!fixture)b.x+=.5;else b.x+=local*.125;
 if(fixture==4)b=(Body){(id%32)*.75-12,(id/32)*.75-12,((int)(id%7)-3)*2,((int)(id%5)-2)*2,.25};
 if(fixture==5)b=(Body){id%2==0?-8:8,(id/2)*16.,id%2==0?16:-16,0,.25};
 if(fixture==6){uint32_t row=id/2;b=(Body){(row%3==0?-4.5:(row%3==1?3.5:-.5))+(id%2),row*16.,0,0,.5};}
 if(fixture==7)b=(Body){id%2==0?-8589934080.:8589934080.,(id/2)*16.,0,0,512};
 if(fixture==8)b=(Body){0,0,0,0,.5};if(fixture==9)b.x=NAN;if(fixture==10)b=(Body){0,id*16.,1e9,0,.5};
 if(fixture==11)b=(Body){id%2==0?-8589934080.:8589934080.,(id/2)*16.,0,0,.5};if(fixture==12)b.x=1e20;if(fixture==13)b.r=-1;if(fixture==14)b.vx=INFINITY;if(fixture==15)b=(Body){-4,(id/2)*16.,0,0,0};
 if(fixture>=16){uint32_t distribution=fixture%16,level=fixture/16-1;size=distribution==2?8:(distribution==3&&((id/1024)%16==0)?16:2);group=distribution==3?(id/1024)*512+(id%1024)/size:id/size;local=id%size;int hot=level==3||(level==1&&group%100==0)||(level==2&&group%10==0);double spacing=distribution==0?128:32;b.x=(group%16384)*spacing-131072+local*(hot?.125:1.5);b.y=(group/16384)*spacing-8192;}
 return b;}
static int eligible(Body a,Body b,int *contact){double dx=a.x-b.x,dy=a.y-b.y,vx=a.vx-b.vx,vy=a.vy-b.vy,r=a.r+b.r;if(a.vx==0&&a.vy==0&&b.vx==0&&b.vy==0){*contact=dx*dx+dy*dy<=r*r;return fabs(dx)<=r&&fabs(dy)<=r;}double vv=vx*vx+vy*vy,t=vv?fmin(1,fmax(0,-(dx*vx+dy*vy)/vv)):0;*contact=(dx+t*vx)*(dx+t*vx)+(dy+t*vy)*(dy+t*vy)<=r*r;return fmin(a.x,a.x+a.vx)-a.r<=fmax(b.x,b.x+b.vx)+b.r&&fmin(b.x,b.x+b.vx)-b.r<=fmax(a.x,a.x+a.vx)+a.r&&fmin(a.y,a.y+a.vy)-a.r<=fmax(b.y,b.y+b.vy)+b.r&&fmin(b.y,b.y+b.vy)-b.r<=fmax(a.y,a.y+a.vy)+a.r;}
static int on(Spatial *s,uint32_t id){return s->stride&&id%s->stride==0;}
static uint32_t cpuRoot(uint32_t *parent,uint32_t i){while(parent[i]!=i){parent[i]=parent[parent[i]];i=parent[i];}return i;}
int sp_state(Spatial *s,const uint32_t *words,const uint32_t *slots){for(uint32_t i=0;i<s->n;i++){Body b=body(slots[i],s->fixture);float values[5]={(float)b.x,(float)b.y,(float)b.vx,(float)b.vy,(float)b.r};int fields[]={0,1,2,3,8};for(int j=0;j<5;j++){uint32_t v;memcpy(&v,&values[j],4);if(words[(uint64_t)fields[j]*s->cap+i]!=v)return 0;}if(words[15ull*s->cap+i]!=slots[i])return 0;}return 1;}
int sp_verify(Spatial *s,SpatialResult *r,const uint32_t *slots,const uint32_t *gens,const uint32_t *dense){
 uint32_t *p=readBuffer(s,3);if(!p)return 0;if(p[12]!=G2_TAG||p[13]!=G2_COUNT(s->n-1)||p[14]!=G2_OFFSET(s->cap,s->n-1)||p[15]!=G2_COVERAGE(s->cap,3,s->n-1)||p[16]!=G2_SCAN_BASE(s->cap)||p[22]!=G2_CONTACT_COUNT(s->cap,s->n-1)||p[23]!=G2_CONTACT_OFFSET(s->cap,s->n-1)||p[24]!=s->out+G2_PAIR_BYTES*s->k[12])return 0;if(p[0]!=p[G2_STICKY_ERROR_BYTE/4])return 0;r->status=p[0];memcpy(&r->pairs,p+2,8);memcpy(&r->contacts,(char*)p+G2_CONTACT_TOTAL_BYTE,8);r->islands=p[7];r->largest=p[9];r->participants=p[18];r->committed=s->total;for(int i=0;i<5;i++)r->logical+=s->bytes[i];Memory mem;s_memory(s->d,&mem);r->peak=mem.peak_committed;
 uint32_t guard=(uint32_t)(s->bytes[3]/4)-64;for(int i=0;i<64;i++){if(p[guard+i]!=0xbaadc0deu)return 0;r->guards++;}
 for(uint32_t i=0;i<s->n;i++){if(p[G2_COVERAGE((uint64_t)s->cap,0,i)/4]!=1)return 0;r->verified_objects++;r->active+=on(s,slots[i]);}
 if(r->status){if(p[4]!=0)return 0;return unmap(s);}
 if(r->pairs>s->k[12]||r->contacts>r->pairs)return 0;
 for(uint32_t k=1;k<4;k++)for(uint32_t i=0;i<s->n;i++)if(p[G2_COVERAGE((uint64_t)s->cap,k,i)/4]!=1)return 0;
 uint64_t expected=0,contacts=0;int small=s->n<=4096;uint64_t bits=(uint64_t)s->cap*(small?s->cap:16),bytes=(bits+7)/8;unsigned char *seen=calloc(1,(size_t)bytes);if(!seen)return 0;Body *bodies=calloc(s->cap,sizeof(Body));if(!bodies){free(seen);return 0;}for(uint32_t i=0;i<s->n;i++)bodies[slots[i]]=body(slots[i],s->fixture);uint32_t *parents=malloc(4ull*s->cap),*sizes=calloc(s->cap,4);unsigned char *used=calloc(s->cap,1);if(!parents||!sizes||!used)return 0;for(uint32_t i=0;i<s->cap;i++)parents[i]=i;
 for(uint64_t k=0;k<r->pairs;k++){uint32_t *v=(uint32_t*)((char*)p+s->out+G2_PAIR_BYTES*k);uint32_t a=v[0],b=v[2];int contact=0;if(a>=s->cap||b>=s->cap||a>=b||dense[a]>=s->n||dense[b]>=s->n||v[1]!=gens[a]||v[3]!=gens[b]||(!on(s,a)&&!on(s,b))||!eligible(bodies[a],bodies[b],&contact)||v[4]!=(uint32_t)contact){fprintf(stderr,"bad pair %llu: %u %u\n",(unsigned long long)k,a,b);free(bodies);free(seen);return 0;}uint64_t bit;if(small)bit=(uint64_t)a*s->cap+b;else{if(b-a>16){free(bodies);free(seen);return 0;}bit=(uint64_t)a*16+b-a-1;}if(seen[bit/8]&(1u<<(bit%8))){free(bodies);free(seen);return 0;}seen[bit/8]|=1u<<(bit%8);r->verified_pairs++;}
 unsigned char *contact_seen=r->contacts?calloc(1,(size_t)((r->pairs+7)/8)):NULL;if(r->contacts&&!contact_seen)return 0;
 for(uint64_t ci=0;ci<r->contacts;ci++){uint32_t index;memcpy(&index,(char*)p+s->out+G2_PAIR_BYTES*(uint64_t)s->k[12]+G2_CONTACT_INDEX_BYTES*ci,4);if(index>=r->pairs||*(uint32_t*)((char*)p+s->out+G2_PAIR_BYTES*(uint64_t)index+16)!=1||(contact_seen[index/8]&(1u<<(index%8))))return 0;contact_seen[index/8]|=1u<<(index%8);r->verified_contacts++;}free(contact_seen);
 // Independent enumeration: exhaustive for small scenes; disjoint geometric
 // groups for large fixtures, with exact per-pair membership (not sampling).
 for(uint32_t i=0;i<s->n;i++){uint32_t a=slots[i],distribution=s->fixture%16;uint32_t size=s->fixture==0?1:(s->fixture==2||distribution==2?8:(distribution==3&&(a/1024)%16==0?16:2));uint32_t end=(a/size+1)*size,limit=small?s->cap:(end<s->cap?end:s->cap);for(uint32_t b=a+1;b<limit;b++){if(dense[b]>=s->n||(!on(s,a)&&!on(s,b)))continue;int contact;if(!eligible(bodies[a],bodies[b],&contact))continue;expected++;contacts+=contact;if(contact){used[a]=used[b]=1;uint32_t ra=cpuRoot(parents,a),rb=cpuRoot(parents,b);parents[ra>rb?ra:rb]=ra<rb?ra:rb;}uint64_t bit=small?(uint64_t)a*s->cap+b:(uint64_t)a*16+b-a-1;if(!(seen[bit/8]&(1u<<(bit%8)))){free(bodies);free(seen);return 0;}}}
 uint32_t islands=0,largest=0,participants=0;for(uint32_t i=0;i<s->cap;i++)if(used[i]){uint32_t root=cpuRoot(parents,i);sizes[root]++;participants++;if(p[G2_PARENT((uint64_t)s->cap,i)/4]!=root)return 0;}
 for(uint32_t i=0;i<s->cap;i++){if(sizes[i]){islands++;if(sizes[i]>largest)largest=sizes[i];}if(p[G2_SIZE((uint64_t)s->cap,i)/4]!=sizes[i]||p[G2_DEGREE((uint64_t)s->cap,i)/4]!=used[i])return 0;}
 free(parents);free(sizes);free(used);free(bodies);free(seen);if(expected!=r->pairs||contacts!=r->contacts||islands!=r->islands||largest!=r->largest||participants!=r->participants){fprintf(stderr,"oracle counts P=%llu C=%llu I=%u L=%u participants=%u; GPU P=%llu C=%llu I=%u L=%u participants=%u\n",(unsigned long long)expected,(unsigned long long)contacts,islands,largest,participants,(unsigned long long)r->pairs,(unsigned long long)r->contacts,r->islands,r->largest,r->participants);return 0;}if(!unmap(s))return 0;
 for(int k=0;k<3;k++){p=readBuffer(s,k);if(!p)return 0;guard=(uint32_t)(s->bytes[k]/4)-64;for(int j=0;j<64;j++){if(p[guard+j]!=0xbaadc0deu)return 0;r->guards++;}if(k==0)for(uint32_t i=0;i<s->n;i++){Body b=body(slots[i],s->fixture);int32_t x=(int32_t)floor(b.x/4),y=(int32_t)floor(b.y/4);if((int32_t)p[4*i]!=x||(int32_t)p[4*i+1]!=y)return 0;}if(!unmap(s))return 0;}
 return s_errors(s->d)==0;
}
int sp_ledger(Spatial *s,const char *path){FILE *f=fopen(path,"w");if(!f)return 0;fprintf(f,"{\"n\":%u,\"capacity\":%u,\"table_slots\":%u,\"scan_elements\":%u,\"output_byte\":%u,\"contact_indices_byte\":%u,\"pair_capacity\":%u,\"logical\":[",s->n,s->cap,s->design?s->T:0,s->M,s->out,s->out+G2_PAIR_BYTES*s->k[12],s->k[12]);for(int i=0;i<5;i++)fprintf(f,"%s%llu",i?",":"",(unsigned long long)s->bytes[i]);fprintf(f,"],\"committed\":[");for(int i=0;i<5;i++)fprintf(f,"%s%llu",i?",":"",(unsigned long long)s->committed[i]);fprintf(f,"],\"total\":%llu,\"frames\":1,\"growth_overlap\":0,\"cell_edge\":%.2f,\"g4_cell_mode\":%u}",(unsigned long long)s->total,(s->physics_policy&G4_FINE_CELL_FLAG)?.25:4.0,(s->physics_policy&G4_FINE_CELL_FLAG)?1u:0u);return fclose(f)==0;}

int sp_g4_occupancy(Spatial *s){return dispatch(s,79,s->design?s->T:s->n);}

int sp_g4_cell_mode(Spatial *s,uint32_t mode){if(mode>1||s_completed(s->d)<s_fence(s->d))return 0;s->physics_policy=(s->physics_policy&~G4_FINE_CELL_FLAG)|(mode?G4_FINE_CELL_FLAG:0);return 1;}
