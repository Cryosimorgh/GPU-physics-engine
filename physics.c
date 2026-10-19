#include "asset_path.h"
#include "physics.h"
#include "physics-layout.h"
#include "execution-layout.h"
#include "pool-layout.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <limits.h>
#include <float.h>
#ifndef G5_MEASURE_TIMESTAMPS
#define G5_MEASURE_TIMESTAMPS 0
#endif
#if G5_MEASURE_TIMESTAMPS
#define G5_TIMESTAMP_COUNT 48
#else
#define G5_TIMESTAMP_COUNT 40
#endif
enum {SCENE=41,GUARDS,CLEAR,PREPARE,ROUND,APPEND,WALLS,ADMIT,GRAPH_CLEAR,UNION,COMPRESS,COUNTS,SCAN,ADD,MEMBERS,SCATTER,ARGS,COLOR,COLOR_COUNTS,COLOR_RANGES,READY,SOLVE,CHECK_CONTACTS,CHECK_BODIES,CHECK_PAIRS,CHECK_GUARDS,PUBLISH,EXEC_CONFIG,RETRY,SCENE_ONE,SOURCE_EPOCH,POOL_POSITIONS};
static const char *names[]={"ph_scene","ph_guards","ph_clear","ph_prepare","ph_round","ph_append","ph_walls","ph_admit_round","ph_graph_clear","ph_union","ph_compress","ph_contact_counts","ph_scan","ph_add","ph_members","ph_contact_scatter","ph_args","ph_color","ph_color_counts","ph_color_ranges","ph_ready","ph_solve","ph_check_contacts","ph_check_bodies","ph_check_pairs","ph_check_guards","ph_publish","ph_execution_config","ph_retry_admission","ph_scene_one","ph_source_epoch","ph_pool_positions"};
typedef struct StateSlot {uint64_t buffer,serial,fence;uint32_t tick,epoch,generation,readers;int pending;} StateSlot;
typedef struct StateLease {PhWorkDependency extra[PH_WORK_EXTRA];uint32_t extra_count,task_status,task_releasing,queue_kind;void *queue;PhStateLease value;void *completion;uint64_t completion_value;} StateLease;
struct Physics {PhWorkInfo producer;StateSlot state[PH_STATE_SLOTS];StateLease leases[PH_STATE_LEASES];uint64_t state_context,state_serial,lease_nonce,state_committed,state_bytes;unsigned state_count;int accepted_slot,pending_slot,state_owner;StorageDevice *d;PhysicsConfig cfg;Spatial *sp;SpatialOutput output;uint64_t h[8],owned[6],bytes[6],commit[6],total;uint32_t k[16],tail,end;double allocation_us;int poisoned,has_tick;uint32_t consumer_owners;uint32_t last_tick,execution_mode,cell_mode,source_epoch,work_budget,quiet_ticks,cached_tick,header[G4_DESCRIPTOR_WORDS];int header_valid;double retry_blocking_us;};
static int last_error;
int ph_error(void){return last_error;}
static int add(uint64_t a,uint64_t b,uint64_t *out){if(a>UINT64_MAX-b)return 0;*out=a+b;return 1;}
static int mul(uint64_t a,uint64_t b,uint64_t *out){if(b&&a>UINT64_MAX/b)return 0;*out=a*b;return 1;}
#include "state-publication.inc"
#include "work-ownership.inc"
#include "physics-failure.inc"
static int bind(Physics *p){return s_bind(p->d,p->h,p->k);}
static int dispatch(Physics *p,int pass,uint32_t count){uint32_t x,y;if(!s_dispatch_shape(count?count:1,1,&x,&y))return 0;p->k[6]=(p->k[6]&65535)|(x<<16);return bind(p)&&s_dispatch_grid(p->d,pass,x,y);}
// Constant 15 is kick_slot during prediction, island_base during these
// disjoint indirect kernels. Restore it before any normal dispatch.
static int indirect(Physics *p,int pass,uint32_t offset){uint32_t saved=p->k[15];int ok=1;if(pass==SOLVE&&p->execution_mode){p->k[15]=0;ok=bind(p)&&s_indirect_count(p->d,pass,p->owned[3],G4_INDIRECT_DISPATCH_BYTE,G4_INDIRECT_COUNT_BYTE);}else if(pass==SOLVE){for(uint32_t chunk=0;chunk<G3_ARGS_CHUNKS(p->cfg.n,p->cfg.flags);chunk++){p->k[15]=chunk*G3_SOLVER_CHUNK_GROUPS;if(!bind(p)||!s_indirect(p->d,pass,p->owned[3],G3_INDIRECT_HEADER_BYTES+G3_INDIRECT_STRIDE_BYTES*chunk)||(p->cfg.fixture!=13&&!s_split(p->d,G3_DISCOVERY_ROUNDS*G3_ARGS_CHUNKS(p->cfg.n,p->cfg.flags)))){ok=0;break;}}}else{p->k[15]=0;ok=bind(p)&&s_indirect(p->d,pass,p->owned[3],offset);}p->k[15]=saved;return ok;}
#if G5_MEASURE_TIMESTAMPS
static int measurement_dispatch(Physics *p,int pass,uint32_t count){uint32_t q=pass==ADMIT?40:pass==MEMBERS?42:pass==SCATTER?44:UINT32_MAX;if((p->k[6]&255u)!=0||q==UINT32_MAX)return dispatch(p,pass,count);return s_stamp(p->d,q)&&dispatch(p,pass,count)&&s_stamp(p->d,q+1);}
static int measurement_indirect(Physics *p,int pass,uint32_t offset){if((p->k[6]&255u)!=0||pass!=COLOR_RANGES)return indirect(p,pass,offset);return s_stamp(p->d,46)&&indirect(p,pass,offset)&&s_stamp(p->d,47);}
#else
#define measurement_dispatch(p,pass,count) dispatch(p,pass,count)
#define measurement_indirect(p,pass,offset) indirect(p,pass,offset)
#endif
static int scan(Physics *p,uint32_t count,uint32_t input,uint32_t output,int input32){uint32_t ns[8],is[8],os[8],depth=0,tail=p->tail,old[16];memcpy(old,p->k,sizeof(old));ns[0]=count;is[0]=input;os[0]=output;while(ns[depth]>256){uint32_t next=(ns[depth]+255)/256;depth++;if(depth>=8)return 0;ns[depth]=next;is[depth]=tail;tail+=8*next;os[depth]=tail;tail+=8*next;}if(tail>p->end)return 0;for(uint32_t j=0;j<=depth;j++){p->k[6]=(old[6]&255)|((j==0&&input32)?256:0);p->k[8]=ns[j];p->k[9]=is[j];p->k[10]=os[j];p->k[11]=j<depth?is[j+1]:UINT32_MAX;if(!dispatch(p,SCAN,ns[j]))return 0;}for(uint32_t j=depth;j-->0;){p->k[8]=ns[j];p->k[10]=os[j];p->k[11]=os[j+1];if(!dispatch(p,ADD,ns[j]))return 0;}memcpy(p->k,old,sizeof(old));return 1;}
int ph_try_close(Physics *p){if(!p)return 1;if(p->consumer_owners)return 0;if(s_device_state(p->d)!=S_CONTEXT_ACTIVE&&(!s_drain(p->d,1000)||!ph_failure_cleanup(p)))return 0;for(unsigned i=0;i<PH_STATE_LEASES;i++)if(p->leases[i].value.nonce){last_error=61;return 0;}for(unsigned i=0;i<p->state_count;i++)if(p->state[i].buffer&&!s_retire(p->d,p->state[i].buffer))return 0;sp_close(p->sp);for(int i=0;i<6;i++)if(p->owned[i]&&!s_retire(p->d,p->owned[i]))abort();s_collect(p->d);if(p->state_owner)s_state_owner_drop(p->d);free(p);return 1;}
void ph_close(Physics *p){(void)ph_try_close(p);}
Physics *ph_open(StorageDevice *d,const uint64_t *base,const PhysicsConfig *cfg){last_error=1;if(!cfg||!cfg->n||cfg->n>cfg->capacity||cfg->capacity>UINT32_MAX/G3_METADATA_STRIDE||cfg->design>1||cfg->fixture>13||(cfg->fixture==13&&cfg->n!=16)||(cfg->flags&~15u)||!isfinite(cfg->dt)||cfg->dt<FLT_MIN||!cfg->iterations||cfg->iterations>16384||!cfg->sleep_frames||!cfg->max_bodies||cfg->max_bodies>65534||!cfg->max_work)return NULL;
 if(G3_DISCOVERY_ROUNDS*G3_ARGS_CHUNKS(cfg->n,cfg->flags)>G3_MAX_STREAM_SPLITS)return NULL;
 Physics *p=calloc(1,sizeof(*p));if(!p)return NULL;p->d=d;p->cfg=*cfg;p->state_owner=s_state_owner_hold(d);if(!p->state_owner)goto fail;p->accepted_slot=p->pending_slot=-1;p->state_context=s_unique_id();if(!p->state_context)goto fail;p->source_epoch=1;uint64_t meta=G3_METADATA_END((uint64_t)cfg->capacity),tmp,total=meta;
 for(uint64_t n=cfg->capacity;n>256;){n=(n+255)/256;if(!mul(n,16,&tmp)||!add(total,tmp,&total))goto fail;}
 if(meta>UINT32_MAX||total>UINT32_MAX)goto fail;p->tail=(uint32_t)meta;p->end=(uint32_t)total;
 if(!mul(cfg->capacity,64,&tmp)||!add(tmp,256,&p->bytes[0])||!add(total,256,&p->bytes[1])||!mul(cfg->contacts,G3_ARENA_STRIDE,&tmp)||!add(tmp,256,&p->bytes[2]))goto fail;if(cfg->fixture==13&&!add(p->bytes[1],POOL_EXTENSION_BYTES,&p->bytes[1]))goto fail;p->bytes[3]=G3_ARGS_END((uint64_t)cfg->n,cfg->flags)+G3_GUARD_BYTES;p->bytes[4]=p->bytes[0];for(int i=1;i<4;i++)if(p->bytes[i]>p->bytes[4])p->bytes[4]=p->bytes[i];p->bytes[5]=cfg->fixture==13?8:0;for(int i=0;i<6;i++){if(i==5&&!p->bytes[i])continue;if(!p->bytes[i]||p->bytes[i]>UINT32_MAX)goto fail;p->commit[i]=s_allocation(d,p->bytes[i],i==4?2:0);if(p->commit[i]==UINT64_MAX||!add(p->total,p->commit[i],&p->total))goto fail;}
 if(!mul(cfg->capacity,76,&p->state_bytes)||!add(p->state_bytes,256,&p->state_bytes)||(cfg->fixture==13&&!add(p->state_bytes,POOL_SNAPSHOT_BYTES,&p->state_bytes))||p->state_bytes>UINT32_MAX)goto fail;
 uint64_t publication_one=s_allocation(d,p->state_bytes,0),publication_total;if(publication_one==UINT64_MAX||!mul(publication_one,2,&publication_total)||!add(p->total,publication_total,&p->total))goto fail;
 last_error=2;if(!s_admit(d,p->total,cfg->budget))goto fail;double start=s_clock();last_error=3;for(int i=0;i<6;i++){if(!p->bytes[i])continue;p->owned[i]=s_new(d,p->bytes[i],i==4?2:0,"G3 transactional physics");if(!p->owned[i])goto fail;}
 p->state_count=2;p->state_committed=publication_total;for(unsigned i=0;i<2;i++){p->state[i].buffer=s_new(d,p->state_bytes,0,"G6 immutable publication");if(!p->state[i].buffer)goto fail;}
 p->sp=sp_open(d,base,cfg->n,cfg->capacity,cfg->design,0,1,cfg->pairs,65536,cfg->budget);if(!p->sp){last_error=10+sp_error();goto fail;}p->output=sp_output(p->sp);sp_physics(p->sp,p->owned[0],p->owned[1],cfg->dt,((cfg->flags&8)?8192:0)|(cfg->fixture>=9?G4_PRECISE_CONTACT_POLICY_FLAG:0));
 p->h[0]=base[0];p->h[1]=p->owned[0];p->h[2]=base[1];p->h[3]=p->output.buffer;p->h[4]=p->owned[1];p->h[5]=p->owned[2];p->h[6]=p->owned[3];p->h[7]=base[8];
 uint32_t dt;memcpy(&dt,&cfg->dt,4);uint32_t k[]={cfg->n,cfg->capacity,cfg->contacts,cfg->pairs,dt,cfg->flags,0,cfg->fixture,p->output.pairs_byte,p->output.contacts_indices_byte,0,cfg->iterations,cfg->sleep_frames,cfg->max_bodies,cfg->max_work,cfg->kick_slot};memcpy(p->k,k,sizeof(k));
 if(cfg->fixture>=12){void *zero=s_map(d,base[8],0);if(!zero)goto fail;memset(zero,0,32);if(!s_unmap(d,base[8],32))goto fail;}
 last_error=4;for(int i=0;i<32;i++){char name[128];snprintf(name,sizeof(name),"%s.dxil",names[i]);FILE *f=bench_asset_open(name);if(!f)goto fail;fseek(f,0,SEEK_END);long len=ftell(f);if(len<=0||len>16*1024*1024){fclose(f);goto fail;}rewind(f);void *data=malloc((size_t)len);if(!data){fclose(f);goto fail;}int ok=fread(data,1,(size_t)len,f)==(size_t)len;fclose(f);ok=ok&&s_load(d,41+i,data,(uint64_t)len);free(data);if(!ok)goto fail;}
 if(!s_indirect_open(d)||!s_begin(d)||!dispatch(p,GUARDS,64)||!s_submit(d,0)||!s_wait(d))goto fail;p->allocation_us=s_clock()-start;return p;
fail:ph_close(p);return NULL;
}
int ph_scene(Physics *p){return ph_state_editable(p)&&s_begin(p->d)&&dispatch(p,SCENE,p->cfg.n)&&s_submit(p->d,0)&&s_wait(p->d)&&state_seed(p);}
int ph_input(Physics *p,const void *data,uint32_t count){if(!ph_state_editable(p)||count!=p->cfg.n||count>4096)return 0;uint64_t bytes=(uint64_t)p->cfg.capacity*64;uint64_t upload=s_new(p->d,bytes,1,"Small oracle fixture upload (SoA)");if(!upload)return 0;uint32_t *dst=s_map(p->d,upload,0);if(!dst){s_retire(p->d,upload);s_collect(p->d);return 0;}memset(dst,0,(size_t)bytes);const uint32_t *src=data;for(uint32_t i=0;i<count;i++)for(int f=0;f<16;f++)dst[(uint64_t)f*p->cfg.capacity+i]=src[16ull*i+f];if(!s_unmap(p->d,upload,bytes)||!s_begin(p->d)||!s_transition(p->d,p->h[0],2)||!s_copy(p->d,p->h[0],upload,bytes)||!s_transition(p->d,p->h[0],0)||!s_submit(p->d,0)||!s_wait(p->d)||!s_retire(p->d,upload))return 0;s_collect(p->d);return state_seed(p);}
static int execution_config(Physics *p){if(!p->execution_mode)return 1;uint32_t a=p->k[8],b=p->k[9];p->k[8]=p->work_budget;p->k[9]=p->execution_mode;int ok=dispatch(p,EXEC_CONFIG,1);p->k[8]=a;p->k[9]=b;return ok;}
int ph_execution(Physics *p,uint32_t mode,uint32_t budget){if(mode>1||s_completed(p->d)<s_fence(p->d)||(mode&&(!budget||budget>G4_MAXIMUM_WORK_BUDGET)))return 0;p->execution_mode=mode;p->work_budget=budget;p->k[5]=(p->k[5]&~G4_GUARDED_FLAG)|(mode?G4_GUARDED_FLAG:0);return 1;}
static int capture_round(Physics *p,uint32_t round,uint64_t readback){if(p->cfg.fixture<9)return 1;uint64_t at=G4_ROUND_HISTORY_BYTE+G4_ROUND_HISTORY_STRIDE*(uint64_t)round;return s_transition(p->d,p->output.buffer,1)&&s_transition(p->d,p->owned[1],1)&&s_copy_offset(p->d,readback,at,p->output.buffer,0,96)&&s_copy_offset(p->d,readback,at+96,p->owned[1],0,8)&&s_transition(p->d,p->output.buffer,0)&&s_transition(p->d,p->owned[1],0);}
// Pool-only GPU status snapshot. Never predicate diagnostics, validation or publication.
// The dedicated 8-byte resource is admitted/accounted and fence-retired with Physics.
static int graph_predicate(Physics *p,int enabled){
 if(!p->owned[5])return 1;
 if(!enabled)return s_predicate_zero(p->d,0,0);
 return s_transition(p->d,p->owned[1],1)&&s_transition(p->d,p->owned[5],2)&&s_copy_offset(p->d,p->owned[5],0,p->owned[1],0,8)&&s_transition(p->d,p->owned[1],0)&&s_transition(p->d,p->owned[5],4)&&s_predicate_zero(p->d,p->owned[5],0);
}
static int record_frame(Physics *p,uint32_t tick,PhysicsResult *r,uint64_t header_target,uint64_t snapshot){if(p->poisoned||tick==UINT32_MAX||(p->has_tick&&tick!=p->last_tick+1))return 0;p->poisoned=1;p->last_tick=tick;p->has_tick=1;double start=s_clock();p->k[10]=tick;p->k[6]=0;uint64_t readback=header_target?header_target:p->owned[4];
 if((!s_recording(p->d)&&!s_begin(p->d))||!s_stamp(p->d,0)||!s_transition(p->d,p->h[0],1)||!s_transition(p->d,p->owned[0],2)||!s_copy(p->d,p->owned[0],p->h[0],64ull*p->cfg.capacity)||!s_transition(p->d,p->h[0],0)||!s_transition(p->d,p->owned[0],0)||!dispatch(p,CLEAR,p->cfg.capacity)||!execution_config(p)||!dispatch(p,PREPARE,p->cfg.n)||!s_stamp(p->d,1))return 0;
 for(uint32_t round=0;round<=8;round++){p->k[6]=round;
  // Round zero always discovers contacts after this tick's prediction/wake-up.
  // Later pool rounds reuse the preceding admission's immutable GPU snapshot:
  // DONE/error is monotonic until next tick's CLEAR. A solver error still takes
  // the existing shader stop path. No CPU decision or extra status copy needed.
  int conditional=round>0&&p->owned[5];
  if((conditional&&!s_predicate_zero(p->d,p->owned[5],0))||!dispatch(p,ROUND,p->cfg.capacity)||!sp_record_physics(p->sp)||(round==0&&p->cfg.fixture>=9&&!sp_g4_occupancy(p->sp)))return 0;
  // CopyBufferRegion is predicated too: always capture every diagnostic slot,
  // including terminated rounds, then restore the same admission snapshot.
  if((conditional&&!graph_predicate(p,0))||!capture_round(p,round,readback)||!s_stamp(p->d,2+3*round)||(conditional&&!s_predicate_zero(p->d,p->owned[5],0))||!dispatch(p,APPEND,p->cfg.pairs)||!dispatch(p,WALLS,p->cfg.n)||!measurement_dispatch(p,ADMIT,1)||(conditional&&!graph_predicate(p,0))||!s_stamp(p->d,30+round))return 0;if(round==8){if(!s_stamp(p->d,27))return 0;break;}
  if(!graph_predicate(p,1)||!dispatch(p,GRAPH_CLEAR,p->cfg.capacity)||!dispatch(p,UNION,p->cfg.contacts)||!dispatch(p,COMPRESS,p->cfg.n)||!dispatch(p,COUNTS,p->cfg.contacts)||!scan(p,p->cfg.n,G3_SIZE(p->cfg.capacity,0),G3_MEMBER_START(p->cfg.capacity,0),1)||!scan(p,p->cfg.n,G3_CONTACT_COUNT(p->cfg.capacity,0),G3_CONTACT_START(p->cfg.capacity,0),1)||!measurement_dispatch(p,MEMBERS,p->cfg.n)||!measurement_dispatch(p,SCATTER,p->cfg.contacts)||!dispatch(p,ARGS,G3_ARGS_CHUNKS(p->cfg.n,p->cfg.flags))||!s_transition(p->d,p->owned[3],4)||!indirect(p,COLOR,0)||!dispatch(p,COLOR_COUNTS,p->cfg.n)||!scan(p,p->cfg.n,G3_COLOR_ELEMENTS(p->cfg.capacity,0),G3_COLOR_BASE(p->cfg.capacity,0),0)||!measurement_indirect(p,COLOR_RANGES,0)||!indirect(p,READY,0)||!s_transition(p->d,p->owned[3],0)||!dispatch(p,ARGS,G3_ARGS_CHUNKS(p->cfg.n,p->cfg.flags))||!s_transition(p->d,p->owned[3],4)||!s_stamp(p->d,3+3*round)||!indirect(p,SOLVE,16)||!s_transition(p->d,p->owned[3],0)||!s_stamp(p->d,4+3*round)||!graph_predicate(p,0))return 0;
 }
 if(!dispatch(p,CHECK_CONTACTS,p->cfg.contacts)||!dispatch(p,CHECK_BODIES,p->cfg.n)||(p->cfg.fixture==13&&!dispatch(p,POOL_POSITIONS,1))||!dispatch(p,CHECK_PAIRS,p->cfg.pairs)||!dispatch(p,CHECK_GUARDS,64)||!s_stamp(p->d,28)||!dispatch(p,PUBLISH,p->cfg.n)||!s_stamp(p->d,29)||!s_transition(p->d,p->owned[1],1)||!s_copy(p->d,readback,p->owned[1],256)||!s_transition(p->d,p->owned[1],0)||!s_transition(p->d,p->output.buffer,1)||!s_copy_offset(p->d,readback,256,p->output.buffer,0,256)||!s_transition(p->d,p->output.buffer,0) )return 0;
 if(snapshot&&(!s_transition(p->d,p->h[0],1)||!s_transition(p->d,p->owned[1],1)||!s_transition(p->d,snapshot,2)||!s_copy_offset(p->d,snapshot,0,p->h[0],0,64ull*p->cfg.capacity)||!s_copy_offset(p->d,snapshot,64ull*p->cfg.capacity,p->owned[1],0,256)||!s_transition(p->d,p->h[0],0)||!s_transition(p->d,p->owned[1],0)||!s_transition(p->d,snapshot,5)))return 0;
 if(!state_record_copy(p,(unsigned)p->pending_slot))return 0;
 if(!s_stamp(p->d,39)||!s_submit(p->d,G5_TIMESTAMP_COUNT))return 0;r->cpu_us=s_clock()-start;r->command_packets=s_packet_count(p->d);s_submission_metrics(p->d,&r->queue_submit_us,&r->queue_submit_calls);r->cpu_record_us=r->cpu_us-r->queue_submit_us;r->execution_mode=p->execution_mode;p->poisoned=0;return 1;
}
int ph_record_frame(Physics *p,uint32_t tick,PhysicsResult *r,uint64_t header,uint64_t snapshot){
 if(!p||!r||p->poisoned||tick==UINT32_MAX||(p->has_tick&&tick!=p->last_tick+1)||!state_prepare(p,tick))return 0;
 if(!producer_prepare(p,tick,header,snapshot)){p->state[p->pending_slot].pending=0;p->pending_slot=-1;last_error=62;return 0;}
 int slot=p->pending_slot;int ok=record_frame(p,tick,r,header,snapshot);
 p->state[slot].fence=s_fence(p->d);p->pending_slot=-1;p->producer.completion_fence=s_fence(p->d);p->producer.status=ok?PH_WORK_SUBMITTED:PH_WORK_FAILED;
 if(!ok){s_abort(p->d);p->state[slot].pending=0;p->poisoned=1;}
 return ok;
}
int ph_decode_frame(Physics *p,uint32_t tick,PhysicsResult *r,const double *q,const uint32_t *header){
 if(!p||!r||!q||!header||!state_complete(p,tick,header))return 0;
 for(int i=0;i<G5_TIMESTAMP_COUNT;i++)r->gpu_us[i]=q[i]-q[0];memset(p->header,0,sizeof(p->header));memcpy(p->header,header,G4_DESCRIPTOR_BASE_BYTES);if(p->cfg.fixture>=9)memcpy((char*)p->header+G4_ROUND_HISTORY_BYTE,(const char*)header+G4_ROUND_HISTORY_BYTE,G4_ROUND_HISTORY_STRIDE*G4_ROUND_HISTORY_COUNT);memcpy(r,header,64);p->cached_tick=tick;p->header_valid=1;r->admission_spent=p->header[G4_SPENT_BYTE/4];r->retry_count=0;r->retry_gpu_us=r->retry_control_us=0;r->allocation_us=p->allocation_us;r->committed=p->total;int clean=s_errors(p->d)==0;return clean;
}
int ph_tick(Physics *p,uint32_t tick,PhysicsResult *r){double start=s_clock();if(!ph_record_frame(p,tick,r,0,0))return 0;double wait=s_clock();if(!s_wait(p->d))return 0;r->blocking_us=s_clock()-wait;double q[64]={0};if(!s_times_count(p->d,q,G5_TIMESTAMP_COUNT))return 0;const uint32_t *h=s_map(p->d,p->owned[4],G4_DESCRIPTOR_BYTES);if(!h)return 0;int ok=ph_decode_frame(p,tick,r,q,h);if(!s_unmap(p->d,p->owned[4],0))return 0;r->api_us=s_clock()-start;return ok;}
uint64_t ph_metadata(Physics *p){return p->owned[1];}
int ph_read(Physics *p,int which,const void **data,uint64_t *bytes){uint64_t source;switch(which){case 0:source=p->h[0];*bytes=64ull*p->cfg.capacity;break;case 1:source=p->owned[0];*bytes=p->bytes[0];break;case 2:source=p->owned[1];*bytes=p->bytes[1];break;case 3:source=p->owned[2];*bytes=p->bytes[2];break;case 4:source=p->owned[3];*bytes=p->bytes[3];break;default:return 0;}if(*bytes>p->bytes[4]||!s_begin(p->d)||!s_transition(p->d,source,1)||!s_copy(p->d,p->owned[4],source,*bytes)||!s_transition(p->d,source,0)||!s_submit(p->d,0)||!s_wait(p->d))return 0;*data=s_map(p->d,p->owned[4],*bytes);return *data!=NULL;}
int ph_unmap(Physics *p){return s_unmap(p->d,p->owned[4],0);}
int ph_ledger(Physics *p,const char *path){FILE *f=fopen(path,"w");if(!f)return 0;fprintf(f,"{\"version\":%u,\"n\":%u,\"capacity\":%u,\"contact_capacity\":%u,\"pair_capacity\":%u,\"scan_base\":%u,\"scan_end\":%u,\"bytes\":[",p->owned[5]?3u:2u,p->cfg.n,p->cfg.capacity,p->cfg.contacts,p->cfg.pairs,p->tail,p->end);for(int i=0;i<(p->owned[5]?6:5);i++)fprintf(f,"%s%llu",i?",":"",(unsigned long long)p->bytes[i]);fprintf(f,"],\"committed\":[");for(int i=0;i<(p->owned[5]?6:5);i++)fprintf(f,"%s%llu",i?",":"",(unsigned long long)p->commit[i]);fprintf(f,"],\"publication_slots\":%u,\"publication_bytes_per_slot\":%llu,\"publication_committed\":%llu,\"total\":%llu,\"frames\":1,\"trial_layout\":\"SoA, exact 16 G1 fields\"}",p->state_count,(unsigned long long)p->state_bytes,(unsigned long long)p->state_committed,(unsigned long long)p->total);int ok=fclose(f)==0;char sub[2048];if(snprintf(sub,sizeof(sub),"%s.spatial.json",path)>=(int)sizeof(sub))return 0;return ok&&sp_ledger(p->sp,sub);}

