// UI, picking and bounded commands. No contact formulation lives here.
static void p_world(Viewer *v,int x,int y,float *wx,float *wy){float scale=2*v->half_height/v->height;*wx=v->camera_x+(x-v->width*.5f)*scale;*wy=v->camera_y-(y-v->height*.5f)*scale;}
static void p_overview(Viewer *v){if(v->cfg.profile==13){float w=POOL_TABLE_WIDTH,h=POOL_TABLE_HEIGHT;v->half_height=fmaxf(h*.68f,w*.57f*v->height/fmaxf(200,v->width-330));v->camera_x=w*.5f+310*v->half_height/v->height;v->camera_y=h*.5f-100*v->half_height/v->height;return;}uint32_t cols=(uint32_t)ceil(sqrt(v->cfg.n)),rows=(v->cfg.n+cols-1)/cols;float w=cols*.1875f+.5f,h=rows*.1875f+.5f;v->half_height=fmaxf(h*.67f,w*.64f*v->height/fmaxf(200,v->width-330));v->camera_x=w*.5f+310*v->half_height/v->height;v->camera_y=h*.5f-100*v->half_height/v->height;}
static void p_action(Viewer *v,UINT cmd){
 if(cmd==162){v->request_n=16;v->request_profile=13;v->request=1;vevent(v,"BILLIARDS_REQUEST");}
 else if(cmd==163){v->sandbox_shots=!v->sandbox_shots;vevent(v,"SANDBOX_SHOTS_TOGGLE");}
 else if((cmd>=110&&cmd<=112)&&v->cfg.profile==13){v->request_profile=9;vcommand(v,cmd);}
 else if(cmd==113||cmd==114){v->request_n=cmd==113?100:1000;v->request_profile=12;v->request=1;vevent(v,"POPULATION_REQUEST");}
 else if(cmd==160){v->request_profile=12;v->request=1;vevent(v,"PLAYGROUND_REQUEST");}
 else if(cmd>=121&&cmd<=123){if(v->cfg.n<10000)v->request_n=10000;vcommand(v,cmd);}
 else if(cmd==161){if(v->selected!=UINT32_MAX){v->camera_x=v->selected_x+.27f;v->camera_y=v->selected_y;v->half_height=.7f;vevent(v,"CAMERA_FOCUS");}}
 else if(cmd==170){v->screenshot_requested=1;vevent(v,"SCREENSHOT_REQUEST");}
 else vcommand(v,cmd);
}
static int p_input(Viewer *v,UINT message,WPARAM a,LPARAM b){
 if(v->ui)play_ui_event(v->ui,v->window,message,a,b);
 if(message==WM_COMMAND){p_action(v,LOWORD(a));return 1;}
 if(message==WM_KEYDOWN){if(v->ui&&play_ui_keyboard(v->ui))return 1;if(b&(1ll<<30))return 1;
  if(a==VK_ESCAPE){if(v->selected!=UINT32_MAX){v->selected=UINT32_MAX;v->aiming=v->released=0;vevent(v,"DESELECT");}else v->running=0;return 1;}
  if(v->cfg.profile==13&&a>='1'&&a<='3'){p_action(v,110+(UINT)(a-'1'));return 1;}if(v->cfg.profile==13&&a=='P'){p_action(v,121);return 1;}UINT cmd=a==VK_OEM_PERIOD?101:a=='F'?161:a==VK_F12?170:0;if(cmd){p_action(v,cmd);return 1;}return 0;
 }
 int mouse=message>=WM_MOUSEFIRST&&message<=WM_MOUSELAST;
 if(mouse&&v->ui&&play_ui_mouse(v->ui)&&!v->dragging&&!v->aiming)return 1;
 if(message==WM_RBUTTONDOWN){v->dragging=1;v->previous=(POINT){GET_X_LPARAM(b),GET_Y_LPARAM(b)};SetCapture(v->window);return 1;}
 if(message==WM_RBUTTONUP){v->dragging=0;ReleaseCapture();return 1;}
 if(message==WM_LBUTTONDOWN){if(v->cfg.profile<12)return 1;if(v->pick_active){vevent(v,"PICK_BUSY");return 1;}v->selected=UINT32_MAX;v->pick_active=1;p_world(v,GET_X_LPARAM(b),GET_Y_LPARAM(b),&v->pick_x,&v->pick_y);v->aim_x=(float)GET_X_LPARAM(b);v->aim_y=(float)GET_Y_LPARAM(b);v->pick_pending=1;v->aiming=1;v->released=0;SetCapture(v->window);vevent(v,"PICK_REQUEST");return 1;}
 if(message==WM_MOUSEMOVE&&v->aiming){v->aim_x=(float)GET_X_LPARAM(b);v->aim_y=(float)GET_Y_LPARAM(b);return 1;}
 if(message==WM_LBUTTONUP){if(v->aiming){v->aim_x=(float)GET_X_LPARAM(b);v->aim_y=(float)GET_Y_LPARAM(b);v->released=1;}ReleaseCapture();return 1;}
 return 0;
}
static int p_draw(Viewer *v,VFrame *f,Slot *slot){vrolling(v);VSample *s=&v->last;Memory m={0};VCHECK(s_memory(v->d,&m));PlayStats p={0};p.sandbox=v->sandbox_shots;p.iterations=s->physics.total_iterations;p.width=v->width;p.height=v->height;p.n=v->cfg.n;p.profile=v->cfg.profile;p.depth=v->cfg.depth;p.paused=v->paused;p.recording=v->recording;p.selected=v->selected;p.active=s->physics.active;p.contacts=s->physics.contacts;p.islands=s->physics.islands;p.largest=s->physics.largest;p.rendered=f->camera[G4_V_INSTANCECOUNT];p.backlog=v->submitted-v->completed;p.errors=s->physics.error_flags;p.rejected=v->rejection_count;p.hidden=v->hud_hidden;p.tps=v->rolling_ticks[0];p.fps=v->rolling_frames[0];p.physics_ms=s->simulated?s->physics.gpu_us[39]/1000:0;p.render_ms=s->render_us/1000;p.cpu_ms=s->frame_us/1000;p.submit_ms=(s->submit_us+(s->simulated?s->physics.queue_submit_us:0))/1000;p.present_ms=s->present_us/1000;p.p50=v->quantiles[0];p.p95=v->quantiles[1];p.p99=v->quantiles[2];p.memory=m.usage/1048576.;p.budget=m.budget/1048576.;p.peak=m.peak_usage/1048576.;p.speed=v->speed;p.selected_x=v->selected_x;p.selected_y=v->selected_y;p.camera_x=v->camera_x;p.camera_y=v->camera_y;p.half_height=v->half_height;p.aim_x=v->aim_x;p.aim_y=v->aim_y;p.aiming=v->aiming;p.impulse_strength=v->impulse_strength;
 VCHECK(play_ui_draw(v->ui,slot->list,&p));uint64_t bytes=play_ui_memory(v->ui);VCHECK(bytes<=PLAY_GUI_RESERVE_BYTES&&v->d->committed>=v->ui_commit);v->d->committed=v->d->committed-v->ui_commit+bytes;v->ui_commit=bytes;if(v->d->committed>v->d->peak)v->d->peak=v->d->committed;v->impulse_strength=p.strength;if(p.command)p_action(v,p.command);return 1;
}
static void p_complete(Viewer *v,VFrame *f,VSample *s){if(v->cfg.profile<12)return;
 if(v->cfg.profile==13&&s->simulated){for(uint32_t k=0;k<2;k++){uint32_t count=s->descriptor[(256+(k?G4_POSITIVE_WALL_CONTACTS_BYTE:G4_POSITIVE_BODY_CONTACTS_BYTE))/4];if(count){BenchRecord impact={0};impact.qpc=vqpc();impact.frame=f->sequence;impact.n=16;impact.profile=13;impact.generation=s->descriptor[G4_SOURCE_GENERATION_BYTE/4];impact.epoch=v->cfg.source_epoch;strcpy(impact.event,k?"RAIL_IMPACT":"BALL_IMPACT");bench_log_push(&impact);}}}
 if(f->pick_request){v->pick_active=0;v->selected=s->render[10]<v->cfg.n?s->render[10]:UINT32_MAX;v->selected_generation=s->render[11];vevent(v,v->selected!=UINT32_MAX?"BALL_SELECTED":"PICK_EMPTY");}
 if(v->cfg.profile==13&&v->selected!=UINT32_MAX&&v->selected!=0){v->selected=UINT32_MAX;vevent(v,"CUE_ONLY");}
 if(s->render[10]==v->selected&&v->selected!=UINT32_MAX){memcpy(&v->selected_x,s->render+12,4);memcpy(&v->selected_y,s->render+13,4);}
 if(v->released&&!v->pick_active&&v->selected==UINT32_MAX)v->released=v->aiming=0;
 if(v->released&&!v->pick_active&&v->selected!=UINT32_MAX){float wx,wy;p_world(v,(int)v->aim_x,(int)v->aim_y,&wx,&wy);float x=(wx-v->pick_x)*v->impulse_strength,y=(wy-v->pick_y)*v->impulse_strength,len=sqrtf(x*x+y*y);if(len>.004f){if(!v->impulse_pending){float scale=len>PLAY_MAX_IMPULSE_DELTA_V?PLAY_MAX_IMPULSE_DELTA_V/len:1;v->impulse_x=x*scale;v->impulse_y=y*scale;v->impulse_entity=v->selected;v->impulse_generation=v->selected_generation;v->impulse_pending=1;vevent(v,"IMPULSE_QUEUED");}else vevent(v,"IMPULSE_QUEUE_FULL");}v->released=v->aiming=0;}
 if(f->has_user&&s->simulated&&s->physics.published==v->cfg.n&&!(v->cfg.profile==13&&s->render[7]==2)){BenchRecord e={0};e.qpc=vqpc();e.n=v->cfg.n;e.profile=v->cfg.profile;e.epoch=v->cfg.source_epoch;e.generation=f->generation;e.frame=f->sequence;e.impulse_entity=f->user_words[1];e.impulse_generation=f->user_words[2];memcpy(&e.impulse_x,f->user_words+4,4);memcpy(&e.impulse_y,f->user_words+5,4);e.impulse_serial=f->user_words[6];strcpy(e.event,"IMPULSE_COMMITTED");bench_log_push(&e);}else if(f->has_user&&s->simulated&&v->cfg.profile==13&&s->render[7]==2)vevent(v,"SHOT_BLOCKED_MOVING");
}
static int p_command(Viewer *v,VFrame *f){f->has_user=0;if(v->cfg.profile<12)return 1;uint32_t words[8]={0};if(v->impulse_pending){words[0]=PLAY_COMMAND_MAGIC;words[1]=v->impulse_entity;words[2]=v->impulse_generation;words[3]=v->cfg.source_epoch;memcpy(words+4,&v->impulse_x,4);memcpy(words+5,&v->impulse_y,4);if(v->impulse_serial>=0x7ffffffeu)return 0;words[6]=++v->impulse_serial;if(v->cfg.profile==13&&v->sandbox_shots)words[6]|=0x80000000u;words[7]=f->tick;v->impulse_pending=0;f->has_user=1;}
 uint32_t *mapped=s_map(v->d,f->user_command,0);VCHECK(mapped);memcpy(f->user_words,words,sizeof(words));memcpy(mapped,words,sizeof(words));VCHECK(s_unmap(v->d,f->user_command,sizeof(words)));return ph_user_command(v->p,f->user_command);
}
