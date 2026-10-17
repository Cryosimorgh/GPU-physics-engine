#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct PlayUI PlayUI;
typedef struct PlayStats {
 uint32_t sandbox,iterations;uint32_t width,height,n,profile,depth,paused,recording,selected,active,contacts,islands,largest,rendered,backlog,errors,rejected,hidden;
 double tps,fps,physics_ms,render_ms,cpu_ms,submit_ms,present_ms,p50,p95,p99,memory,budget,peak,speed;
 float selected_x,selected_y,camera_x,camera_y,half_height,aim_x,aim_y,impulse_strength;uint32_t aiming;
 uint32_t command;float strength;
} PlayStats;
PlayUI *play_ui_open(void *window,void *device);
int play_ui_event(PlayUI*,void*,uint32_t,uint64_t,int64_t);
int play_ui_mouse(PlayUI*);
int play_ui_keyboard(PlayUI*);
int play_ui_draw(PlayUI*,void *list,PlayStats*);
uint64_t play_ui_memory(PlayUI*);
void play_ui_close(PlayUI*);
#ifdef __cplusplus
}
#endif
