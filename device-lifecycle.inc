// Sticky failure is separate from proof that GPU resources may be destroyed.
int s_device_check(StorageDevice *s){return s_active(s)&&gp_poll(&s->g);}
uint32_t s_device_state(StorageDevice *s){
 if(!s)return S_CONTEXT_CLOSED;if(gp_removed(&s->g))return S_CONTEXT_REMOVED;
 if(s->g.failed)return S_CONTEXT_FAILED;return s->stopping?S_CONTEXT_QUIESCING:S_CONTEXT_ACTIVE;
}
int s_device_error(StorageDevice *s,int32_t hr){if(!s)return 0;gp_ok(&s->g,(HRESULT)hr);gp_removed(&s->g);return s_device_check(s);}
int s_device_info(StorageDevice *s,DeviceStatus *out){
 if(!s||!out)return 0;memset(out,0,sizeof(*out));out->identity=s->identity;out->state=s_device_state(s);out->error=s->g.first_error;out->removed_reason=s->g.removed_reason;out->owners=s->state_owners;out->unfenced=s->g.unfenced;out->quiesced=s->quiesced;
 for(unsigned i=1;i<MAX_BUFFERS;i++)if(s->b[i].p){out->live_buffers++;out->claims+=s->b[i].read_claims+s->b[i].write_claims;}return 1;
}
int s_drain(StorageDevice *s,uint32_t timeout){
 if(!s)return 1;if(gp_removed(&s->g)){s->recording=s->predicating=0;for(unsigned i=0;i<MAX_BUFFERS;i++)s->b[i].used=0;return 1;}if(!s->g.queue||!s->g.fence)return 1;
 if(s->recording&&!s_abort(s)){gp_ok(&s->g,E_FAIL);return 0;}
 if(s->value>=UINT64_MAX-1)return gp_ok(&s->g,E_FAIL);
 uint64_t terminal=++s->value;
 if(FAILED(gp_queue_signal(&s->g,s->g.queue,s->g.fence,terminal)))return 0;
 if(!gp_wait_for(&s->g,terminal,timeout))return gp_removed(&s->g);
 s->g.unfenced=0;return 1;
}
int s_quiesce(StorageDevice *s,uint32_t timeout){
 if(!s)return 1;s->stopping=1;if(s->quiesced)return 1;
 if(!s_drain(s,timeout))return 0;s->quiesced=1;return 1;
}
void s_test_api_fault(StorageDevice *s,uint32_t point,uint32_t count){
 if(point==S_FAULT_SIGNAL)s->g.test_signal_failures=count;
 else if(point==S_FAULT_WAIT)s->g.test_wait_failures=count;
 else if(point==S_FAULT_CLOSE)s->g.test_close_failures=count;
}
