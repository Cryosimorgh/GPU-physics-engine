#pragma once
#include "physics.h"

typedef struct Viewer Viewer;
typedef struct ViewerConfig {
 uint32_t n,capacity,profile,depth,mode,vsync,separate_queue,snapshot;
 uint32_t width,height,steps,warmup,interactive,debug,visual_stride;
 uint32_t capture_every,self_test,execution,cell_mode,source_epoch,tick_base;
 uint64_t budget;
 const char *output_path,*capture_prefix;
} ViewerConfig;

// One specialized native billiards viewer, not a general renderer/scheduler.
Viewer *viewer_open(StorageDevice*,const uint64_t*,Physics*,const ViewerConfig*);
int viewer_run(Viewer*);
void viewer_close(Viewer*);
StorageDevice *s_open_view(int debug,int direct);
int viewer_request(Viewer*,ViewerConfig*);
void viewer_rejected(Viewer*);
void viewer_hide(Viewer*);
uint64_t viewer_live_ticks(Viewer*);
