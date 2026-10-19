#pragma once
#include "runtime.h"
typedef struct Spatial Spatial;
typedef struct SpatialResult {uint64_t pairs,contacts,verified_pairs,verified_contacts,verified_objects,committed,logical,peak,active;uint32_t status,guards,islands,largest,participants;double stages[12],cpu_us,allocation_us;} SpatialResult;
Spatial *sp_open(StorageDevice*,const uint64_t*,uint32_t,uint32_t,uint32_t,uint32_t,uint32_t,uint32_t,uint32_t,uint64_t);
void sp_close(Spatial*);
int sp_fixture(Spatial*);
int sp_run(Spatial*,SpatialResult*);
int sp_run_zero_reference(Spatial*,SpatialResult*);
int sp_verify(Spatial*,SpatialResult*,const uint32_t*,const uint32_t*,const uint32_t*);
int sp_state(Spatial*,const uint32_t*,const uint32_t*);
int sp_ledger(Spatial*,const char*);
int sp_error(void);
void sp_dispatch_extent(Spatial*,uint32_t);
void sp_fast_static(Spatial*,int);
int sp_math_tests(void);
int sp_fence_test(Spatial*);
int sp_scan_test(Spatial*);
int sp_inject(Spatial*,int);
int sp_mapping_test(Spatial*);
typedef struct SpatialOutput {uint64_t buffer;uint32_t count_byte,error_byte,admitted_byte,pairs_byte,pair_stride,pair_capacity,contacts_count_byte,contacts_indices_byte,contact_index_stride;} SpatialOutput;
SpatialOutput sp_output(Spatial*);
/* G3 records into an already-open command list; no submit/wait/readback. */
int sp_record_physics(Spatial*);
void sp_physics(Spatial*,uint64_t trial,uint64_t control,float dt,uint32_t policy);

int sp_g4_occupancy(Spatial*);

int sp_g4_cell_mode(Spatial*,uint32_t);
uint32_t sp_resources(Spatial*,uint64_t*,uint32_t);
