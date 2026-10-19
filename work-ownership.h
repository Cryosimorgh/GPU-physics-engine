#pragma once
#define PH_WORK_DEPS 32
#define PH_WORK_EXTRA 5
enum {PH_WORK_READ=1,PH_WORK_WRITE=2};
enum {PH_WORK_PREPARED=1,PH_WORK_SUBMITTED,PH_WORK_CANCEL_PENDING,PH_WORK_FAIL_PENDING,PH_WORK_COMPLETE,PH_WORK_CANCELLED,PH_WORK_FAILED};
typedef struct PhWorkHandle {uint64_t device,context,id;} PhWorkHandle;
typedef struct PhWorkDependency {uint64_t buffer;uint32_t access,reserved;} PhWorkDependency;
typedef struct PhWorkInfo {
 uint64_t device,owner,id,publication_serial,ready_fence,completion_fence;
 uint32_t generation,tick,status,queue_kind,dependency_count,completion_ready;
 PhWorkDependency dependencies[PH_WORK_DEPS];
} PhWorkInfo;
// A task reads one leased immutable generation and at most three separately
// owned resources. No work queue or allocator is created. Calls are CPU-owner
// thread serialized. Register queue/fence BEFORE executing external GPU work.
int ph_work_prepare(Physics*,const PhWorkDependency*,uint32_t,PhWorkHandle*);
int ph_work_submit(Physics*,const PhWorkHandle*,void *native_queue,void *native_fence,uint64_t);
int ph_work_info(Physics*,const PhWorkHandle*,PhWorkInfo*);
int ph_work_cancel(Physics*,const PhWorkHandle*);
int ph_work_fail(Physics*,const PhWorkHandle*);
int ph_work_finish(Physics*,const PhWorkHandle*,uint32_t *terminal_status);
int ph_producer_work(Physics*,PhWorkInfo*);
int ph_ownership_tests(StorageDevice*,const uint64_t*);
