// Real queues/resources; only explicitly labeled failure HRESULTs are injected.
static PhWorkHandle device_test_old_task;
static PhStateLease device_test_old_lease;
static int device_test_gate(Viewer *v,ID3D12Fence **gate,int compute,int graphics){
 RCHECK(SUCCEEDED(ID3D12Device_CreateFence(v->d->g.device,0,0,&IID_ID3D12Fence,(void**)gate)));
 if(compute)RCHECK(SUCCEEDED(ID3D12CommandQueue_Wait(v->d->g.queue,*gate,1)));
 if(graphics)RCHECK(SUCCEEDED(ID3D12CommandQueue_Wait(v->graphics_queue,*gate,1)));return 1;
}
int viewer_device_test(StorageDevice *d,const uint64_t *base,uint32_t test,const char *path){
 RCHECK(test<=7);Memory before;RCHECK(s_memory(d,&before));Viewer *v=vheadless_open(d,base,9,2);RCHECK(v);v->cfg.nonblocking=1;Physics *p=v->p;
 RCHECK(ph_state_acquire(p,&device_test_old_lease)&&ph_work_prepare(p,NULL,0,&device_test_old_task));
 StorageDevice *same=d;Physics *same_p=p;RCHECK(!s_try_close(&same,0)&&same==d&&!ph_teardown(&same_p)&&same_p==p);
 ID3D12Fence *gate=NULL;DeviceStatus pending,held,done;PhWorkInfo info;int removed=0;double blocked_us=0,start=0;
 if(test==0){
  RCHECK(vheadless_start(v,0,1)&&ph_state_release(p,&device_test_old_lease)&&ph_work_cancel(p,&device_test_old_task));
 }else if(test==1){
  VFrame *f=&v->frames[0];f->tick=0;RCHECK(vbegin_physics(v,f));s_test_api_fault(d,S_FAULT_CLOSE,1);
  RCHECK(!ph_record_frame(p,0,&f->result,f->header,0)&&s_device_state(d)==S_CONTEXT_FAILED);
 }else if(test==2||test==4){
  RCHECK(device_test_gate(v,&gate,1,0));VFrame *f=&v->frames[0];f->tick=0;RCHECK(vbegin_physics(v,f));
  if(test==2)s_test_api_fault(d,S_FAULT_SIGNAL,1);
  int recorded=ph_record_frame(p,0,&f->result,f->header,0);f->physics=d->slot;f->cf=s_fence(d);
  if(test==2)RCHECK(!recorded&&d->g.unfenced);
  else{RCHECK(recorded);s_test_api_fault(d,S_FAULT_WAIT,1);RCHECK(!s_wait(d));}
  RCHECK(s_device_state(d)==S_CONTEXT_FAILED&&s_device_info(d,&pending));
  start=s_clock();RCHECK(!viewer_try_close(&v,5)&&v);blocked_us=s_clock()-start;
  RCHECK(s_device_info(d,&held)&&held.live_buffers==pending.live_buffers&&held.claims==pending.claims);
  RCHECK(SUCCEEDED(ID3D12Fence_Signal(gate,1)));
 }else if(test==3||test==5||test==6){
  RCHECK(device_test_gate(v,&gate,test==5,1));
  if(test==6){
   v->cfg.mode=1;VFrame *f=&v->frames[0];f->sequence=0;f->tick=0;s_test_api_fault(d,S_FAULT_SIGNAL,1);RCHECK(!vrender(v,f)&&f->consumer.id);
  }else RCHECK(vheadless_start(v,0,1));
  RCHECK(s_device_info(d,&pending));
  if(test==5){
   removed=p2_remove(&d->g);RCHECK(removed&&s_device_state(d)==S_CONTEXT_REMOVED);
   RCHECK(gp_completed(&d->g)==UINT64_MAX&&ID3D12Fence_GetCompletedValue(v->graphics_fence)==UINT64_MAX);
   RCHECK(!s_wait(d));
  }else{
   start=s_clock();RCHECK(!viewer_try_close(&v,5)&&v);blocked_us=s_clock()-start;
   RCHECK(s_device_state(d)==S_CONTEXT_FAILED&&s_device_info(d,&held)&&held.live_buffers==pending.live_buffers&&held.claims==pending.claims);
   RCHECK(!ph_failure_cleanup(p)); // A failed wait is not completion.
   RCHECK(SUCCEEDED(ID3D12Fence_Signal(gate,1)));
  }
 }else if(test==7){
  RCHECK(viewer_try_close(&v,1000)&&!v&&s_begin(d)&&s_transition(d,device_test_old_lease.buffer,1));
  RCHECK(s_recording(d));removed=p2_remove(&d->g);RCHECK(removed&&s_device_state(d)==S_CONTEXT_REMOVED);
 }
 if(test){
  uint64_t serial;PhStateStats stats;RCHECK(ph_state_stats(p,&stats));serial=stats.serial;
  PhStateLease rejected;PhysicsResult rejected_result={0};
  RCHECK(!ph_state_validate(p,&device_test_old_lease)&&!ph_work_info(p,&device_test_old_task,&info)&&!ph_state_acquire(p,&rejected));
  RCHECK(!ph_tick(p,ph_next_tick(p),&rejected_result)&&ph_state_stats(p,&stats)&&stats.serial==serial);
  RCHECK(!s_begin(d)&&!s_new(d,256,0,"must reject on failed context")&&!s_resource_available(d,base[0],PH_WORK_READ));
 }
 start=s_clock();RCHECK(viewer_try_close(&v,1000)&&!v&&viewer_try_close(&v,0));double cleanup_us=s_clock()-start;
 RCHECK(ph_teardown(&p)&&!p&&ph_teardown(&p));gp_release(gate);
 RCHECK(s_device_info(d,&done)&&done.owners==0&&done.claims==0);
 if(test)RCHECK(!s_device_check(d));else RCHECK(s_device_check(d));
 if(!removed)RCHECK(s_errors(d)==0);
 FILE *f=fopen(path,"w");RCHECK(f);
 const char *names[]={"normal pending-consumer shutdown","injected Close failure before Execute","injected compute Signal failure after Execute","real timeout behind held consumer gate","injected compute wait failure","API-triggered D3D12 RemoveDevice","injected graphics Signal failure after Execute","API removal during unsubmitted recording without renderer owner"};
 fprintf(f,"{\"status\":\"PASS\",\"case\":%u,\"trigger\":\"%s\",\"failure_injected\":%s,\"api_device_removal_executed\":%s,\"physical_hardware_loss\":false,\"terminal_state\":%u,\"first_error\":%u,\"removed_reason\":%u,\"owners_after\":%u,\"claims_after\":%u,\"blocked_cleanup_us\":%.9g,\"cleanup_us\":%.9g,\"repeated_teardown\":true,\"stale_handles_rejected\":true,\"new_publications_blocked\":%s}",test,names[test],test==1||test==2||test==4||test==6?"true":"false",removed?"true":"false",done.state,(unsigned)done.error,(unsigned)done.removed_reason,done.owners,done.claims,blocked_us,cleanup_us,test?"true":"false");RCHECK(fclose(f)==0);
 fprintf(stderr,"PASS device lifecycle case %u: %s; removed=%d physical_hardware_loss=0\n",test,names[test],removed);return 1;
}
int viewer_device_recreated(StorageDevice *d,const uint64_t *base){
 Viewer *v=vheadless_open(d,base,9,2);RCHECK(v);PhWorkInfo info;
 RCHECK(!ph_work_info(v->p,&device_test_old_task,&info)&&!ph_state_validate(v->p,&device_test_old_lease));
 v->cfg.nonblocking=0;RCHECK(vheadless_start(v,0,1)&&vheadless_proof(v,&v->frames[0])&&vfinish(v,&v->frames[0]));
 v->cfg.nonblocking=1;RCHECK(vheadless_start(v,1,1)&&vheadless_proof(v,&v->frames[1])&&vfinish(v,&v->frames[1]));
 Physics *p=v->p;RCHECK(viewer_try_close(&v,1000)&&ph_teardown(&p));return 1;
}
