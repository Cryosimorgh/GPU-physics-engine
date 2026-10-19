#include <string.h>
#include <stdlib.h>
#define PUB_REQUIRE(x) do{if(!(x)){fprintf(stderr,"G6 publication test FAIL line %d: %s\n",__LINE__,#x);return 0;}}while(0)
static uint64_t publication_hash(const void *raw,uint64_t bytes){const unsigned char *data=raw;uint64_t h=1469598103934665603ull;for(uint64_t i=0;i<bytes;i++)h=(h^data[i])*1099511628211ull;return h;}
static int publication_read(StorageDevice *d,const PhStateLease *lease,uint64_t *hash){
 uint64_t bytes=76ull*lease->capacity+256+lease->pool_bytes,staging=s_new(d,bytes,2,"G6 test-only full snapshot verification");if(!staging)return 0;
 if(!s_begin(d)||!s_transition(d,lease->buffer,1)||!s_copy(d,staging,lease->buffer,bytes)||!s_transition(d,lease->buffer,5)||!s_submit(d,0)||!s_wait(d))return 0;
 void *data=s_map(d,staging,bytes);if(!data)return 0;*hash=publication_hash(data,bytes);
 return s_unmap(d,staging,0)&&s_retire(d,staging)&&(s_collect(d)>=1);
}
int ph_publication_tests(StorageDevice *d,const uint64_t *base){
 PhysicsConfig c={32,32,256,256,1,1,4096,20,4096,8388608,1,UINT32_MAX,1.f/128,0};
 Memory before,after;PUB_REQUIRE(s_memory(d,&before));
 Physics *p=ph_open(d,base,&c);PUB_REQUIRE(p&&ph_scene(p));
 PhStateLease initial,a,b,stale;uint64_t initial_hash,ha,hb;
 PUB_REQUIRE(ph_state_acquire(p,&initial)&&publication_read(d,&initial,&initial_hash));
 PUB_REQUIRE(!ph_try_close(p)&&!ph_scene(p)&&!ph_state_editable(p));
 PhysicsResult r={0};PUB_REQUIRE(ph_tick(p,0,&r)&&!r.error_flags&&r.published==32);
 PUB_REQUIRE(ph_state_acquire(p,&a)&&a.generation==1&&a.tick==0&&a.serial>initial.serial&&a.buffer!=initial.buffer);
 PUB_REQUIRE(publication_read(d,&initial,&ha)&&ha==initial_hash);
 // Both bounded slots are pinned. The failed admission cannot advance the tick.
 PhStateStats stats;PUB_REQUIRE(ph_state_stats(p,&stats)&&stats.slots==2&&stats.leases==2);
 PUB_REQUIRE(!ph_tick(p,1,&r)&&ph_error()==60&&ph_next_tick(p)==1);
 PUB_REQUIRE(ph_state_release(p,&initial)&&!ph_state_validate(p,&initial)&&!ph_state_release(p,&initial));
 PUB_REQUIRE(ph_state_reserve(p,3)); // Explicit checked growth, no implicit allocation.
 uint64_t one=s_allocation(d,76ull*c.capacity+256,0);PUB_REQUIRE(ph_state_stats(p,&stats)&&stats.committed==3*one);
 // A real delayed GPU reader retains generation 1 while producer advances.
 uint64_t old_hash;PUB_REQUIRE(publication_read(d,&a,&old_hash));
 void *done=NULL,*reader=s_test_reader(d,a.buffer,76ull*a.capacity+256,&done);PUB_REQUIRE(reader);
 PUB_REQUIRE(ph_state_track(p,&a,done,1)&&!ph_state_track(p,&a,done,1)&&s_test_reader_start(reader));
 PUB_REQUIRE(!ph_state_release(p,&a));
 PUB_REQUIRE(ph_tick(p,1,&r)&&!r.error_flags&&ph_state_acquire(p,&b)&&b.generation==2);
 PUB_REQUIRE(publication_read(d,&a,&ha)&&ha==old_hash);
 PUB_REQUIRE(s_test_reader_finish(reader,&hb)&&hb==old_hash);
 PUB_REQUIRE(ph_state_release(p,&a)&&!ph_state_validate(p,&a));
 // Fence-complete is not enough: CPU acceptance must decode the matching header.
 PUB_REQUIRE(s_delay(d));PUB_REQUIRE(ph_record_frame(p,2,&r,0,0));
 PhStateLease pending;PUB_REQUIRE(ph_state_acquire(p,&pending)&&pending.serial==b.serial);
 double q[64]={0};uint32_t fake[256]={0};PUB_REQUIRE(!ph_decode_frame(p,2,&r,q,fake));
 PUB_REQUIRE(s_unblock(d)&&s_wait(d)&&s_times_count(d,q,40));
 // Existing readback is private; ph_header reads only its completed metadata.
 uint32_t h[128]={0};PUB_REQUIRE(ph_header(p,h));
 PUB_REQUIRE(ph_decode_frame(p,2,&r,q,h)&&!r.error_flags);
 PUB_REQUIRE(!ph_decode_frame(p,2,&r,q,h)); // Replay cannot republish a generation.
 PUB_REQUIRE(ph_state_release(p,&pending)&&ph_state_release(p,&b));
 PUB_REQUIRE(ph_state_acquire(p,&a)&&a.generation==3&&a.tick==2);stale=a;
 PhStateLease forged=a;forged.serial++;PUB_REQUIRE(!ph_state_validate(p,&forged));
 PUB_REQUIRE(!ph_state_reserve(p,PH_STATE_SLOTS+1));
 // Lease-table exhaustion is explicit; no new GPU resources are allocated.
 PhStateLease held[PH_STATE_LEASES];unsigned count=0;while(count<PH_STATE_LEASES&&ph_state_acquire(p,&held[count]))count++;
 PUB_REQUIRE(count==PH_STATE_LEASES-1&&!ph_state_acquire(p,&b));
 for(unsigned i=0;i<count;i++)PUB_REQUIRE(ph_state_release(p,&held[i]));
 PUB_REQUIRE(publication_read(d,&a,&old_hash));
 PUB_REQUIRE(ph_inject(p,2)&&ph_tick(p,3,&r)&&r.error_flags&&r.published==0);
 PUB_REQUIRE(ph_state_acquire(p,&b)&&b.serial==a.serial&&publication_read(d,&b,&ha)&&ha==old_hash);
 PUB_REQUIRE(ph_state_release(p,&a)&&ph_state_release(p,&b)&&ph_try_close(p));
 fprintf(stderr,"PASS publication acceptance, rejection rollback, delayed/concurrent GPU reader, exhaustion, completion replay, stale lease\n");
 p=ph_open(d,base,&c);PUB_REQUIRE(p&&ph_scene(p)&&!ph_state_validate(p,&stale));
 PUB_REQUIRE(ph_state_acquire(p,&a)&&publication_read(d,&a,&old_hash));
 // Failed dispatch after transitions: discard the unsubmitted packet. No publish.
 s_fail_dispatch_after(d,1);PUB_REQUIRE(!ph_tick(p,0,&r)&&!s_recording(d));s_fail_dispatch_after(d,UINT32_MAX);
 PUB_REQUIRE(ph_state_validate(p,&a)&&publication_read(d,&a,&ha)&&ha==old_hash);
 PUB_REQUIRE(!ph_tick(p,1,&r)&&ph_state_release(p,&a)&&ph_try_close(p));
 p=ph_open(d,base,&c);PUB_REQUIRE(p&&ph_scene(p)&&ph_state_acquire(p,&a)&&publication_read(d,&a,&old_hash));
 s_fail_dispatch_after(d,100);PUB_REQUIRE(!ph_tick(p,0,&r)&&!s_recording(d)&&s_packet_count(d)>1);s_fail_dispatch_after(d,UINT32_MAX);
 PUB_REQUIRE(s_wait(d)&&publication_read(d,&a,&ha)&&ha==old_hash&&ph_state_release(p,&a)&&ph_try_close(p));
 fprintf(stderr,"PASS failed dispatch recording preserves immutable accepted state; context fail-closed\n");
 // A real nonconverging solver is distinct from a validation fault injection.
 PhysicsConfig reject=c;reject.fixture=4;reject.iterations=1;
 p=ph_open(d,base,&reject);PUB_REQUIRE(p&&ph_scene(p)&&ph_state_acquire(p,&a)&&publication_read(d,&a,&old_hash));
 PUB_REQUIRE(ph_tick(p,0,&r)&&(r.error_flags&2)&&r.published==0&&r.solver_dispatches>0);
 PUB_REQUIRE(ph_state_acquire(p,&b)&&b.serial==a.serial&&publication_read(d,&b,&ha)&&ha==old_hash);
 PUB_REQUIRE(ph_state_release(p,&a)&&ph_state_release(p,&b)&&ph_try_close(p));
 // Existing admission retry can publish exactly once after the rejected attempt.
 reject.iterations=4096;p=ph_open(d,base,&reject);PUB_REQUIRE(p&&ph_scene(p)&&ph_execution(p,1,1));
 PUB_REQUIRE(ph_tick(p,0,&r)&&r.error_flags==1024&&r.published==0&&ph_retry_admission(p,0));
 PUB_REQUIRE(ph_tick(p,0,&r)&&!r.error_flags&&ph_state_acquire(p,&a)&&a.generation==1&&a.tick==0);
 PUB_REQUIRE(!ph_source_epoch_set(p,2)&&ph_state_release(p,&a)&&ph_source_epoch_set(p,2));
 PUB_REQUIRE(ph_state_acquire(p,&b)&&b.epoch==2&&b.generation==1&&b.tick==0&&b.serial>a.serial);
 PUB_REQUIRE(ph_state_release(p,&b)&&ph_try_close(p));
 fprintf(stderr,"PASS nonconverging solver rollback, admission retry, structural epoch ownership\n");
 // Persistent pool rolling/configuration fields belong to the same snapshot.
 reject=c;reject.n=16;reject.fixture=13;reject.flags=7;
 p=ph_open(d,base,&reject);PUB_REQUIRE(p&&ph_scene(p));float material[8]={.93f,.8f,.2f,.012f,.02f,.15f,9.81f,.02f},rolling[32]={0};rolling[0]=.001f;
 PUB_REQUIRE(ph_pool_material(p,material)&&ph_pool_rolling(p,rolling)&&ph_state_acquire(p,&a)&&a.pool_bytes==160&&a.pool_byte==76ull*a.capacity+256);
 PUB_REQUIRE(publication_read(d,&a,&old_hash)&&!ph_pool_rolling(p,rolling));
 PUB_REQUIRE(ph_tick(p,0,&r)&&!r.error_flags&&publication_read(d,&a,&ha)&&ha==old_hash);
 PUB_REQUIRE(ph_state_release(p,&a)&&ph_try_close(p));
 PUB_REQUIRE(s_test_device_identity(d));
 fprintf(stderr,"PASS persistent pool snapshot, native-device fence identity check and runtime recreation identities\n");
 // Allocation failure is all-or-nothing, including two publication resources.
 for(unsigned i=0;i<7;i++){s_fail_after(d,i);p=ph_open(d,base,&c);PUB_REQUIRE(!p);s_fail_after(d,UINT32_MAX);PUB_REQUIRE(s_memory(d,&after)&&after.committed==before.committed);}
 p=ph_open(d,base,&c);PUB_REQUIRE(p&&ph_scene(p));s_fail_after(d,1);PUB_REQUIRE(!ph_state_reserve(p,4));s_fail_after(d,UINT32_MAX);
 PUB_REQUIRE(ph_state_stats(p,&stats)&&stats.slots==2&&stats.committed==2*one);PUB_REQUIRE(ph_try_close(p));
 PUB_REQUIRE(s_memory(d,&after)&&after.committed==before.committed&&!s_retired_bytes(d)&&s_errors(d)==0);
 fprintf(stderr,"PASS publication exact allocation ledger and partial-allocation cleanup; device removal UNVERIFIED\n");
 return 1;
}
