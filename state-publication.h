#pragma once
// Immutable GPU snapshots. API calls are serialized by the owning CPU thread.
// A lease is read-only, not permission to use the mutable legacy source/maps.
// Register every GPU reader's completion BEFORE submitting its work. A lease
// without a completion is CPU-owned; releasing it promises no GPU use exists.
#define PH_STATE_SLOTS 4
#define PH_STATE_LEASES 64
typedef struct PhStateLease {
 uint64_t device,context,serial,nonce,buffer,ready_fence,maps_byte,pool_byte;
 uint32_t generation,tick,epoch,n,capacity,slot,pool_bytes,reserved;
} PhStateLease;
typedef struct PhStateStats {
 uint64_t bytes_per_slot,committed,serial;
 uint32_t slots,pending,leases,generation,tick;
} PhStateStats;
int ph_state_reserve(Physics*,uint32_t);
int ph_state_acquire(Physics*,PhStateLease*);
int ph_state_validate(Physics*,const PhStateLease*);
int ph_state_track(Physics*,const PhStateLease*,void *d3d12_fence,uint64_t);
int ph_state_release(Physics*,const PhStateLease*);
int ph_state_stats(Physics*,PhStateStats*);
int ph_state_editable(Physics*);
int ph_try_close(Physics*);
int ph_publication_tests(StorageDevice*,const uint64_t*);
