// Actual rendering must complete while the producer is held on a native fence.
static int vnonblocking_test(StorageDevice *d,const uint64_t *base,const char *path){
 Memory before,after;RCHECK(!G6_P3_BLOCKING_CONTROL&&s_memory(d,&before));
 Viewer *v=vheadless_open(d,base,9,2);RCHECK(v);Physics *p=v->p;ID3D12Fence *gate=NULL;
 RCHECK(SUCCEEDED(ID3D12Device_CreateFence(d->g.device,0,0,&IID_ID3D12Fence,(void**)&gate)));
 PhStateLease initial;RCHECK(ph_state_acquire(p,&initial)&&initial.generation==0);
 RCHECK(SUCCEEDED(ID3D12CommandQueue_Wait(d->g.queue,gate,1)));
 RCHECK(vheadless_start(v,0,1));VFrame *a=&v->frames[0];PhWorkHandle stale=a->consumer;
 RCHECK(gp_completed(&d->g)<a->cf&&a->consumer_info.generation==0&&a->consumer_info.ready_fence<a->cf&&a->snapshot_age==1&&a->handoff_wait_us==0);
 RCHECK(vheadless_proof(v,a)&&gp_completed(&d->g)<a->cf);
 RCHECK(vheadless_start(v,1,1));VFrame *b=&v->frames[1];
 RCHECK(gp_completed(&d->g)<b->cf&&b->consumer_info.generation==0&&b->snapshot_age==2&&vheadless_proof(v,b));
 PhysicsResult r={0};RCHECK(!ph_tick(p,2,&r)&&ph_error()==60&&ph_next_tick(p)==2);
 RCHECK(SUCCEEDED(ID3D12Fence_Signal(gate,1))&&vfinish(v,a)&&vfinish(v,b));gp_release(gate);gate=NULL;
 PhStateStats stats;PhWorkInfo info;RCHECK(ph_state_stats(p,&stats)&&stats.generation==2&&!stats.pending&&!ph_work_info(p,&stale,&info)&&!ph_work_cancel(p,&stale));
 RCHECK(ph_state_validate(p,&initial)&&ph_tick(p,2,&r)&&!r.error_flags&&ph_state_validate(p,&initial)&&ph_state_release(p,&initial)&&!ph_state_validate(p,&initial));
 PhWorkHandle tasks[64],overflow;Memory m0,m1;RCHECK(s_memory(d,&m0));
 for(unsigned i=0;i<64;i++)RCHECK(ph_work_prepare(p,NULL,0,&tasks[i]));
 RCHECK(!ph_work_prepare(p,NULL,0,&overflow));
 for(unsigned i=0;i<64;i++)RCHECK(ph_work_cancel(p,&tasks[i]));
 RCHECK(!ph_work_info(p,&tasks[0],&info)&&s_memory(d,&m1)&&m0.allocations==m1.allocations&&m0.committed==m1.committed);
 // A rejected pending tick must still draw only the previous accepted state.
 RCHECK(ph_inject(p,3));v->cfg.interactive=3;RCHECK(vheadless_start(v,2,1));a=&v->frames[0];
 RCHECK(a->consumer_info.generation==3&&a->snapshot_age==1&&vheadless_proof(v,a));
 RCHECK(!vfinish(v,a)&&a->rejection_reported&&!a->consumer.id&&ph_state_stats(p,&stats)&&stats.generation==3&&!stats.pending);
 v->cfg.interactive=0;v->cfg.mode=1;RCHECK(vheadless_start(v,3,0)&&vheadless_proof(v,b)&&vfinish(v,b)&&v->last.render[3]==3);
 // Real delayed consumer cancellation cannot release a lease before its fence.
 RCHECK(vheadless_gate(v)&&vheadless_start(v,4,0));a=&v->frames[0];uint32_t terminal;
 RCHECK(ph_work_cancel(p,&a->consumer)&&!ph_work_finish(p,&a->consumer,&terminal));
 RCHECK(SUCCEEDED(ID3D12Fence_Signal(v->test_delay,1))&&vheadless_proof(v,a)&&a->consumer_terminal==PH_WORK_CANCELLED&&vfinish(v,a));
 RCHECK(s_errors(d)==0);uint64_t vertices=v->proven_vertices;viewer_close(v);ph_close(p);
 RCHECK(s_memory(d,&after)&&before.committed==after.committed&&s_retired_bytes(d)==0&&s_errors(d)==0);
 FILE *f=fopen(path,"w");RCHECK(f);fprintf(f,"{\"status\":\"PASS\",\"actual_vertex_invocations\":%llu,\"producer_gated_draws\":2,\"snapshot_ages\":[1,2],\"lease_exhaustion\":64,\"stale_handles_rejected\":true,\"rejected_generation_withheld\":true,\"delayed_cancellation\":true,\"allocation_growth_from_leases\":0,\"debug_errors\":0,\"physical_device_loss\":\"UNVERIFIED\"}",(unsigned long long)vertices);RCHECK(fclose(f)==0);
 fprintf(stderr,"PASS real nonblocking renderer: producer-gated draws, deferred validation, age 1/2, reuse, stale handles, exhaustion, rejection and delayed cancellation\n");return 1;
}
