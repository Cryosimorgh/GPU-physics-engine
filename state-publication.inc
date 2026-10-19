// The original source is producer-private. Only these resources may be leased.
static int state_idle(Physics *p){
 if(!p||p->pending_slot>=0)return 0;
 for(unsigned i=0;i<PH_STATE_SLOTS;i++)if(p->state[i].pending)return 0;
 return s_completed(p->d)!=UINT64_MAX&&s_completed(p->d)>=s_fence(p->d);
}
int ph_state_editable(Physics *p){
 if(!state_idle(p)||p->poisoned)return 0;
 for(unsigned i=0;i<PH_STATE_LEASES;i++)if(p->leases[i].value.nonce)return 0;
 return 1;
}
int ph_state_reserve(Physics *p,uint32_t count){
 if(!p||count<2||count>PH_STATE_SLOTS||!state_idle(p))return 0;
 if(count<=p->state_count)return 1;
 uint64_t one=s_allocation(p->d,p->state_bytes,0),extra;
 if(one==UINT64_MAX||!mul(one,count-p->state_count,&extra)||p->total>UINT64_MAX-extra||!s_admit(p->d,extra,p->cfg.budget))return 0;
 unsigned begin=p->state_count,i=begin;
 for(;i<count;i++)if(!(p->state[i].buffer=s_new(p->d,p->state_bytes,0,"G6 immutable publication")))break;
 if(i!=count){for(unsigned j=begin;j<i;j++){s_retire(p->d,p->state[j].buffer);p->state[j].buffer=0;}s_collect(p->d);return 0;}
 p->state_count=count;p->state_committed+=extra;p->total+=extra;return 1;
}
static int state_record_copy(Physics *p,unsigned i){
 uint64_t target=p->state[i].buffer,bytes=64ull*p->cfg.capacity;
 return s_transition(p->d,p->h[0],1)&&s_transition(p->d,p->owned[1],1)&&s_transition(p->d,target,2)&&s_copy_offset(p->d,target,0,p->h[0],0,bytes)&&s_copy_offset(p->d,target,bytes,p->owned[1],0,256)&&s_transition(p->d,p->h[0],0)&&s_transition(p->d,p->h[2],1)&&s_copy_offset(p->d,target,bytes+256,p->h[2],0,12ull*p->cfg.capacity)&&s_transition(p->d,p->h[2],0)&&(p->cfg.fixture!=13||s_copy_offset(p->d,target,bytes+256+12ull*p->cfg.capacity,p->owned[1],POOL_DATA(p->end),160))&&s_transition(p->d,p->owned[1],0)&&s_transition(p->d,target,5);
}
static int state_fence_test(Physics *p){for(unsigned i=0;i<p->state_count;i++)if(!state_record_copy(p,i))return 0;return 1;}
static int state_seed(Physics *p){
 // Initialization/structural edits are drained, with no leases. No tick readback.
 uint32_t h[64];if(!ph_state_editable(p)||!ph_header(p,h)||h[0])return 0;
 if(!ph_state_editable(p)||p->state_serial==UINT64_MAX||!s_begin(p->d)||!state_record_copy(p,0)||!s_submit(p->d,0)||!s_wait(p->d))return 0;
 p->state_serial++;p->accepted_slot=0;
 p->state[0].serial=p->state_serial;p->state[0].fence=s_fence(p->d);
 p->state[0].tick=h[G4_SOURCE_TICK_BYTE/4];p->state[0].epoch=h[G4_SOURCE_EPOCH_BYTE/4];
 p->state[0].generation=h[G4_SOURCE_GENERATION_BYTE/4];
 return 1;
}
static int state_prepare(Physics *p,uint32_t tick){
 if(p->pending_slot>=0||p->state_serial==UINT64_MAX||s_completed(p->d)==UINT64_MAX)return 0;
 for(unsigned i=0;i<p->state_count;i++){
  if((int)i==p->accepted_slot||p->state[i].pending||p->state[i].readers||s_completed(p->d)<p->state[i].fence)continue;
  p->pending_slot=(int)i;p->state[i].pending=1;p->state[i].tick=tick;
  p->state[i].serial=++p->state_serial;p->state[i].epoch=p->source_epoch;return 1;
 }
 last_error=60;return 0; // Bounded backpressure; no tick/state mutation.
}
static int state_complete(Physics *p,uint32_t tick,const uint32_t *h){
 int found=-1;for(unsigned i=0;i<p->state_count;i++)if(p->state[i].pending&&p->state[i].tick==tick){found=(int)i;break;}
 if(found<0||!p->state[found].fence||s_completed(p->d)==UINT64_MAX||s_completed(p->d)<p->state[found].fence)return 0;
 // Rejections never change the accepted pointer. Invalid completion is fail-closed.
 int valid=s_errors(p->d)==0&&(h[0]!=0||(h[13]==p->cfg.n&&h[G4_SOURCE_TICK_BYTE/4]==tick&&h[G4_SOURCE_EPOCH_BYTE/4]==p->state[found].epoch));
 p->state[found].pending=0;if(p->producer.publication_serial==p->state[found].serial){p->producer.status=valid&&!h[0]?PH_WORK_COMPLETE:PH_WORK_FAILED;p->producer.generation=h[G4_SOURCE_GENERATION_BYTE/4];}
 if(!valid){p->poisoned=1;return 0;}
 if(!h[0]){
  if(p->accepted_slot>=0&&p->state[found].serial<=p->state[p->accepted_slot].serial){p->poisoned=1;return 0;}
  p->state[found].generation=h[G4_SOURCE_GENERATION_BYTE/4];p->accepted_slot=found;
 }
 return 1;
}
static int state_lease_index(Physics *p,const PhStateLease *v){
 if(!p||!v||v->device!=s_identity(p->d)||v->context!=p->state_context||!v->nonce||s_completed(p->d)==UINT64_MAX)return -1;
 for(unsigned i=0;i<PH_STATE_LEASES;i++)if(p->leases[i].value.nonce==v->nonce&&!memcmp(v,&p->leases[i].value,sizeof(*v)))return (int)i;
 return -1;
}
int ph_state_acquire(Physics *p,PhStateLease *v){
 if(!p||!v||p->accepted_slot<0||p->lease_nonce==UINT64_MAX||s_completed(p->d)==UINT64_MAX)return 0;
 unsigned slot=(unsigned)p->accepted_slot;
 if(s_completed(p->d)<p->state[slot].fence)return 0;
 for(unsigned i=0;i<PH_STATE_LEASES;i++)if(!p->leases[i].value.nonce){
  PhStateLease a={s_identity(p->d),p->state_context,p->state[slot].serial,++p->lease_nonce,p->state[slot].buffer,p->state[slot].fence,64ull*p->cfg.capacity+256,p->cfg.fixture==13?76ull*p->cfg.capacity+256:0,p->state[slot].generation,p->state[slot].tick,p->state[slot].epoch,p->cfg.n,p->cfg.capacity,slot,p->cfg.fixture==13?160:0,0};
  if(!s_resource_claim(p->d,a.buffer,PH_WORK_READ))return 0;
  p->leases[i].value=a;p->state[slot].readers++;*v=a;return 1;
 }return 0;
}
int ph_state_validate(Physics *p,const PhStateLease *v){return state_lease_index(p,v)>=0;}
int ph_state_track(Physics *p,const PhStateLease *v,void *fence,uint64_t value){
 int i=state_lease_index(p,v);if(i<0||p->leases[i].completion||!value||value==UINT64_MAX)return 0;
 void *retained=s_completion_retain(p->d,fence);if(!retained)return 0;
 p->leases[i].completion=retained;p->leases[i].completion_value=value;return 1;
}
int ph_state_release(Physics *p,const PhStateLease *v){
 int i=state_lease_index(p,v);if(i<0||(p->leases[i].task_status&&!p->leases[i].task_releasing))return 0;
 if(p->leases[i].completion&&!s_completion_ready(p->leases[i].completion,p->leases[i].completion_value))return 0;
 if(!s_resource_unclaim(p->d,v->buffer,PH_WORK_READ))return 0;
 s_queue_release(p->leases[i].queue);s_completion_release(p->leases[i].completion);p->state[v->slot].readers--;memset(&p->leases[i],0,sizeof(p->leases[i]));return 1;
}
int ph_state_stats(Physics *p,PhStateStats *out){
 if(!p||!out)return 0;memset(out,0,sizeof(*out));out->bytes_per_slot=p->state_bytes;out->committed=p->state_committed;out->serial=p->state_serial;out->slots=p->state_count;
 for(unsigned i=0;i<p->state_count;i++)out->pending+=p->state[i].pending;
 for(unsigned i=0;i<PH_STATE_LEASES;i++)out->leases+=p->leases[i].value.nonce!=0;
 if(p->accepted_slot>=0){out->generation=p->state[p->accepted_slot].generation;out->tick=p->state[p->accepted_slot].tick;}return 1;
}
