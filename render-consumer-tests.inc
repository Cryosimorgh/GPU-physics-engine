// Calls the application vrender(), pipelines and ownership helpers directly.
// No HWND, swap chain, Present, pixel/image readback or screenshot is created.
#define RCHECK(x) do{if(!(x)){fprintf(stderr,"Render consumer FAIL line %d: %s\n",__LINE__,#x);return 0;}}while(0)
static Viewer *vheadless_open(StorageDevice *d,const uint64_t *base,uint32_t profile,uint32_t depth){
 PhysicsConfig pc={16,32,256,256,1,profile,4096,20,4096,8388608,7,UINT32_MAX,1.f/128,0};
 Physics *p=ph_open(d,base,&pc);if(!p||!ph_scene(p)||!ph_state_reserve(p,depth+1)){if(p)ph_close(p);return NULL;}
 Viewer *v=calloc(1,sizeof(*v));if(!v){ph_close(p);return NULL;}v->d=d;v->p=p;v->bootstrap=d->slot;v->headless=1;v->running=1;v->selected=UINT32_MAX;
 v->cfg=(ViewerConfig){.n=16,.capacity=32,.profile=profile,.depth=depth,.mode=2,.separate_queue=1,.snapshot=1,.width=128,.height=96,.steps=64,.source_epoch=1};
 v->source=base[0];v->maps=base[1];v->meta=ph_metadata(p);v->width=128;v->height=96;v->tables=v->columns=1;
 v->camera_x=profile==13?1.27f:.75f;v->camera_y=profile==13?.635f:.5f;v->half_height=1;v->samples=calloc(64,sizeof(VSample));if(!v->samples)goto fail;
 D3D12_COMMAND_QUEUE_DESC q={0};q.Type=D3D12_COMMAND_LIST_TYPE_DIRECT;
 if(FAILED(ID3D12Device_CreateCommandQueue(d->g.device,&q,&IID_ID3D12CommandQueue,(void**)&v->graphics_queue))||FAILED(ID3D12Device_CreateFence(d->g.device,0,0,&IID_ID3D12Fence,(void**)&v->graphics_fence))||FAILED(ID3D12CommandQueue_GetTimestampFrequency(v->graphics_queue,&v->graphics_frequency)))goto fail;
 v->graphics_event=CreateEventA(NULL,FALSE,FALSE,NULL);if(!v->graphics_event)goto fail;
 D3D12_DESCRIPTOR_HEAP_DESC heap={D3D12_DESCRIPTOR_HEAP_TYPE_RTV,3,0,0};if(FAILED(ID3D12Device_CreateDescriptorHeap(d->g.device,&heap,&IID_ID3D12DescriptorHeap,(void**)&v->rtv)))goto fail;
 v->rtv_stride=ID3D12Device_GetDescriptorHandleIncrementSize(d->g.device,D3D12_DESCRIPTOR_HEAP_TYPE_RTV);
 D3D12_RESOURCE_DESC desc={0};desc.Dimension=D3D12_RESOURCE_DIMENSION_TEXTURE2D;desc.Width=128;desc.Height=96;desc.DepthOrArraySize=desc.MipLevels=1;desc.Format=DXGI_FORMAT_B8G8R8A8_UNORM;desc.SampleDesc.Count=1;desc.Flags=D3D12_RESOURCE_FLAG_ALLOW_RENDER_TARGET;
 D3D12_HEAP_PROPERTIES properties={0};properties.Type=D3D12_HEAP_TYPE_DEFAULT;D3D12_CLEAR_VALUE clear={0};clear.Format=desc.Format;
 uint64_t bytes=ID3D12Device_GetResourceAllocationInfo(d->g.device,0,1,&desc).SizeInBytes;if(bytes==UINT64_MAX||bytes>UINT64_MAX/depth||!s_admit(d,bytes*depth,0))goto fail;
 D3D12_CPU_DESCRIPTOR_HANDLE handle=ID3D12DescriptorHeap_GetCPUDescriptorHandleForHeapStart(v->rtv);
 for(unsigned i=0;i<depth;i++){if(FAILED(ID3D12Device_CreateCommittedResource(d->g.device,&properties,D3D12_HEAP_FLAG_NONE,&desc,D3D12_RESOURCE_STATE_PRESENT,&clear,&IID_ID3D12Resource,(void**)&v->back[i])))goto fail;ID3D12Device_CreateRenderTargetView(d->g.device,v->back[i],NULL,handle);handle.ptr+=v->rtv_stride;v->back_commit+=bytes;d->committed+=bytes;}
 if(d->committed>d->peak)d->peak=d->committed;
 D3D12_QUERY_HEAP_DESC stats={D3D12_QUERY_HEAP_TYPE_PIPELINE_STATISTICS,1,0};if(FAILED(ID3D12Device_CreateQueryHeap(d->g.device,&stats,&IID_ID3D12QueryHeap,(void**)&v->headless_stats)))goto fail;
 v->stats_readback=s_new(d,sizeof(D3D12_QUERY_DATA_PIPELINE_STATISTICS),2,"Headless actual draw invocation proof");if(!v->stats_readback||!vpipeline(v))goto fail;
 if(G6_RENDER_LEGACY_CONTROL){Buffer *m=buffer(d,base[1]);v->render_maps=s_new(d,m->bytes,0,"P2 structural map copy");if(!v->render_maps||!s_begin(d)||!s_transition(d,base[1],1)||!s_transition(d,v->render_maps,2)||!s_copy(d,v->render_maps,base[1],m->bytes)||!s_transition(d,base[1],0)||!s_transition(d,v->render_maps,5)||!s_submit(d,0)||!s_wait(d))goto fail;}
 for(unsigned i=0;i<depth;i++)if(!vframe_slot(v,&v->frames[i]))goto fail;return v;
fail:viewer_close(v);ph_close(p);return NULL;
}
static int vheadless_start_command(Viewer *v,uint32_t seq,int simulate,int command){
 VFrame *f=&v->frames[seq%v->cfg.depth];RCHECK(vfinish(v,f));
 f->sequence=seq;f->tick=ph_next_tick(v->p);f->generation=f->tick+(simulate?1:0);f->simulate=simulate;f->has_user=command;f->submit_start=s_clock();f->result=(PhysicsResult){0};f->gf=0;f->record_us=f->submit_us=0;
 if(simulate){RCHECK(vbegin_physics(v,f)&&vrecord_physics(v,f));f->physics=v->d->slot;f->cf=s_fence(v->d);}else f->cf=s_fence(v->d);
 RCHECK(vrender(v,f));f->pending=1;v->submitted=seq+1;return 1;
}
static int vheadless_start(Viewer *v,uint32_t seq,int simulate){return vheadless_start_command(v,seq,simulate,v->cfg.profile==13&&simulate);}
static int vheadless_proof(Viewer *v,VFrame *f){
 RCHECK(vwait(v,f->gf)&&vconsumer_release(v,f,0));
 const D3D12_QUERY_DATA_PIPELINE_STATISTICS *stats=s_map(v->d,v->stats_readback,sizeof(*stats));RCHECK(stats);
 uint64_t vs=stats->VSInvocations,ps=stats->PSInvocations;RCHECK(s_unmap(v->d,v->stats_readback,0));
 RCHECK(vs==3+6*16&&ps>0);v->proven_vertices+=vs;return 1;
}
static int vheadless_gate(Viewer *v){
 if(v->test_delay){gp_release(v->test_delay);v->test_delay=NULL;}
 RCHECK(SUCCEEDED(ID3D12Device_CreateFence(v->d->g.device,0,0,&IID_ID3D12Fence,(void**)&v->test_delay))&&SUCCEEDED(ID3D12CommandQueue_Wait(v->graphics_queue,v->test_delay,1)));return 1;
}
static int vheadless_poison(Viewer *v,const uint64_t *base){
 uint64_t upload=s_new(v->d,12,1,"Test-only private buffer poison");RCHECK(upload);uint32_t *data=s_map(v->d,upload,0);RCHECK(data);data[0]=0x7fc00000u;data[1]=UINT32_MAX;data[2]=0;
 RCHECK(s_unmap(v->d,upload,12)&&s_begin(v->d)&&s_transition(v->d,base[0],2)&&s_transition(v->d,base[1],2)&&s_copy_offset(v->d,base[0],0,upload,0,4)&&s_copy_offset(v->d,base[1],0,upload,4,8)&&s_transition(v->d,base[0],0)&&s_transition(v->d,base[1],0)&&s_submit(v->d,0)&&s_wait(v->d)&&s_retire(v->d,upload)&&ph_inject(v->p,3));s_collect(v->d);return 1;
}
#include "nonblocking-consumer-tests.inc"
int viewer_consumer_mode_test(StorageDevice *d,const uint64_t *base,uint32_t profile,uint32_t samples,uint32_t nonblocking,const char *path){
 if(!samples&&profile==9)return vnonblocking_test(d,base,path);
 Memory initial,memory,final;RCHECK(s_memory(d,&initial));Viewer *v=vheadless_open(d,base,profile,samples?2:1);RCHECK(v);v->cfg.nonblocking=nonblocking;Physics *p=v->p;
 if(!samples){
  RCHECK(!G6_RENDER_LEGACY_CONTROL&&profile==13&&vheadless_gate(v));
  uint32_t *cmd=s_map(d,base[8],0);RCHECK(cmd);uint32_t words[8]={PLAY_COMMAND_MAGIC,0,1,1,0x3f800000u,0,1,0};memcpy(cmd,words,32);RCHECK(s_unmap(d,base[8],32));
  v->pick_pending=1;v->pick_x=POOL_CUE_X;v->pick_y=POOL_CUE_Y;
  RCHECK(vheadless_start(v,0,1));VFrame *f=&v->frames[0];RCHECK(f->consumer.id&&f->ready_waits==1&&f->consumer_info.generation==1);
  cmd=s_map(d,base[8],0);RCHECK(cmd);words[6]=2;words[7]=1;memcpy(cmd,words,32);RCHECK(s_unmap(d,base[8],32));
  PhysicsResult next={0};RCHECK(ph_tick(p,1,&next)&&!next.error_flags&&!ph_tick(p,2,&next)&&ph_error()==60&&vheadless_poison(v,base));
  uint32_t terminal;RCHECK(!ph_work_finish(p,&f->consumer,&terminal));
  RCHECK(SUCCEEDED(ID3D12Fence_Signal(v->test_delay,1))&&vheadless_proof(v,f)&&vfinish(v,f));
  RCHECK(v->last.render[0]==0&&v->last.render[1]==16&&v->last.render[3]==1&&v->last.render[7]==1&&v->last.render[8]==0&&v->last.render[9]==15&&v->last.render[10]==0&&v->last.render[11]==1);
  fprintf(stderr,"PASS actual vrender draw/verify/pick uses immutable bodies, maps, header and pool status despite poisoned private buffers\n");
  v->cfg.mode=1;RCHECK(vheadless_start(v,1,0)&&vheadless_proof(v,f)&&vfinish(v,f)&&v->last.render[3]==2&&v->last.render[7]==2);
  v->test_fail_record=1;f->sequence=2;f->tick=ph_next_tick(p);RCHECK(!vrender(v,f)&&f->consumer.id&&vconsumer_release(v,f,1));v->test_fail_record=0;
  for(unsigned fail=0;fail<2;fail++){
   RCHECK(vheadless_gate(v)&&vheadless_start(v,2+fail,0));
   RCHECK((fail?ph_work_fail(p,&f->consumer):ph_work_cancel(p,&f->consumer))&&!ph_work_finish(p,&f->consumer,&terminal));
   RCHECK(SUCCEEDED(ID3D12Fence_Signal(v->test_delay,1))&&vheadless_proof(v,f)&&f->consumer_terminal==(fail?PH_WORK_FAILED:PH_WORK_CANCELLED)&&vfinish(v,f));
  }
  // The poisoned producer must fail validation; its accepted snapshot survives.
  v->cfg.mode=2;f->sequence=4;f->tick=ph_next_tick(p);f->result=(PhysicsResult){0};RCHECK(vbegin_physics(v,f)&&ph_record_frame(p,f->tick,&f->result,f->header,0));f->physics=d->slot;f->cf=s_fence(d);v->cfg.interactive=3;f->simulate=1;f->has_user=1;RCHECK(!vrender(v,f)&&!f->consumer.id&&f->rejection_reported);v->cfg.interactive=0;
  v->cfg.mode=1;RCHECK(vheadless_start(v,4,0)&&vheadless_proof(v,f)&&vfinish(v,f)&&v->last.render[3]==2);
  fprintf(stderr,"PASS delayed renderer, real producer overlap, slot backpressure, reuse, cancellation, failure cleanup and rejected-state withholding\n");
 }
 double gpu[32]={0},render[32]={0},cpu[32]={0},wait[32]={0},age[32]={0},retire[32]={0},handoff[32]={0},frame[32]={0},submit[32]={0},commands[32]={0},contacts[32]={0};uint64_t vertex_count=0;
 for(unsigned i=0;i<samples+4&&samples;i++){
  double frame_start=s_clock();int command=profile==13&&i%8==0;
  if(profile==13){uint32_t *cmd=s_map(d,base[8],0);RCHECK(cmd);uint32_t words[8]={0};if(command){uint32_t shot[8]={PLAY_COMMAND_MAGIC,0,1,1,0x3f800000u,0,i+1,i};memcpy(words,shot,32);}memcpy(cmd,words,32);RCHECK(s_unmap(d,base[8],32));}
  double handoff_start=s_clock();RCHECK(vheadless_start_command(v,i,1,command));double handoff_us=s_clock()-handoff_start;VFrame *f=&v->frames[i%v->cfg.depth];RCHECK(vheadless_proof(v,f)&&vfinish(v,f)&&v->last.render[1]==16&&v->last.render[8]==0&&v->last.render[9]==15);vertex_count+=99;
  if(i>=4){gpu[i-4]=v->last.physics.gpu_us[39];render[i-4]=v->last.render_us;cpu[i-4]=v->last.physics.cpu_us+f->record_us+f->submit_us;wait[i-4]=f->handoff_wait_us;age[i-4]=f->snapshot_age;handoff[i-4]=handoff_us;retire[i-4]=v->last.backpressure_us;frame[i-4]=s_clock()-frame_start;submit[i-4]=v->last.physics.queue_submit_us+f->submit_us;commands[i-4]=command;contacts[i-4]=v->last.physics.contacts;}
 }
 // Outside timing: full final body-state signature across all slots/fields.
 uint64_t state_hash=1469598103934665603ull;
 if(samples){const void *state;uint64_t bytes;RCHECK(ph_read(p,0,&state,&bytes));const unsigned char *raw=state;for(uint64_t i=0;i<bytes;i++)state_hash=(state_hash^raw[i])*1099511628211ull;RCHECK(ph_unmap(p));}
 RCHECK(s_memory(d,&memory)&&s_errors(d)==0);FILE *file=fopen(path,"w");RCHECK(file);
 fprintf(file,"{\"nonblocking_requested\":%u,\"blocking_build\":%u,\"default_mode\":\"blocking\",\"final_state_fnv64\":\"%016llx\",",nonblocking,G6_P3_BLOCKING_CONTROL,(unsigned long long)state_hash);
 fprintf(file,"\"status\":\"PASS\",\"legacy_control\":%d,\"samples\":%u,\"profile\":%u,\"actual_vertex_invocations\":%llu,\"coverage_per_frame\":16,\"no_window\":true,\"no_present\":true,\"pixel_readback\":false,\"committed\":%llu,\"allocations\":%llu,\"managed_buffer_allocations\":%llu,\"native_target_allocations\":%u,\"validation_enabled\":%s,\"gpu_tick_us\":[",G6_RENDER_LEGACY_CONTROL,samples,profile,(unsigned long long)v->proven_vertices,(unsigned long long)memory.committed,(unsigned long long)(memory.allocations+v->cfg.depth),(unsigned long long)memory.allocations,v->cfg.depth,samples?"false":"true");
 for(unsigned i=0;i<samples;i++)fprintf(file,"%s%.9g",i?",":"",gpu[i]);fprintf(file,"],\"gpu_render_us\":[");for(unsigned i=0;i<samples;i++)fprintf(file,"%s%.9g",i?",":"",render[i]);fprintf(file,"],\"cpu_record_submit_us\":[");for(unsigned i=0;i<samples;i++)fprintf(file,"%s%.9g",i?",":"",cpu[i]);fprintf(file,"],\"acceptance_wait_us\":[");for(unsigned i=0;i<samples;i++)fprintf(file,"%s%.9g",i?",":"",wait[i]);fprintf(file,"],\"snapshot_age_ticks\":[");for(unsigned i=0;i<samples;i++)fprintf(file,"%s%.9g",i?",":"",age[i]);
 fprintf(file,"],\"retirement_blocking_us\":[");for(unsigned i=0;i<samples;i++)fprintf(file,"%s%.9g",i?",":"",retire[i]);
 fprintf(file,"],\"cpu_handoff_us\":[");for(unsigned i=0;i<samples;i++)fprintf(file,"%s%.9g",i?",":"",handoff[i]);fprintf(file,"],\"frame_complete_us\":[");for(unsigned i=0;i<samples;i++)fprintf(file,"%s%.9g",i?",":"",frame[i]);
 fprintf(file,"],\"cpu_queue_submit_us\":[");for(unsigned i=0;i<samples;i++)fprintf(file,"%s%.9g",i?",":"",submit[i]);
 fprintf(file,"],\"command_frames\":[");for(unsigned i=0;i<samples;i++)fprintf(file,"%s%.0f",i?",":"",commands[i]);
 fprintf(file,"],\"contacts\":[");for(unsigned i=0;i<samples;i++)fprintf(file,"%s%.0f",i?",":"",contacts[i]);
 double elapsed=0;for(unsigned i=0;i<samples;i++)elapsed+=frame[i];fprintf(file,"],\"complete_frames_per_second\":%.9g}",elapsed>0?1e6*samples/elapsed:0);RCHECK(fclose(file)==0);
 viewer_close(v);ph_close(p);RCHECK(s_memory(d,&final)&&final.committed==initial.committed&&s_retired_bytes(d)==0&&s_errors(d)==0);
 fprintf(stderr,"PASS real application render consumer: %u measured frames, 16 objects per frame, no GUI or image readback\n",samples);return 1;
}

// Retain the P3/P4 direct-test API; application mode selection uses ViewerConfig.
int viewer_consumer_test(StorageDevice *d,const uint64_t *b,uint32_t profile,uint32_t samples,const char *path){return viewer_consumer_mode_test(d,b,profile,samples,1,path);}