int ph_inject(Physics *p,int kind){if(kind==3){
 // Deliberate test corruption; this API is never used by normal frame code.
 uint64_t upload=s_new(p->d,4,1,"G4 generation-overflow fault injection");if(!upload)return 0;uint32_t *word=s_map(p->d,upload,0);if(!word){s_retire(p->d,upload);s_collect(p->d);return 0;}*word=UINT32_MAX;
 int ok=s_unmap(p->d,upload,4)&&s_begin(p->d)&&s_transition(p->d,p->owned[1],2)&&s_copy_offset(p->d,p->owned[1],G4_SOURCE_GENERATION_BYTE,upload,0,4)&&s_transition(p->d,p->owned[1],0)&&s_submit(p->d,0)&&s_wait(p->d);
 if(!s_retire(p->d,upload))return 0;s_collect(p->d);p->header_valid=0;return ok;
 }if(kind==1)return sp_inject(p->sp,1);if(kind==2){p->k[5]|=16;return 1;}return 0;}
int ph_fence_test(Physics *p){Memory before,after;if(!s_memory(p->d,&before)||!s_delay(p->d)||!s_begin(p->d)||!dispatch(p,GUARDS,64)||s_split(p->d,0)!=0||s_split(p->d,G3_MAX_STREAM_SPLITS+1)!=0||!s_split(p->d,1)||s_split(p->d,1)!=0||!dispatch(p,GUARDS,64)||!s_transition(p->d,p->owned[0],1)||!s_copy(p->d,p->owned[4],p->owned[0],p->bytes[0])||!s_transition(p->d,p->owned[0],0)||!graph_predicate(p,1)||!graph_predicate(p,0)||!state_fence_test(p)||!s_submit(p->d,0))return 0;uint64_t stale=p->owned[3];for(unsigned i=0;i<p->state_count;i++)if(!s_retire(p->d,p->state[i].buffer))return 0;for(int i=0;i<6;i++)if(p->owned[i]&&!s_retire(p->d,p->owned[i]))return 0;if(s_collect(p->d)!=0||s_retired_bytes(p->d)!=p->total||s_begin(p->d)!=0)return 0;if(!s_unblock(p->d)||!s_wait(p->d)||s_collect(p->d)!=(p->cfg.fixture==13?6:5)+(int)p->state_count||!s_memory(p->d,&after)||before.committed-after.committed!=p->total)return 0;memset(p->owned,0,sizeof(p->owned));memset(p->state,0,sizeof(p->state));p->state_count=0;if(s_transition(p->d,stale,0)!=0)return 0;return 1;}

