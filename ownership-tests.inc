#define OWN(x) do{if(!(x)){fprintf(stderr,"G6-P2 FAIL line %d: %s\n",__LINE__,#x);return 0;}}while(0)
int ph_ownership_tests(StorageDevice *d,const uint64_t *base){
 PhysicsConfig c={32,32,256,256,1,1,4096,20,4096,8388608,1,UINT32_MAX,1.f/128,0};
 Memory before,after;OWN(s_memory(d,&before));uint64_t baseline_committed=before.committed;Physics *p=ph_open(d,base,&c);OWN(p&&ph_scene(p));
 PhWorkHandle a,b;PhWorkInfo info,producer;uint32_t terminal;
 uint64_t output=s_new(d,4096,2,"P2 conflict test output");OWN(output);
 PhWorkDependency extra={output,PH_WORK_WRITE,0};OWN(ph_work_prepare(p,&extra,1,&a)&&ph_work_info(p,&a,&info));
 OWN(info.status==PH_WORK_PREPARED&&info.dependency_count==2&&info.publication_serial&&info.ready_fence);
 OWN(!ph_work_prepare(p,&extra,1,&b)&&!s_retire(d,output)&&!s_map(d,output,0));
 extra.access=PH_WORK_READ;OWN(!ph_work_prepare(p,&extra,1,&b));
 extra=(PhWorkDependency){info.dependencies[0].buffer,PH_WORK_WRITE,0};OWN(!ph_work_prepare(p,&extra,1,&b));
 OWN(!s_retire(d,info.dependencies[0].buffer));
 OWN(s_begin(d)&&!s_transition(d,info.dependencies[0].buffer,2)&&s_abort(d));
 OWN(ph_work_cancel(p,&a)&&!ph_work_info(p,&a,&info)&&!ph_work_cancel(p,&a));
 OWN(s_retire(d,output));s_collect(d);
 fprintf(stderr,"PASS task read/write conflicts, immutable write rejection, pre-submit cancellation and stale handles\n");
 // Shared readers are legal, exclusive output writer is rejected.
 output=s_new(d,4096,2,"P2 shared output");OWN(output);extra=(PhWorkDependency){output,PH_WORK_READ,0};
 OWN(ph_work_prepare(p,&extra,1,&a)&&ph_work_prepare(p,&extra,1,&b));
 PhWorkHandle rejected;extra.access=PH_WORK_WRITE;OWN(!ph_work_prepare(p,&extra,1,&rejected));
 OWN(ph_work_cancel(p,&a)&&ph_work_cancel(p,&b)&&s_retire(d,output));s_collect(d);
 // Delayed actual copy-queue consumers: cancellation never drops GPU ownership.
 for(unsigned failure=0;failure<2;failure++){
  PhStateLease lease;uint64_t initial_hash,read_hash;OWN(ph_state_acquire(p,&lease)&&publication_read(d,&lease,&initial_hash));
  void *fence=NULL,*reader=s_test_reader(d,lease.buffer,76ull*lease.capacity+256,&fence);OWN(reader);output=s_test_reader_output(reader);
  extra=(PhWorkDependency){output,PH_WORK_WRITE,0};OWN(ph_work_prepare(p,&extra,1,&a));
  OWN(ph_work_info(p,&a,&info)&&info.dependencies[0].buffer==lease.buffer&&info.publication_serial==lease.serial);
  OWN(ph_work_submit(p,&a,s_test_reader_queue(reader),fence,1)&&!ph_work_submit(p,&a,s_test_reader_queue(reader),fence,1)&&s_test_reader_start(reader));
  OWN(ph_state_release(p,&lease));
  OWN((failure?ph_work_fail(p,&a):ph_work_cancel(p,&a))&&!ph_work_finish(p,&a,&terminal)&&!s_retire(d,output));
  OWN(ph_work_info(p,&a,&info)&&!info.completion_ready&&info.completion_fence==1&&info.queue_kind==3);
  PhysicsResult r={0};uint32_t tick=ph_next_tick(p);OWN(ph_tick(p,tick,&r)&&!r.error_flags&&ph_producer_work(p,&producer));
  OWN(producer.status==PH_WORK_COMPLETE&&producer.completion_ready&&producer.publication_serial!=info.publication_serial&&producer.dependency_count>8);
  OWN(!ph_tick(p,tick+1,&r)&&ph_error()==60&&ph_next_tick(p)==tick+1);
  OWN(s_test_reader_finish(reader,&read_hash)==2&&read_hash==initial_hash);
  PhWorkHandle stale_fence;OWN(ph_work_prepare(p,NULL,0,&stale_fence));
  OWN(!ph_work_submit(p,&stale_fence,s_test_reader_queue(reader),fence,1)&&ph_work_cancel(p,&stale_fence));
  OWN(ph_work_finish(p,&a,&terminal)&&terminal==(failure?PH_WORK_FAILED:PH_WORK_CANCELLED));
  OWN(!ph_work_info(p,&a,&info)&&s_test_reader_finish(reader,&read_hash)==1);
 }
 fprintf(stderr,"PASS concurrent producer/copy-queue tasks, delayed cancellation/failure cleanup, backpressure and generation reuse\n");
 // Exhaustion is bounded and reversible; there is no task eviction or allocation.
 PhWorkHandle held[PH_STATE_LEASES];OWN(s_memory(d,&before));
 for(unsigned i=0;i<PH_STATE_LEASES;i++)OWN(ph_work_prepare(p,NULL,0,&held[i]));
 OWN(!ph_work_prepare(p,NULL,0,&a));for(unsigned i=0;i<PH_STATE_LEASES;i++)OWN(ph_work_cancel(p,&held[i]));
 OWN(s_memory(d,&after)&&after.allocations==before.allocations&&after.committed==before.committed);
 // Partial admission unwinds every claim.
 output=s_new(d,4096,2,"P2 partial claim rollback");OWN(output);
 PhWorkDependency partial[2]={{output,PH_WORK_WRITE,0},{UINT64_MAX,PH_WORK_WRITE,0}};
 OWN(!ph_work_prepare(p,partial,2,&a)&&s_resource_available(d,output,PH_WORK_WRITE)&&s_retire(d,output));s_collect(d);
 OWN(ph_work_prepare(p,NULL,0,&a));PhWorkHandle stale=a;OWN(ph_work_fail(p,&a)&&ph_try_close(p));
 p=ph_open(d,base,&c);OWN(p&&ph_scene(p)&&!ph_work_info(p,&stale,&info));
 OWN(ph_work_prepare(p,NULL,0,&a)&&ph_work_info(p,&a,&info));uint64_t serial=info.publication_serial;
 s_fail_dispatch_after(d,1);PhysicsResult failed={0};OWN(!ph_tick(p,0,&failed));s_fail_dispatch_after(d,UINT32_MAX);
 OWN(ph_work_info(p,&a,&info)&&info.publication_serial==serial&&ph_producer_work(p,&producer)&&producer.status==PH_WORK_FAILED);
 OWN(ph_work_cancel(p,&a)&&ph_try_close(p));
 OWN(s_memory(d,&after)&&after.committed==baseline_committed&&s_errors(d)==0&&s_retired_bytes(d)==0);
 fprintf(stderr,"PASS bounded task exhaustion, zero task allocations, partial-claim rollback, context reuse; device loss UNVERIFIED\n");return 1;
}
