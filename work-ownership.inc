// A bounded extension of the existing lease table, not a task scheduler.
static StateLease *work_find(Physics *p,const PhWorkHandle *h){
 if(!p||!h||h->device!=s_identity(p->d)||h->context!=p->state_context||!h->id||s_completed(p->d)==UINT64_MAX)return NULL;
 for(unsigned i=0;i<PH_STATE_LEASES;i++)if(p->leases[i].task_status&&p->leases[i].value.nonce==h->id)return &p->leases[i];return NULL;
}
static int producer_dependency(PhWorkInfo *w,uint64_t h,uint32_t access){
 if(!h)return 1;for(unsigned i=0;i<w->dependency_count;i++)if(w->dependencies[i].buffer==h){w->dependencies[i].access|=access;return 1;}
 if(w->dependency_count==PH_WORK_DEPS)return 0;w->dependencies[w->dependency_count++]=(PhWorkDependency){h,access,0};return 1;
}
static int producer_prepare(Physics *p,uint32_t tick,uint64_t header,uint64_t snapshot){
 PhWorkInfo w={0};w.device=s_identity(p->d);w.owner=p->state_context;w.id=p->state[p->pending_slot].serial;w.publication_serial=w.id;w.tick=tick;w.status=PH_WORK_PREPARED;w.queue_kind=s_producer_queue_kind(p->d);w.ready_fence=s_fence(p->d);
 for(unsigned i=0;i<8;i++)if(!producer_dependency(&w,p->h[i],i==2||i==7?PH_WORK_READ:PH_WORK_READ|PH_WORK_WRITE))return 0;
 for(unsigned i=0;i<6;i++)if(!producer_dependency(&w,p->owned[i],PH_WORK_READ|PH_WORK_WRITE))return 0;
 uint64_t spatial[16];uint32_t count=sp_resources(p->sp,spatial,16);if(!count)return 0;
 for(unsigned i=0;i<count;i++)if(!producer_dependency(&w,spatial[i],PH_WORK_READ|PH_WORK_WRITE))return 0;
 if(!producer_dependency(&w,p->state[p->pending_slot].buffer,PH_WORK_WRITE)||!producer_dependency(&w,header,PH_WORK_WRITE)||!producer_dependency(&w,snapshot,PH_WORK_WRITE))return 0;
 for(unsigned i=0;i<w.dependency_count;i++)if(!s_resource_available(p->d,w.dependencies[i].buffer,w.dependencies[i].access))return 0;
 p->producer=w;return 1;
}
int ph_producer_work(Physics *p,PhWorkInfo *out){if(!p||!out||!p->producer.id)return 0;*out=p->producer;out->completion_ready=out->completion_fence&&s_completed(p->d)!=UINT64_MAX&&s_completed(p->d)>=out->completion_fence;return 1;}
int ph_work_prepare(Physics *p,const PhWorkDependency *extra,uint32_t count,PhWorkHandle *out){
 if(!p||!out||count>PH_WORK_EXTRA||(count&&!extra))return 0;
 // Producer-private and publication resources cannot be borrowed as extras.
 uint64_t spatial[16];uint32_t sn=sp_resources(p->sp,spatial,16);if(!sn)return 0;
 for(unsigned i=0;i<count;i++){
  if(!extra[i].buffer||extra[i].reserved||!extra[i].access||(extra[i].access&~3u))return 0;
  for(unsigned j=0;j<i;j++)if(extra[i].buffer==extra[j].buffer)return 0;
  for(unsigned j=0;j<8;j++)if(extra[i].buffer==p->h[j])return 0;
  for(unsigned j=0;j<6;j++)if(extra[i].buffer==p->owned[j])return 0;
  for(unsigned j=0;j<sn;j++)if(extra[i].buffer==spatial[j])return 0;
  for(unsigned j=0;j<p->state_count;j++)if(extra[i].buffer==p->state[j].buffer)return 0;
 }
 PhStateLease lease;if(!ph_state_acquire(p,&lease))return 0;
 StateLease *task=&p->leases[state_lease_index(p,&lease)];unsigned acquired=0;
 for(;acquired<count;acquired++)if(!s_resource_claim(p->d,extra[acquired].buffer,extra[acquired].access))break;
 if(acquired!=count){while(acquired){acquired--;s_resource_unclaim(p->d,extra[acquired].buffer,extra[acquired].access);}ph_state_release(p,&lease);return 0;}
 task->task_status=PH_WORK_PREPARED;task->extra_count=count;
 if(count)memcpy(task->extra,extra,count*sizeof(*extra));
 *out=(PhWorkHandle){lease.device,lease.context,lease.nonce};return 1;
}
int ph_work_submit(Physics *p,const PhWorkHandle *h,void *queue,void *fence,uint64_t value){
 StateLease *task=work_find(p,h);if(!task||task->task_status!=PH_WORK_PREPARED)return 0;
 void *held=s_queue_retain(p->d,queue,&task->queue_kind);if(!held)return 0;
 if(s_completion_ready(fence,value)||!ph_state_track(p,&task->value,fence,value)){s_queue_release(held);return 0;}
 task->queue=held;task->task_status=PH_WORK_SUBMITTED;return 1;
}
int ph_work_info(Physics *p,const PhWorkHandle *h,PhWorkInfo *out){
 StateLease *task=work_find(p,h);if(!task||!out)return 0;memset(out,0,sizeof(*out));
 out->device=h->device;out->owner=h->context;out->id=h->id;out->publication_serial=task->value.serial;out->generation=task->value.generation;out->tick=task->value.tick;out->ready_fence=task->value.ready_fence;out->status=task->task_status;out->queue_kind=task->queue?task->queue_kind:UINT32_MAX;out->completion_fence=task->completion_value;out->completion_ready=task->completion&&s_completion_ready(task->completion,task->completion_value);
 out->dependencies[0]=(PhWorkDependency){task->value.buffer,PH_WORK_READ,0};out->dependency_count=1+task->extra_count;memcpy(out->dependencies+1,task->extra,task->extra_count*sizeof(*task->extra));return 1;
}
int ph_work_finish(Physics *p,const PhWorkHandle *h,uint32_t *terminal){
 StateLease *task=work_find(p,h);if(!task||!terminal||task->task_status==PH_WORK_PREPARED)return 0;
 if(task->completion&&!s_completion_ready(task->completion,task->completion_value))return 0;
 uint32_t status=task->task_status==PH_WORK_CANCEL_PENDING?PH_WORK_CANCELLED:task->task_status==PH_WORK_FAIL_PENDING?PH_WORK_FAILED:PH_WORK_COMPLETE;
 PhWorkDependency extras[PH_WORK_EXTRA];unsigned count=task->extra_count;memcpy(extras,task->extra,sizeof(extras));PhStateLease lease=task->value;task->task_releasing=1;
 if(!ph_state_release(p,&lease)){task->task_releasing=0;return 0;}
 for(unsigned i=0;i<count;i++)if(!s_resource_unclaim(p->d,extras[i].buffer,extras[i].access))abort();*terminal=status;return 1;
}
int ph_work_cancel(Physics *p,const PhWorkHandle *h){
 StateLease *task=work_find(p,h);if(!task||task->task_status==PH_WORK_FAIL_PENDING)return 0;
 task->task_status=PH_WORK_CANCEL_PENDING;if(task->completion)return 1;uint32_t terminal;return ph_work_finish(p,h,&terminal);
}
int ph_work_fail(Physics *p,const PhWorkHandle *h){
 StateLease *task=work_find(p,h);if(!task)return 0;task->task_status=PH_WORK_FAIL_PENDING;if(task->completion)return 1;uint32_t terminal;return ph_work_finish(p,h,&terminal);
}