int ph_spatial_counts(Physics *p,uint64_t *pairs,uint64_t *contacts){if(!s_begin(p->d)||!s_transition(p->d,p->output.buffer,1)||!s_copy(p->d,p->owned[4],p->output.buffer,256)||!s_transition(p->d,p->output.buffer,0)||!s_submit(p->d,0)||!s_wait(p->d))return 0;uint32_t *h=s_map(p->d,p->owned[4],256);if(!h)return 0;*pairs=(uint64_t)h[2]|((uint64_t)h[3]<<32);*contacts=(uint64_t)h[20]|((uint64_t)h[21]<<32);return s_unmap(p->d,p->owned[4],0);}

int ph_indirect_rejection_tests(Physics *p){if(!s_begin(p->d)||!bind(p)||!s_transition(p->d,p->owned[3],4))return 0;if(s_indirect(p->d,SOLVE,p->owned[3],1)||s_indirect(p->d,SOLVE,p->owned[3],UINT64_MAX)||s_indirect(p->d,SOLVE,p->owned[3],p->bytes[3]-4))return 0;return s_transition(p->d,p->owned[3],0)&&s_submit(p->d,0)&&s_wait(p->d);}

int ph_header(Physics *p,uint32_t *out){if(p->header_valid&&p->cached_tick==p->last_tick&&s_completed(p->d)>=s_fence(p->d)){memcpy(out,p->header,256);return 1;}if(!s_begin(p->d)||!s_transition(p->d,p->owned[1],1)||!s_copy(p->d,p->owned[4],p->owned[1],256)||!s_transition(p->d,p->owned[1],0)||!s_submit(p->d,0)||!s_wait(p->d))return 0;const void *h=s_map(p->d,p->owned[4],256);if(!h)return 0;memcpy(out,h,256);return s_unmap(p->d,p->owned[4],0);}
int ph_retry_admission(Physics *p,uint32_t tick){uint32_t header[64];if(!p->has_tick||p->last_tick!=tick||!ph_header(p,header)||header[0]!=G4_ADMISSION_ERROR||header[13]!=0)return 0;if(!s_begin(p->d)||!dispatch(p,RETRY,1)||!s_submit(p->d,0))return 0;double wait=s_clock();if(!s_wait(p->d)||!ph_execution(p,0,0))return 0;p->retry_blocking_us=s_clock()-wait;p->header_valid=0;p->has_tick=tick!=0;p->last_tick=tick?tick-1:0;return 1;}

