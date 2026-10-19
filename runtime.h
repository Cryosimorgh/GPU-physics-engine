#pragma once
#include <stdint.h>
typedef struct StorageDevice StorageDevice;
typedef struct Memory {uint64_t budget,usage,nonlocal_budget,nonlocal_usage,committed,peak_committed,peak_usage,allocations,releases,context_committed; } Memory;
StorageDevice *s_open(int debug);
void s_close(StorageDevice*);
int s_memory(StorageDevice*,Memory*);
const char *s_name(StorageDevice*);
uint64_t s_driver(StorageDevice*);
uint64_t s_allocation(StorageDevice*,uint64_t,int);
int s_admit(StorageDevice*,uint64_t,uint64_t);
uint64_t s_new(StorageDevice*,uint64_t,int,const char*);
int s_retire(StorageDevice*,uint64_t);
int s_collect(StorageDevice*);
int s_begin(StorageDevice*);
int s_bind(StorageDevice*,const uint64_t*,const uint32_t*);
int s_dispatch(StorageDevice*,int,uint32_t);
int s_stamp(StorageDevice*,uint32_t);
int s_submit(StorageDevice*,int);
int s_wait(StorageDevice*);
int s_copy(StorageDevice*,uint64_t,uint64_t,uint64_t);
void *s_map(StorageDevice*,uint64_t,uint64_t);
int s_unmap(StorageDevice*,uint64_t,uint64_t);
int s_transition(StorageDevice*,uint64_t,int);
int s_times(StorageDevice*,double*);
uint64_t s_errors(StorageDevice*);
int s_delay(StorageDevice*);
int s_unblock(StorageDevice*);
uint64_t s_fence(StorageDevice*);
uint64_t s_completed(StorageDevice*);
double s_clock(void);
int s_load(StorageDevice*,int,const void*,uint64_t);
uint64_t s_retired_bytes(StorageDevice*);
uint64_t s_context_bytes(StorageDevice*);
int s_policy(StorageDevice*,uint64_t,uint32_t,uint64_t);
void s_fail_after(StorageDevice*,uint32_t);
int s_spatial_features(StorageDevice*);
int s_dispatch_shape(uint32_t,int,uint32_t*,uint32_t*);
int s_dispatch_grid(StorageDevice*,int,uint32_t,uint32_t);
int s_indirect_open(StorageDevice*);
int s_indirect(StorageDevice*,int,uint64_t,uint64_t);

int s_times_count(StorageDevice*,double*,uint32_t);

int s_split(StorageDevice*,uint32_t);
uint32_t s_packet_count(StorageDevice*);
int s_indirect_count(StorageDevice*,int,uint64_t,uint64_t,uint64_t);
void s_submission_metrics(StorageDevice*,double*,uint32_t*);

int s_copy_offset(StorageDevice*,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t);

int s_recording(StorageDevice*);

// Execute only while the GPU 64-bit predicate is zero; handle 0 disables.
int s_predicate_zero(StorageDevice*,uint64_t,uint64_t);

// Recording cancellation discards only the unsubmitted packet; earlier split
// packets remain fence-owned. Device removal is fail-closed, never completion.
int s_abort(StorageDevice*);
void s_record_checkpoint(StorageDevice*);
uint64_t s_unique_id(void);
uint64_t s_identity(StorageDevice*);
int s_state_owner_hold(StorageDevice*);
void s_state_owner_drop(StorageDevice*);
int s_test_device_identity(StorageDevice*);
void *s_completion_retain(StorageDevice*,void*);
int s_completion_ready(void*,uint64_t);
void s_completion_release(void*);
void s_fail_dispatch_after(StorageDevice*,uint32_t);
// Headless secondary-copy-queue regression helpers; never called in normal ticks.
void *s_test_reader(StorageDevice*,uint64_t,uint64_t,void**);
int s_test_reader_finish(void*,uint64_t*);
int s_test_reader_start(void*);
