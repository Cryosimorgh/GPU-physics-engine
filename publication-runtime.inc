// Monotonic process-local identities survive device/context recreation. No wrap.
static volatile LONG64 publication_identity;
uint64_t s_unique_id(void){
 LONG64 old=InterlockedCompareExchange64(&publication_identity,0,0);
 for(;;){if(old==INT64_MAX)return 0;LONG64 next=InterlockedCompareExchange64(&publication_identity,old+1,old);if(next==old)return (uint64_t)old+1;old=next;}
}
uint64_t s_identity(StorageDevice *s){return s?s->identity:0;}
int s_state_owner_hold(StorageDevice *s){if(!s_active(s)||s->state_owners==UINT32_MAX)return 0;s->state_owners++;return 1;}
void s_state_owner_drop(StorageDevice *s){if(!s||!s->state_owners)abort();s->state_owners--;}
int s_test_device_identity(StorageDevice *s){
 StorageDevice *other=s_open(0);if(!other)return 0;
 uint64_t id=other->identity;ID3D12Fence *fence=NULL;
 int ok=id!=s->identity&&SUCCEEDED(ID3D12Device_CreateFence(other->g.device,0,0,&IID_ID3D12Fence,(void**)&fence));
 if(ok){void *retained=s_completion_retain(s,fence);int shared=other->g.device==s->g.device;ok=shared?(retained!=NULL):(retained==NULL);s_completion_release(retained);fprintf(stderr,"DEVICE_BOUNDARY shared_native_device=%d distinct_runtime_identity=%d\n",shared,id!=s->identity);}
 gp_release(fence);s_close(other);other=s_open(0);
 if(!other)return 0;ok=ok&&other->identity!=id&&other->identity!=s->identity;s_close(other);return ok;
}
void s_record_checkpoint(StorageDevice *s){for(unsigned i=0;i<MAX_BUFFERS;i++)s->record_state[i]=s->b[i].state;}
int s_abort(StorageDevice *s){
 if(!s||!s->recording)return 1;
 if(FAILED(ID3D12GraphicsCommandList_Close(s->slot.list)))return 0;
 for(unsigned i=0;i<MAX_BUFFERS;i++){s->b[i].state=s->record_state[i];s->b[i].used=0;}
 s->recording=s->predicating=0;return 1;
}
void s_fail_dispatch_after(StorageDevice *s,uint32_t index){s->dispatch_fail=index;s->dispatch_calls=0;}
void *s_completion_retain(StorageDevice *s,void *opaque){
 if(!s||!opaque||s_completed(s)==UINT64_MAX)return NULL;
 ID3D12Fence *f=opaque;ID3D12Device *device=NULL;
 if(FAILED(ID3D12Fence_GetDevice(f,&IID_ID3D12Device,(void**)&device)))return NULL;
 int same=device==s->g.device;gp_release(device);
 if(!same||ID3D12Fence_GetCompletedValue(f)==UINT64_MAX)return NULL;
 ID3D12Fence_AddRef(f);return f;
}
int s_completion_ready(void *f,uint64_t value){if(!f||!value||value==UINT64_MAX)return 0;uint64_t done=ID3D12Fence_GetCompletedValue((ID3D12Fence*)f);return done!=UINT64_MAX&&done>=value;}
void s_completion_release(void *f){if(f)ID3D12Fence_Release((ID3D12Fence*)f);}