int ph_tick_auto(Physics *p,uint32_t tick,PhysicsResult *r){double start=s_clock();if(!ph_tick(p,tick,r))return 0;if(r->error_flags==G4_ADMISSION_ERROR&&p->execution_mode){PhysicsResult rejected=*r;double control=s_clock();if(!ph_retry_admission(p,tick))return 0;control=s_clock()-control;double submit;uint32_t calls;s_submission_metrics(p->d,&submit,&calls);if(!ph_tick(p,tick,r))return 0;r->retry_count=1;r->retry_gpu_us=rejected.gpu_us[39];r->retry_control_us=control;r->queue_submit_us+=rejected.queue_submit_us+submit;r->queue_submit_calls+=rejected.queue_submit_calls+calls;r->command_packets+=rejected.command_packets+calls;r->blocking_us+=rejected.blocking_us+p->retry_blocking_us;r->cpu_record_us+=rejected.cpu_record_us+control-submit-p->retry_blocking_us;r->cpu_us=r->cpu_record_us+r->queue_submit_us;p->quiet_ticks=0;}else if(!r->error_flags&&!p->execution_mode){p->quiet_ticks=r->contacts==0?p->quiet_ticks+1:0;if(p->quiet_ticks>=64){if(!ph_execution(p,1,G4_DEFAULT_WORK_BUDGET))return 0;p->quiet_ticks=0;}}r->api_us=s_clock()-start;return 1;}

