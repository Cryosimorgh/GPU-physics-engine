#pragma once
#include "spatial.h"
typedef struct Physics Physics;
typedef struct PhysicsConfig {uint32_t n,capacity,contacts,pairs,design,fixture,iterations,sleep_frames,max_bodies,max_work,flags,kick_slot;float dt;uint64_t budget;} PhysicsConfig;
typedef struct PhysicsResult {uint32_t error_flags,done,contacts,added,roots,queue,islands,largest,solved_bodies,solver_dispatches,total_iterations,max_iterations,rounds,published,active,woken;double gpu_us[64],cpu_us,blocking_us,allocation_us;uint64_t committed;double api_us;uint32_t command_packets;double queue_submit_us,cpu_record_us;uint32_t queue_submit_calls,execution_mode,admission_spent,retry_count;double retry_gpu_us,retry_control_us;} PhysicsResult;
Physics *ph_open(StorageDevice*,const uint64_t*,const PhysicsConfig*);
void ph_close(Physics*);
int ph_scene(Physics*);
int ph_input(Physics*,const void*,uint32_t);
int ph_tick(Physics*,uint32_t,PhysicsResult*);
int ph_read(Physics*,int,const void**,uint64_t*);
int ph_unmap(Physics*);
int ph_ledger(Physics*,const char*);
int ph_error(void);
typedef struct PhysicsVerification {uint64_t objects,contacts,mandatory_pairs,guards,solver_bodies;uint32_t islands,largest;double residual_ratio,penetration_ratio,momentum_error,energy_before,energy_after,angular_drift_error,angular_rounding_bound;} PhysicsVerification;
int ph_verify(Physics*,const PhysicsConfig*,uint32_t,const uint32_t*,const uint32_t*,const uint32_t*,PhysicsVerification*);

int ph_fence_test(Physics*);
int ph_device_tests(StorageDevice*,const uint64_t*);
int ph_inject(Physics*,int);

int ph_spatial_counts(Physics*,uint64_t*,uint64_t*);

int ph_indirect_rejection_tests(Physics*);
int ph_execution(Physics*,uint32_t,uint32_t);
int ph_tick_auto(Physics*,uint32_t,PhysicsResult*);
int ph_header(Physics*,uint32_t*);
int ph_descriptor(Physics*,uint32_t*);
int ph_retry_admission(Physics*,uint32_t);

int ph_record_frame(Physics*,uint32_t,PhysicsResult*,uint64_t,uint64_t);
int ph_decode_frame(Physics*,uint32_t,PhysicsResult*,const double*,const uint32_t*);
uint64_t ph_metadata(Physics*);
int ph_verify_initial(Physics*,const PhysicsConfig*,const uint32_t*,uint64_t*);

int ph_view_compatible(Physics*,const uint64_t*,uint32_t,uint32_t,uint32_t);

int ph_cell_mode(Physics*,uint32_t);
uint32_t ph_cell_mode_value(Physics*);

int ph_spatial_diagnostics(Physics*,uint32_t*);

// Caller drains BOTH compute and any graphics owners before structural updates.
uint32_t ph_next_tick(Physics*);
uint32_t ph_source_epoch_value(Physics*);
int ph_source_epoch_set(Physics*,uint32_t);
int ph_scene_one(Physics*,uint32_t);

// Playground requires a nonzero, initialized, fence-owned 32-byte upload.
int ph_user_command(Physics*,uint64_t);
