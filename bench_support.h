#pragma once
#include <stdint.h>
typedef struct BenchRecord {
 uint64_t simulation_start_qpc;uint64_t qpc,frame,present_begin,present_end,budget,usage,committed,peak;
 uint32_t n,profile,depth,vsync,generation,epoch,simulated,rendered,active,contacts,islands,largest,errors,rejected,convergence,backlog,age;
 uint64_t candidates;
 double physics_ms,render_ms,record_ms,submit_ms,present_ms,frame_ms,completion_ms,camera_x,camera_y,zoom,speed;
 uint64_t swap_chain,submit_qpc,snapshot_start_qpc,graphics_fence,allocations,releases;
 uint32_t present_id,present_result,back_buffer,nonblocking;double acceptance_wait_ms;
 uint32_t impulse_entity,impulse_generation,impulse_serial;float impulse_x,impulse_y;char event[64];
} BenchRecord;
int bench_log_start(const char *directory,int automated);
void bench_log_push(const BenchRecord*);
void bench_log_event(const char*,uint32_t,uint32_t);
void bench_log_save(void);
void bench_log_close(void);
uint64_t bench_log_dropped(void);
uint64_t bench_log_written(void);
int bench_log_failed(void);
const char *bench_log_directory(void);
void bench_message(const char*);