int ph_descriptor(Physics *p,uint32_t *out){if(!p->header_valid||p->cached_tick!=p->last_tick||s_completed(p->d)==UINT64_MAX||s_completed(p->d)<s_fence(p->d))return 0;memcpy(out,p->header,sizeof(p->header));return 1;}

int ph_view_compatible(Physics *p,const uint64_t *base,uint32_t n,uint32_t cap,uint32_t fixture){return p&&base&&p->cfg.n==n&&p->cfg.capacity==cap&&p->cfg.fixture==fixture&&fixture>=9&&fixture<=13&&p->h[0]==base[0]&&p->h[2]==base[1];}

int ph_cell_mode(Physics *p,uint32_t mode){if(!p||mode>1||p->has_tick||(mode&&p->cfg.fixture<9)||!sp_g4_cell_mode(p->sp,mode))return 0;p->cell_mode=mode;return 1;}
uint32_t ph_cell_mode_value(Physics *p){return p->cell_mode;}

int ph_spatial_diagnostics(Physics *p,uint32_t *out){if(!s_begin(p->d)||!s_transition(p->d,p->output.buffer,1)||!s_copy(p->d,p->owned[4],p->output.buffer,256)||!s_transition(p->d,p->output.buffer,0)||!s_submit(p->d,0)||!s_wait(p->d))return 0;const uint32_t *h=s_map(p->d,p->owned[4],256);if(!h)return 0;out[0]=h[G4_POSITIVE_BODY_CONTACTS_BYTE/4];out[1]=h[G4_POSITIVE_WALL_CONTACTS_BYTE/4];out[2]=h[G4_SPATIAL_CELL_POLICY_BYTE/4];return s_unmap(p->d,p->owned[4],0);}

