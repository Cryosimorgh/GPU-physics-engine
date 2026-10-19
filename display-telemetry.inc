// Present calls are NOT display events. These CPU records are correlation keys
// for an external ETW/PresentMon trace, not a displayed-FPS estimator.
static void vimage_event(Viewer *v,VFrame *f,const char *type){
 if(v->cfg.interactive!=3)return;BenchRecord r={0};snprintf(r.event,sizeof(r.event),"%s",type);
 r.qpc=vqpc();r.frame=f->sequence;r.n=v->cfg.n;r.profile=v->cfg.profile;r.epoch=v->cfg.source_epoch;r.generation=f->generation;
 r.vsync=f->submitted_vsync;r.depth=v->cfg.depth;r.nonblocking=v->cfg.nonblocking;r.swap_chain=(uint64_t)(uintptr_t)v->swap;r.back_buffer=f->target_index;
 r.submit_qpc=f->image_submit_qpc;r.simulation_start_qpc=f->simulation_start_qpc;r.snapshot_start_qpc=f->image_simulation_qpc;r.graphics_fence=f->gf;
 r.present_begin=f->present_begin;r.present_end=f->present_end;r.present_id=f->image_present_id;r.present_result=f->image_present_hr;r.age=f->snapshot_age;
 r.acceptance_wait_ms=f->handoff_wait_us/1000;bench_log_push(&r);
}
// Bounded application test controls: real window-message path, real command
// upload/acceptance, existing scene and solver. Not physical input latency.
static void vdisplay_test(Viewer *v){
 if(v->cfg.self_test!=40&&v->cfg.self_test!=41)return;
 const unsigned at[]={4,30,42,298};const UINT cmd[]={201,100,100,WM_CLOSE};
 if(v->display_test_action<4&&v->submitted>=at[v->display_test_action]){
  UINT action=cmd[v->display_test_action++];
  if(action==WM_CLOSE&&v->cfg.self_test==41)PostMessageW(v->window,WM_COMMAND,202,0);
  else PostMessageW(v->window,action==WM_CLOSE?WM_CLOSE:WM_COMMAND,action==WM_CLOSE?0:action,0);
 }
}
