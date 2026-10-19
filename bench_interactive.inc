// Interactive host only: original G4 simulation passes and dt are unchanged.
static void vmenu(Viewer *v){HMENU root=CreateMenu(),sim=CreatePopupMenu(),scene=CreatePopupMenu(),view=CreatePopupMenu(),bench=CreatePopupMenu();
 AppendMenuW(sim,MF_STRING,100,L"Pause / resume\tSpace");AppendMenuW(sim,MF_STRING,101,L"Single step (paused)\tN");AppendMenuW(sim,MF_STRING,102,L"Reset deterministic scene\tR");
 AppendMenuW(sim,MF_STRING,130,L"Faster tick pacing\t+");AppendMenuW(sim,MF_STRING,131,L"Slower tick pacing\t-");
 AppendMenuW(scene,MF_STRING,110,L"10,000 balls\t1");AppendMenuW(scene,MF_STRING,111,L"100,000 balls\t2");AppendMenuW(scene,MF_STRING,112,L"1,000,000 balls\t3");
 AppendMenuW(scene,MF_STRING,121,L"Sparse");AppendMenuW(scene,MF_STRING,122,L"Mixed");AppendMenuW(scene,MF_STRING,123,L"Clustered");AppendMenuW(scene,MF_STRING,120,L"Cycle collision profile\tP");
 AppendMenuW(scene,MF_STRING,141,L"1 frame in flight");AppendMenuW(scene,MF_STRING,142,L"2 frames in flight");AppendMenuW(scene,MF_STRING,143,L"3 frames in flight");
 AppendMenuW(view,MF_STRING,150,L"Overview\tHome");AppendMenuW(view,MF_STRING,151,L"Individual table\tZ");AppendMenuW(view,MF_STRING,103,L"Toggle dashboard\tH");AppendMenuW(view,MF_STRING,152,L"Toggle VSync");
 AppendMenuW(bench,MF_STRING,104,L"Start / stop recording\tF9");AppendMenuW(bench,MF_STRING,105,L"Save / flush results\tF10");
 AppendMenuW(root,MF_POPUP,(UINT_PTR)sim,L"Simulation");AppendMenuW(root,MF_POPUP,(UINT_PTR)scene,L"Scene");AppendMenuW(root,MF_POPUP,(UINT_PTR)view,L"View");AppendMenuW(root,MF_POPUP,(UINT_PTR)bench,L"Benchmark");SetMenu(v->window,root);DrawMenuBar(v->window);
}
static void vevent(Viewer *v,const char *event){BenchRecord r={0};r.qpc=vqpc();r.n=v->cfg.n;r.profile=v->cfg.profile;r.depth=v->cfg.depth;r.vsync=v->cfg.vsync;r.generation=ph_next_tick(v->p);r.epoch=v->cfg.source_epoch;r.camera_x=v->camera_x;r.camera_y=v->camera_y;r.zoom=v->half_height;r.speed=v->speed;snprintf(r.event,sizeof(r.event),"%s",event);bench_log_push(&r);}
static void vcommand(Viewer *v,UINT command){
 switch(command){case 100:v->paused=!v->paused;v->pause_count++;v->next_tick=s_clock();vevent(v,v->paused?"PAUSE":"RESUME");break;
 case 101:v->paused=1;v->step_requested=1;vevent(v,"SINGLE_STEP");break;
 case 102:v->request=1;vevent(v,"RESET_REQUEST");break;
 case 103:v->hud_hidden=!v->hud_hidden;vevent(v,"HUD_TOGGLE");break;
 case 104:v->recording=!v->recording;vevent(v,v->recording?"RECORD_START":"RECORD_STOP");bench_log_save();break;
 case 105:vevent(v,"SAVE");bench_log_save();break;
 case 110:case 111:case 112:v->request_n=command==110?10000:command==111?100000:1000000;v->request=1;vevent(v,"POPULATION_REQUEST");break;
 case 120:case 121:case 122:case 123:v->request_profile=command==120?9+(v->cfg.profile-8)%3:command-112;v->request=1;vevent(v,"PROFILE_REQUEST");break;
 case 130:case 131:v->speed=fmin(4.,fmax(.125,v->speed*(command==130?2.:.5)));v->next_tick=s_clock();vevent(v,"PACING");break;
 case 141:case 142:case 143:v->request_depth=command-140;v->request=1;vevent(v,"DEPTH_REQUEST");break;
 case 150:voverview(v);vevent(v,"CAMERA_OVERVIEW");break;
 case 151:v->camera_x=.75;v->camera_y=.5;v->half_height=.65;vevent(v,"CAMERA_DETAIL");break;
 case 152:v->cfg.vsync=!v->cfg.vsync;vevent(v,"VSYNC");break;
 // Test-only admission request: normal controls never set this budget.
 case 199:if(v->cfg.self_test==20){v->request=2;vevent(v,"TEST_ADMISSION_REQUEST");}break;
 }
}
static void vrolling(Viewer *v){double now=s_clock();if(now-v->last_dashboard<250000)return;v->last_dashboard=now;double vals[4096];uint32_t nv=0;uint64_t qpc=vqpc();
 for(UINT w=0;w<2;w++){double seconds=w?10.:1.;uint64_t cutoff=qpc>(uint64_t)(seconds*gp_clock_frequency())?qpc-(uint64_t)(seconds*gp_clock_frequency()):0;uint32_t frames=0,ticks=0;double oldest=now;
 for(UINT j=0;j<4096&&j<v->completed;j++){VSample *s=&v->samples[(v->completed-1-j)%4096];if(!s->completed_qpc||s->completed_qpc<cutoff)break;frames++;ticks+=s->simulated;oldest=s->completed_qpc*1e6/gp_clock_frequency();if(w&&s->simulated&&nv<4096)vals[nv++]=s->physics.gpu_us[39]/1000;}
 double elapsed=fmin(seconds,fmax(.001,(now-fmax(v->loop_start,now-seconds*1e6))/1e6));v->rolling_ticks[w]=ticks/elapsed;v->rolling_frames[w]=frames/elapsed;}
 for(UINT i=1;i<nv;i++){double x=vals[i];UINT j=i;while(j&&vals[j-1]>x){vals[j]=vals[j-1];j--;}vals[j]=x;}v->quantiles[0]=nv?vals[(nv-1)/2]:0;v->quantiles[1]=nv?vals[(UINT)ceil(.95*nv)-1]:0;v->quantiles[2]=nv?vals[(UINT)ceil(.99*nv)-1]:0;
}
static uint64_t vcandidates(const VSample *s){uint64_t n=0;for(UINT round=0;round<9;round++){UINT at=G4_ROUND_HISTORY_BYTE/4+G4_ROUND_HISTORY_STRIDE/4*round;if(!s->descriptor[at+24]&&!s->descriptor[at+25])n+=(uint64_t)s->descriptor[at+2]|((uint64_t)s->descriptor[at+3]<<32);}return n;}
static void vlive_hud(Viewer *v,HudPixel *p,uint32_t *count){vrolling(v);VSample *s=&v->last;Memory m={0};s_memory(v->d,&m);char line[160];uint32_t row=6;
 #define LINE(...) do{snprintf(line,sizeof(line),__VA_ARGS__);*count=hud_text(p,*count,8,row,line);row+=12;}while(0)
 uint32_t stride=v->cfg.visual_stride?v->cfg.visual_stride:v->detail?1:(v->cfg.n+49999)/50000,rendered=(v->cfg.n+stride-1)/stride;
 LINE("GPU PHYSICS BENCH 2D 16-BALL INDEPENDENT TABLES");
 LINE("SIMULATED %u RENDERED %u RATIO %.4f",v->cfg.n,rendered,(double)rendered/v->cfg.n);
 LINE("PROFILE %u %s SPEED %.3f DT 1/128",v->cfg.profile,v->paused?"PAUSED":"RUNNING",v->speed);
 LINE("1S TICKS/S %.1f RENDER FPS %.1f",v->rolling_ticks[0],v->rolling_frames[0]);
 LINE("10S TICKS/S %.1f RENDER FPS %.1f",v->rolling_ticks[1],v->rolling_frames[1]);
 LINE("GPU TICK P50 %.2f P95 %.2f P99 %.2f MS",v->quantiles[0],v->quantiles[1],v->quantiles[2]);
 LINE("RENDER GPU %.2f CPU FRAME %.2f MS",s->render_us/1000,s->frame_us/1000);
 LINE("PRESENT %.1f CALL/S BLOCK %.2f MS VSYNC %u",v->rolling_frames[0],s->present_us/1000,v->cfg.vsync);
 LINE("DISPLAY FPS: UNVERIFIED");
 LINE("A %u P %llu C %u I %u LMAX %u",s->physics.active,(unsigned long long)vcandidates(s),s->physics.contacts,s->physics.islands,s->physics.largest);
 LINE("CPU RECORD %.2f SUBMIT %.2f MS",(s->record_us+(s->simulated?s->physics.cpu_record_us:0))/1000,(s->submit_us+(s->simulated?s->physics.queue_submit_us:0))/1000);
 LINE("DEPTH %u IN FLIGHT %u GEN %u AGE %u",v->cfg.depth,v->submitted-v->completed,ph_next_tick(v->p),v->completed?ph_next_tick(v->p)-s->render[3]:0);
 LINE("COMMITTED %.0f BUDGET %.0f PEAK %.0f MIB",m.committed/1048576.,m.budget/1048576.,m.peak_committed/1048576.);
 LINE("DXGI USE %.0f PEAK %.0f MIB",m.usage/1048576.,m.peak_usage/1048576.);
 LINE("VALIDATION %llu REJECTED %u",(unsigned long long)s_errors(v->d),v->rejection_count);
 LINE("TICK ERRORS %u CONVERGENCE %u",s->physics.error_flags,(s->physics.error_flags&2u)!=0);
 LINE("RECORD %s DROPPED %llu IO ERROR %u",v->recording?"ON":"OFF",(unsigned long long)bench_log_dropped(),bench_log_failed());
 LINE("SPACE PAUSE N STEP R RESET 1/2/3 SIZE P PROFILE");
 LINE("HOME OVERVIEW Z TABLE WHEEL ZOOM DRAG PAN");
 LINE("H HUD F9 RECORD F10 SAVE +/- SPEED");
 #undef LINE
}
static void vobserve(Viewer *v,VFrame *f,VSample *s){s->frame_us=f->cpu_frame_us;v->last.frame_us=s->frame_us;v->live_completed++;v->live_ticks+=s->simulated;if(!v->recording)return;Memory m={0};s_memory(v->d,&m);BenchRecord r={0};strcpy(r.event,"FRAME");r.qpc=s->completed_qpc;r.frame=f->sequence;r.n=v->cfg.n;r.profile=v->cfg.profile;r.depth=v->cfg.depth;r.vsync=f->submitted_vsync;r.generation=f->generation;r.epoch=v->cfg.source_epoch;r.simulated=s->simulated;r.rendered=f->camera[G4_V_INSTANCECOUNT];r.active=s->physics.active;r.candidates=vcandidates(s);r.contacts=s->physics.contacts;r.islands=s->physics.islands;r.largest=s->physics.largest;r.errors=s->physics.error_flags;r.rejected=v->rejection_count;r.convergence=(s->physics.error_flags&2u)!=0;r.backlog=v->submitted-v->completed;r.age=ph_next_tick(v->p)-f->generation;r.physics_ms=s->simulated?s->physics.gpu_us[39]/1000:0;r.render_ms=s->render_us/1000;r.record_ms=(s->record_us+(s->simulated?s->physics.cpu_record_us:0))/1000;r.submit_ms=(s->submit_us+(s->simulated?s->physics.queue_submit_us:0))/1000;r.present_ms=s->present_us/1000;r.frame_ms=s->frame_us/1000;r.completion_ms=s->completion_us/1000;r.present_begin=s->present_begin_qpc;r.present_end=s->present_end_qpc;r.committed=m.committed;r.budget=m.budget;r.usage=m.usage;r.peak=m.peak_usage;float camera[4];memcpy(camera,f->camera+G4_V_CAMERAX,16);r.camera_x=camera[0];r.camera_y=camera[1];r.zoom=camera[3];r.speed=f->submitted_speed;r.simulation_start_qpc=f->simulation_start_qpc;bench_log_push(&r);}
static int vinteractive(Viewer *v){if(!v->loop_start){v->loop_start=s_clock();v->last_frame=v->loop_start;v->next_tick=v->loop_start;vevent(v,"SCENE_READY");}
 int ok=1;while(v->running&&!v->request&&(!v->cfg.steps||v->submitted<v->cfg.steps)){
 MSG msg;while(PeekMessageW(&msg,NULL,0,0,PM_REMOVE)){TranslateMessage(&msg);DispatchMessageW(&msg);}if(!v->running||v->request)break;
 if(v->minimized){MsgWaitForMultipleObjects(0,NULL,FALSE,50,QS_ALLINPUT);continue;}
 double now=s_clock();int simulate=(!v->paused&&(now>=v->next_tick||v->cfg.self_test==21))||v->step_requested;
 if(!simulate&&now-v->last_frame<16666){MsgWaitForMultipleObjects(0,NULL,FALSE,1,QS_ALLINPUT);continue;}
 if(v->submitted>=UINT32_MAX-4||ph_next_tick(v->p)>=UINT32_MAX-4){vevent(v,"EXPLICIT_GENERATION_LIMIT");ok=0;break;}
 if(!vresize(v)){ok=0;break;}uint32_t seq=v->submitted;VFrame *f=&v->frames[seq%v->cfg.depth];if(!vfinish(v,f)){ok=0;break;}
 f->submitted_speed=v->speed;f->submitted_vsync=v->cfg.vsync;f->simulation_start_qpc=simulate?vqpc():0;f->result=simulate?(PhysicsResult){0}:v->last.physics;f->simulate=simulate;f->sequence=seq;f->tick=ph_next_tick(v->p);f->generation=f->tick+(simulate?1:0);f->submit_start=s_clock();f->backpressure_us=now-v->last_frame;v->last_frame=now;f->record_us=f->submit_us=f->present_us=0;f->gf=0;
 if(simulate){if(v->cfg.ui_mode&&!p_command(v,f)){ok=0;break;}double reset_start=s_clock();if(!vbegin_physics(v,f)){ok=0;break;}f->record_us=s_clock()-reset_start;if(!vrecord_physics(v,f)){ok=0;break;}f->physics=v->d->slot;f->cf=s_fence(v->d);v->step_requested=0;v->next_tick=fmax(v->next_tick+1000000./(128*v->speed),now);}
 else f->cf=s_fence(v->d);
 if(!vrender(v,f)){ok=0;break;}f->cpu_frame_us=s_clock()-now;f->pending=1;v->submitted++;uint64_t backlog=v->submitted-v->completed;if(backlog>v->peak_backlog)v->peak_backlog=backlog;
 if(v->submitted%16==0){char title[256];snprintf(title,sizeof(title),"GPU Physics %s | %u balls profile %u | %.1f ticks/s %.1f render FPS | %s | F9 record F10 save",v->cfg.ui_mode?"Playground":"Bench",v->cfg.n,v->cfg.profile,v->rolling_ticks[0],v->rolling_frames[0],v->paused?"PAUSED":"RUNNING");SetWindowTextA(v->window,title);}
 }
 if(!vdrain(v))ok=0;
 // Consume completions in submission order, including the partially used ring.
 while(v->completed<v->submitted){VFrame *old=NULL;for(UINT j=0;j<v->cfg.depth;j++)if(v->frames[j].pending&&(!old||v->frames[j].sequence<old->sequence))old=&v->frames[j];if(!old||!vfinish(v,old)){ok=0;break;}}
 v->d->slot=v->bootstrap;v->loop_end=s_clock();bench_log_save();if(s_errors(v->d))ok=0;return ok?(v->request?2:1):0;
}
int viewer_request(Viewer *v,ViewerConfig *out){if(!v||!out||!v->request)return 0;*out=v->cfg;if(v->request_n)out->n=v->request_n;if(v->request_profile)out->profile=v->request_profile;if(v->request_depth)out->depth=v->request_depth;if(v->request==2)out->budget=1;out->source_epoch=v->cfg.source_epoch+1;out->tick_base=0;return 1;}
void viewer_rejected(Viewer *v){v->request=v->request_n=v->request_profile=v->request_depth=0;v->rejection_count++;v->next_tick=s_clock();vevent(v,"SCENE_REJECTED_ACTIVE_PRESERVED");}
void viewer_hide(Viewer *v){if(v&&v->window)ShowWindow(v->window,SW_HIDE);}
uint64_t viewer_live_ticks(Viewer *v){return v?v->live_ticks:0;}
