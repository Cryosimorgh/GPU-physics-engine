// Shared by the actual application renderer and the offscreen CLI test.
static int vaccept_physics(Viewer *v,VFrame *f){
 if(v->cfg.mode==1||(v->cfg.interactive==3&&!f->simulate))return 1;
 if(!f->accepted_decoded){
  double start=s_clock();VCHECK(gp_wait(&v->d->g,f->cf));double blocked=s_clock()-start;f->acceptance_wait_us+=blocked;v->total_stall_us+=blocked;
  uint64_t *ticks=s_map(v->d,f->phys_times,320);const uint32_t *h=s_map(v->d,f->header,G4_DESCRIPTOR_BYTES);VCHECK(ticks&&h);
  double q[64]={0};for(unsigned i=0;i<40;i++)q[i]=ticks[i]*1e6/v->d->g.frequency;
  int ok=ph_decode_frame(v->p,f->tick,&f->result,q,h);memcpy(f->accepted_header,h,G4_DESCRIPTOR_BYTES);
  VCHECK(s_unmap(v->d,f->phys_times,0)&&s_unmap(v->d,f->header,0)&&ok);f->result.blocking_us+=blocked;f->acceptance_cpu_us+=s_clock()-start-blocked;f->accepted_decoded=1;
 }
 if(f->result.error_flags){
  if(!f->rejection_reported){
   f->rejection_reported=1;fprintf(stderr,"Renderer withheld rejected tick %u error %u\n",f->tick,f->result.error_flags);
   if(v->cfg.interactive==3){BenchRecord failure={0};failure.qpc=vqpc();failure.n=v->cfg.n;failure.profile=v->cfg.profile;failure.epoch=v->cfg.source_epoch;failure.generation=f->generation;failure.errors=f->result.error_flags;failure.rejected=1;failure.convergence=(f->result.error_flags&2u)!=0;strcpy(failure.event,"TICK_REJECTED");bench_log_push(&failure);}
  }
  v->running=0;return 0;
 }
 return f->result.published==v->cfg.n&&f->accepted_header[G4_SOURCE_TICK_BYTE/4]==f->tick;
}
static int vconsumer_prepare(Viewer *v,VFrame *f){
 if(G6_RENDER_LEGACY_CONTROL)return 1;if(f->consumer.id)return 0;
 PhWorkDependency extra[5]={{f->diagnostic,PH_WORK_WRITE,0},{f->diagnostic_readback,PH_WORK_WRITE,0},{f->gfx_times,PH_WORK_WRITE,0},{f->hud,PH_WORK_READ,0}};unsigned n=4;
 if(f->capture){if(n==PH_WORK_EXTRA)return 0;extra[n++]=(PhWorkDependency){f->capture,PH_WORK_WRITE,0};}
 if(v->headless_stats){if(n==PH_WORK_EXTRA)return 0;extra[n++]=(PhWorkDependency){v->stats_readback,PH_WORK_WRITE,0};}
 if(n>PH_WORK_EXTRA||!ph_work_prepare(v->p,extra,n,&f->consumer))return 0;
 if(!ph_work_info(v->p,&f->consumer,&f->consumer_info)){ph_work_cancel(v->p,&f->consumer);memset(&f->consumer,0,sizeof(f->consumer));return 0;}
 f->generation=f->consumer_info.generation;
 uint32_t next=ph_next_tick(v->p);if(f->generation>next){ph_work_cancel(v->p,&f->consumer);memset(&f->consumer,0,sizeof(f->consumer));return 0;}
 f->snapshot_age=next-f->generation;
 // Exact generation lookup; zero is explicitly unknown, never a current-tick substitute.
 unsigned clock=f->generation%8;f->image_simulation_qpc=v->publication_clock[clock].generation==f->generation?v->publication_clock[clock].qpc:0;return 1;
}
static int vconsumer_submit(Viewer *v,VFrame *f,uint64_t fence){
 if(G6_RENDER_LEGACY_CONTROL)return SUCCEEDED(gp_queue_wait(&v->d->g,v->graphics_queue,v->d->g.fence,f->cf));
 if(!ph_work_submit(v->p,&f->consumer,v->graphics_queue,v->graphics_fence,fence))return 0;
 // Always express readiness on the consuming queue, even when CPU acceptance
 // has already observed completion. This remains correct across queue modes.
 if(FAILED(gp_queue_wait(&v->d->g,v->graphics_queue,v->d->g.fence,f->consumer_info.ready_fence))){ph_work_fail(v->p,&f->consumer);return 0;}
 f->ready_waits++;return 1;
}
static int vconsumer_release(Viewer *v,VFrame *f,int failure){
 if(!f->consumer.id)return 1;PhWorkInfo info;if(!ph_work_info(v->p,&f->consumer,&info))return 0;
 if(info.status==PH_WORK_PREPARED){if(!ph_work_cancel(v->p,&f->consumer))return 0;f->consumer_terminal=PH_WORK_CANCELLED;}
 else{if(failure&&!ph_work_fail(v->p,&f->consumer))return 0;if(!ph_work_finish(v->p,&f->consumer,&f->consumer_terminal))return 0;}
 memset(&f->consumer,0,sizeof(f->consumer));return 1;
}
