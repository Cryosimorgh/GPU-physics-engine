int s_resource_available(StorageDevice *s,uint64_t h,uint32_t access){
 Buffer *b=buffer(s,h);return s_active(s)&&b&&!b->retired&&access&&!(access&~3u)&&!b->write_claims&&(!(access&2)||!b->read_claims);
}
int s_resource_claim(StorageDevice *s,uint64_t h,uint32_t access){
 Buffer *b=buffer(s,h);if(!s_resource_available(s,h,access)||!drained(s,b)||(s->recording&&b->used)||b->read_claims==UINT32_MAX)return 0;
 if(access&2)b->write_claims=1;else b->read_claims++;return 1;
}
int s_resource_unclaim(StorageDevice *s,uint64_t h,uint32_t access){
 Buffer *b=buffer(s,h);if(!b||!access||(access&~3u))return 0;
 if(access&2){if(!b->write_claims)return 0;b->write_claims=0;}else{if(!b->read_claims)return 0;b->read_claims--;}return 1;
}
void *s_queue_retain(StorageDevice *s,void *opaque,uint32_t *kind){
 if(!s||!opaque||!kind||s_completed(s)==UINT64_MAX)return NULL;ID3D12CommandQueue *q=opaque;ID3D12Device *device=NULL;
 if(FAILED(ID3D12CommandQueue_GetDevice(q,&IID_ID3D12Device,(void**)&device)))return NULL;
 int same=device==s->g.device;gp_release(device);if(!same)return NULL;
 D3D12_COMMAND_QUEUE_DESC desc=ID3D12CommandQueue_GetDesc(q);*kind=(uint32_t)desc.Type;ID3D12CommandQueue_AddRef(q);return q;
}
void s_queue_release(void *opaque){if(opaque)ID3D12CommandQueue_Release((ID3D12CommandQueue*)opaque);}

uint32_t s_producer_queue_kind(StorageDevice *s){D3D12_COMMAND_QUEUE_DESC q=ID3D12CommandQueue_GetDesc(s->g.queue);return (uint32_t)q.Type;}
