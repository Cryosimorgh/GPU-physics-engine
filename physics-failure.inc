int ph_consumer_hold(Physics *p){if(!p||s_device_state(p->d)!=S_CONTEXT_ACTIVE||p->consumer_owners==UINT32_MAX)return 0;p->consumer_owners++;return 1;}
void ph_consumer_drop(Physics *p){if(!p||!p->consumer_owners)abort();p->consumer_owners--;}
int ph_failure_cleanup(Physics *p){
 if(!p||s_device_state(p->d)==S_CONTEXT_ACTIVE)return 0;
 int removed=s_device_state(p->d)==S_CONTEXT_REMOVED;
 // No lease is discarded merely because a wait or Signal failed. A confirmed
 // removed native device is terminal cancellation, not successful completion.
 for(unsigned i=0;i<PH_STATE_LEASES;i++){
  StateLease *a=&p->leases[i];if(a->value.nonce&&a->completion&&!removed&&!s_completion_ready(a->completion,a->completion_value))return 0;
 }
 for(unsigned i=0;i<PH_STATE_LEASES;i++){
  StateLease *a=&p->leases[i];if(!a->value.nonce)continue;
  for(unsigned j=0;j<a->extra_count;j++)if(!s_resource_unclaim(p->d,a->extra[j].buffer,a->extra[j].access))abort();
  if(!s_resource_unclaim(p->d,a->value.buffer,PH_WORK_READ))abort();
  p->state[a->value.slot].readers--;s_queue_release(a->queue);s_completion_release(a->completion);memset(a,0,sizeof(*a));
 }
 p->accepted_slot=p->pending_slot=-1;p->poisoned=1;p->producer.status=PH_WORK_FAILED;
 for(unsigned i=0;i<p->state_count;i++)p->state[i].pending=0;return 1;
}
int ph_teardown(Physics **owner){if(!owner||!*owner)return 1;if(!ph_try_close(*owner))return 0;*owner=NULL;return 1;}