uint32_t ph_next_tick(Physics *p){return p->has_tick?p->last_tick+1:0;}
uint32_t ph_source_epoch_value(Physics *p){return p->source_epoch;}
int ph_source_epoch_set(Physics *p,uint32_t epoch){
 if(!ph_state_editable(p)||!epoch||epoch<p->source_epoch||s_completed(p->d)<s_fence(p->d))return 0;
 if(epoch==p->source_epoch)return 1;uint32_t h[64];if(!ph_header(p,h)||h[0])return 0;
 uint32_t old=p->k[8];p->k[8]=epoch;int ok=s_begin(p->d)&&dispatch(p,SOURCE_EPOCH,1)&&s_submit(p->d,0)&&s_wait(p->d);p->k[8]=old;
 if(ok){p->source_epoch=epoch;p->header_valid=0;ok=state_seed(p);}return ok;
}
int ph_scene_one(Physics *p,uint32_t dense){
 if(!ph_state_editable(p)||p->cfg.fixture<9||p->cfg.fixture>11||dense>=p->cfg.n||s_completed(p->d)<s_fence(p->d))return 0;
 uint32_t h[64];if(!ph_header(p,h)||h[0])return 0;uint32_t old=p->k[15];p->k[15]=dense;
 int ok=s_begin(p->d)&&dispatch(p,SCENE_ONE,1)&&s_submit(p->d,0)&&s_wait(p->d);p->k[15]=old;return ok&&state_seed(p);
}