// Real secondary GPU queue with a deliberately delayed read. This test helper
// owns its list, allocator, fences and readback; all are destroyed after drain.
typedef struct PublicationReader {StorageDevice *s;ID3D12CommandQueue *queue;ID3D12CommandAllocator *allocator;ID3D12GraphicsCommandList *list;ID3D12Fence *gate,*done;ID3D12Resource *readback;uint64_t bytes,output;} PublicationReader;
void *s_test_reader(StorageDevice *s,uint64_t source,uint64_t bytes,void **completion){
 Buffer *b=buffer(s,source);if(!b||b->state!=D3D12_RESOURCE_STATE_COMMON||!drained(s,b)||!bytes||bytes>b->bytes)return NULL;
 PublicationReader *r=calloc(1,sizeof(*r));if(!r)return NULL;r->s=s;r->bytes=bytes;
 D3D12_COMMAND_QUEUE_DESC desc={D3D12_COMMAND_LIST_TYPE_COPY,0,D3D12_COMMAND_QUEUE_FLAG_NONE,0};
 if(FAILED(ID3D12Device_CreateCommandQueue(s->g.device,&desc,&IID_ID3D12CommandQueue,(void**)&r->queue))||FAILED(ID3D12Device_CreateCommandAllocator(s->g.device,D3D12_COMMAND_LIST_TYPE_COPY,&IID_ID3D12CommandAllocator,(void**)&r->allocator))||FAILED(ID3D12Device_CreateCommandList(s->g.device,0,D3D12_COMMAND_LIST_TYPE_COPY,r->allocator,NULL,&IID_ID3D12GraphicsCommandList,(void**)&r->list))||FAILED(ID3D12Device_CreateFence(s->g.device,0,0,&IID_ID3D12Fence,(void**)&r->gate))||FAILED(ID3D12Device_CreateFence(s->g.device,0,0,&IID_ID3D12Fence,(void**)&r->done))||!(r->output=s_new(s,bytes,2,"Headless consumer output")))goto fail;
 r->readback=buffer(s,r->output)->p;
 ID3D12GraphicsCommandList_CopyBufferRegion(r->list,r->readback,0,b->p,0,bytes);
 if(FAILED(ID3D12GraphicsCommandList_Close(r->list)))goto fail;
 // Work is submitted by the finish helper only AFTER the lease is fence-bound.
 *completion=r->done;return r;
fail:if(r->output){s_retire(s,r->output);s_collect(s);}gp_release(r->done);gp_release(r->gate);gp_release(r->list);gp_release(r->allocator);gp_release(r->queue);free(r);return NULL;
}
int s_test_reader_start(void *opaque){
 PublicationReader *r=opaque;if(FAILED(ID3D12CommandQueue_Wait(r->queue,r->gate,1)))return 0;
 ID3D12CommandList *lists[]={(ID3D12CommandList*)r->list};ID3D12CommandQueue_ExecuteCommandLists(r->queue,1,lists);
 return SUCCEEDED(ID3D12CommandQueue_Signal(r->queue,r->done,1));
}
int s_test_reader_finish(void *opaque,uint64_t *hash){
 PublicationReader *r=opaque;int ok=SUCCEEDED(ID3D12Fence_Signal(r->gate,1));HANDLE event=CreateEventA(NULL,FALSE,FALSE,NULL);
 if(!event||FAILED(ID3D12Fence_SetEventOnCompletion(r->done,1,event)))ok=0;
 else if(WaitForSingleObject(event,10000)!=WAIT_OBJECT_0)ok=0;
 if(event)CloseHandle(event);
 if(ok&&!s_completion_ready(r->done,1))ok=0;
 if(ok){unsigned char *data=gp_map(&r->s->g,r->readback,r->bytes);if(!data)ok=0;else{uint64_t h=1469598103934665603ull;for(uint64_t i=0;i<r->bytes;i++)h=(h^data[i])*1099511628211ull;*hash=h;gp_unmap(r->readback,0);}}
 // Failure is test-fatal: do not free in-flight GPU resources after a timeout.
 if(!ok)return 0;
 if(buffer(r->s,r->output)->read_claims||buffer(r->s,r->output)->write_claims)return 2;
 if(!s_retire(r->s,r->output))return 0;s_collect(r->s);gp_release(r->done);gp_release(r->gate);gp_release(r->list);gp_release(r->allocator);gp_release(r->queue);free(r);return 1;
}

void *s_test_reader_queue(void *r){return r?((PublicationReader*)r)->queue:NULL;}
uint64_t s_test_reader_output(void *r){return r?((PublicationReader*)r)->output:0;}