int ph_user_command(Physics *p,uint64_t handle){if(p->cfg.fixture<12)return handle==0;if(!handle)return 0;p->h[7]=handle;return 1;}

int ph_pool_material(Physics *p,const float *values){
 if(!ph_state_editable(p)||p->cfg.fixture!=13||p->has_tick||!values)return 0;for(int i=0;i<8;i++)if(!isfinite(values[i])||values[i]<0||values[i]>(i<2?1:20))return 0;
 uint64_t upload=s_new(p->d,32,1,"Pool material initialization");if(!upload)return 0;void *dst=s_map(p->d,upload,0);if(!dst){s_retire(p->d,upload);s_collect(p->d);return 0;}memcpy(dst,values,32);
 int ok=s_unmap(p->d,upload,32)&&s_begin(p->d)&&s_transition(p->d,p->owned[1],2)&&s_copy_offset(p->d,p->owned[1],POOL_DATA(p->end),upload,0,32)&&s_transition(p->d,p->owned[1],0)&&s_submit(p->d,0)&&s_wait(p->d);if(!s_retire(p->d,upload))ok=0;s_collect(p->d);return ok&&state_seed(p);
}
int ph_pool_rolling(Physics *p,const float *values){
 if(!ph_state_editable(p)||p->cfg.fixture!=13||p->has_tick||!values)return 0;for(int i=0;i<32;i++)if(!isfinite(values[i])||fabsf(values[i])>20)return 0;
 uint64_t upload=s_new(p->d,128,1,"Pool rolling oracle initialization");if(!upload)return 0;void *dst=s_map(p->d,upload,0);if(!dst){s_retire(p->d,upload);s_collect(p->d);return 0;}memcpy(dst,values,128);
 int ok=s_unmap(p->d,upload,128)&&s_begin(p->d)&&s_transition(p->d,p->owned[1],2)&&s_copy_offset(p->d,p->owned[1],POOL_ROLL(POOL_DATA(p->end),0,0),upload,0,128)&&s_transition(p->d,p->owned[1],0)&&s_submit(p->d,0)&&s_wait(p->d);if(!s_retire(p->d,upload))ok=0;s_collect(p->d);return ok&&state_seed(p);
}
