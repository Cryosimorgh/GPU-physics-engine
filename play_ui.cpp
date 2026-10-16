#include "play_ui.h"
#include <windows.h>
#include <cstdio>
#include <cmath>
#include <cfloat>
#include <d3d12.h>
#include <dxgi1_6.h>
#include "third_party/imgui/imgui.h"
#include "third_party/imgui/backends/imgui_impl_win32.h"
// Include the pinned DX12 backend to audit its concrete owned allocations.
#include "third_party/imgui/backends/imgui_impl_dx12.cpp"
extern IMGUI_IMPL_API LRESULT ImGui_ImplWin32_WndProcHandler(HWND,UINT,WPARAM,LPARAM);
struct PlayUI{ImGuiContext *context;ID3D12Device *device;ID3D12DescriptorHeap *heap;float frame[240],physics[240];uint32_t cursor;double last;};
static void context(PlayUI *u){ImGui::SetCurrentContext(u->context);}
PlayUI *play_ui_open(void *window,void *device){PlayUI *u=new PlayUI{};u->device=(ID3D12Device*)device;u->context=ImGui::CreateContext();context(u);ImGuiIO &io=ImGui::GetIO();io.IniFilename=nullptr;io.LogFilename=nullptr;
 char font[MAX_PATH];GetWindowsDirectoryA(font,MAX_PATH);strcat_s(font,"\\Fonts\\segoeui.ttf");if(GetFileAttributesA(font)!=INVALID_FILE_ATTRIBUTES)io.Fonts->AddFontFromFileTTF(font,16);else io.Fonts->AddFontDefault();
 ImGui::StyleColorsDark();ImGuiStyle &s=ImGui::GetStyle();s.WindowRounding=12;s.FrameRounding=6;s.GrabRounding=6;s.WindowPadding=ImVec2(18,16);s.ItemSpacing=ImVec2(10,4);s.Colors[ImGuiCol_WindowBg]=ImVec4(.045f,.065f,.10f,.96f);s.Colors[ImGuiCol_Header]=ImVec4(.08f,.28f,.35f,1);s.Colors[ImGuiCol_Button]=ImVec4(.08f,.30f,.38f,1);s.Colors[ImGuiCol_ButtonHovered]=ImVec4(.10f,.46f,.53f,1);s.Colors[ImGuiCol_CheckMark]=ImVec4(.25f,.90f,.75f,1);s.Colors[ImGuiCol_PlotLines]=ImVec4(.25f,.85f,.73f,1);
 D3D12_DESCRIPTOR_HEAP_DESC h={};h.Type=D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV;h.NumDescriptors=1;h.Flags=D3D12_DESCRIPTOR_HEAP_FLAG_SHADER_VISIBLE;
 if(FAILED(u->device->CreateDescriptorHeap(&h,IID_PPV_ARGS(&u->heap)))||!ImGui_ImplWin32_Init(window)||!ImGui_ImplDX12_Init(u->device,3,DXGI_FORMAT_B8G8R8A8_UNORM,u->heap,u->heap->GetCPUDescriptorHandleForHeapStart(),u->heap->GetGPUDescriptorHandleForHeapStart())||!ImGui_ImplDX12_CreateDeviceObjects()){play_ui_close(u);return nullptr;}return u;
}
int play_ui_event(PlayUI *u,void *w,uint32_t m,uint64_t a,int64_t b){context(u);return (int)ImGui_ImplWin32_WndProcHandler((HWND)w,m,(WPARAM)a,(LPARAM)b);}
int play_ui_mouse(PlayUI *u){context(u);return ImGui::GetIO().WantCaptureMouse;}
int play_ui_keyboard(PlayUI *u){context(u);return ImGui::GetIO().WantCaptureKeyboard;}
static void metric(const char *name,const char *format,double value){ImGui::TextDisabled("%s",name);ImGui::SameLine(156);ImGui::Text(format,value);}
int play_ui_draw(PlayUI *u,void *list,PlayStats *s){context(u);ImGui_ImplDX12_NewFrame();ImGui_ImplWin32_NewFrame();ImGui::NewFrame();s->command=0;s->strength=s->impulse_strength;
 if(!s->hidden){
 if(ImGui::BeginMainMenuBar()){
  if(ImGui::BeginMenu("Scene")){if(ImGui::MenuItem("Playground",nullptr,s->profile==12))s->command=160;if(ImGui::BeginMenu("Scientific Benchmarks")){const char *names[]={"Sparse - independent 16-ball tables","Mixed - independent 16-ball tables","Clustered - independent 16-ball tables"};for(int i=0;i<3;i++)if(ImGui::MenuItem(names[i],nullptr,s->profile==9+i))s->command=121+i;ImGui::EndMenu();}ImGui::EndMenu();}
  if(ImGui::BeginMenu("Population")){if(s->profile==12){if(ImGui::MenuItem("100 / preview"))s->command=113;if(ImGui::MenuItem("1,000 / preview"))s->command=114;}if(ImGui::MenuItem("10,000"))s->command=110;if(ImGui::MenuItem("100,000"))s->command=111;if(ImGui::MenuItem("1,000,000"))s->command=112;ImGui::EndMenu();}
  if(ImGui::BeginMenu("Physics")){if(ImGui::MenuItem(s->paused?"Resume":"Pause","Space"))s->command=100;if(ImGui::MenuItem("Step","."))s->command=101;if(ImGui::MenuItem("Reset seed 18228","R"))s->command=102;if(ImGui::MenuItem("Faster pacing","+"))s->command=130;if(ImGui::MenuItem("Slower pacing","-"))s->command=131;ImGui::EndMenu();}
  if(ImGui::BeginMenu("Recording")){if(ImGui::MenuItem(s->recording?"Stop recording":"Start recording","F9"))s->command=104;if(ImGui::MenuItem("Save / flush","F10"))s->command=105;if(ImGui::MenuItem("Screenshot","F12"))s->command=170;ImGui::EndMenu();}
  if(ImGui::BeginMenu("Settings")){if(ImGui::MenuItem("Overview","Home"))s->command=150;if(ImGui::MenuItem("Focus selected","F",false,s->selected!=UINT32_MAX))s->command=161;if(ImGui::MenuItem("Clean view","H"))s->command=103;if(ImGui::MenuItem("Toggle VSync"))s->command=152;for(int i=1;i<=3;i++){char label[48];snprintf(label,sizeof(label),"%d frames in flight",i);if(ImGui::MenuItem(label,nullptr,s->depth==(unsigned)i))s->command=140+i;}ImGui::EndMenu();}
  ImGui::SameLine();ImGui::TextDisabled("    GPU / PHYSICS PLAYGROUND");ImGui::EndMainMenuBar();}
 ImGui::SetNextWindowPos(ImVec2((float)s->width-306,46),ImGuiCond_Always);ImGui::SetNextWindowSize(ImVec2(288,(float)s->height-64),ImGuiCond_Always);
 if(ImGui::Begin("Live statistics",nullptr,ImGuiWindowFlags_NoMove|ImGuiWindowFlags_NoResize)){
 ImGui::TextColored(ImVec4(.3f,.9f,.77f,1),"%s",s->paused?"PAUSED":"SIMULATION RUNNING");ImGui::TextDisabled("2D disks / shaded sphere rendering");ImGui::Separator();
 if(ImGui::CollapsingHeader("Performance",ImGuiTreeNodeFlags_DefaultOpen)){metric("Physics ticks/s","%.1f",s->tps);metric("Render FPS","%.1f",s->fps);metric("GPU physics","%.2f ms",s->physics_ms);metric("GPU render","%.2f ms",s->render_ms);metric("CPU frame","%.2f ms",s->cpu_ms);metric("CPU submission","%.2f ms",s->submit_ms);metric("Present calls/s","%.1f",s->fps);metric("Present blocking","%.2f ms",s->present_ms);ImGui::TextDisabled("Display FPS: UNVERIFIED");}
 if(ImGui::CollapsingHeader("Workload",ImGuiTreeNodeFlags_DefaultOpen)){metric("Simulated balls","%.0f",s->n);metric("Rendered instances","%.0f",s->rendered);metric("Visual fraction","%.3f",(double)s->rendered/s->n);metric("Active balls","%.0f",s->active);metric("Contact constraints","%.0f",s->contacts);metric("Collision islands","%.0f",s->islands);metric("Largest island","%.0f",s->largest);if(s->profile!=12)ImGui::TextWrapped("Scientific preset: independent 16-ball tables.");}
 if(ImGui::CollapsingHeader("Memory & safety")){metric("DXGI usage","%.0f MiB",s->memory);metric("Current budget","%.0f MiB",s->budget);metric("Peak usage","%.0f MiB",s->peak);metric("Frames in flight","%.0f",s->backlog);metric("Rejected changes","%.0f",s->rejected);metric("Validation flags","%.0f",s->errors);ImGui::TextWrapped("Fixed dt 1/128. Existing checked G4 publication; no new strict snapshot claim.");}
 if(ImGui::CollapsingHeader("Interaction",ImGuiTreeNodeFlags_DefaultOpen)){ImGui::TextDisabled("Impulse strength");ImGui::SetNextItemWidth(-1);ImGui::SliderFloat("##impulse",&s->strength,.1f,3.f,"%.2f");if(s->selected!=UINT32_MAX)ImGui::Text("Selected ball %u",s->selected);else ImGui::TextDisabled("Left-click a ball to select");ImGui::TextWrapped("Drag to aim, release to strike. Right-drag to pan. Wheel to zoom. F to focus. Space to pause. Period to step.");}
 }ImGui::End();
 u->frame[u->cursor%240]=(float)s->cpu_ms;u->physics[u->cursor%240]=(float)s->physics_ms;u->cursor++;
 ImGui::SetNextWindowPos(ImVec2(18,(float)s->height-138),ImGuiCond_Always);ImGui::SetNextWindowSize(ImVec2((float)s->width-342,120),ImGuiCond_Always);
 if(ImGui::Begin("Frame timing",nullptr,ImGuiWindowFlags_NoMove|ImGuiWindowFlags_NoResize)){ImGui::Text("GPU physics p50 %.2f   p95 %.2f   p99 %.2f ms",s->p50,s->p95,s->p99);float width=(ImGui::GetContentRegionAvail().x-16)*.5f;ImGui::TextDisabled("CPU frame                                      GPU physics tick");ImGui::PlotLines("##CPU",u->frame,240,u->cursor%240,nullptr,0,FLT_MAX,ImVec2(width,40));ImGui::SameLine();ImGui::PlotLines("##GPU",u->physics,240,u->cursor%240,nullptr,0,FLT_MAX,ImVec2(width,40));}ImGui::End();
 auto draw=ImGui::GetForegroundDrawList();if(s->aiming&&s->selected!=UINT32_MAX){float scale=s->height/(2*s->half_height);ImVec2 start((s->selected_x-s->camera_x)*scale+s->width*.5f,(s->camera_y-s->selected_y)*scale+s->height*.5f),end(s->aim_x,s->aim_y);draw->AddCircle(start,14,IM_COL32(89,235,207,255),32,2);draw->AddLine(start,end,IM_COL32(89,235,207,255),3);float dx=end.x-start.x,dy=end.y-start.y,len=sqrtf(dx*dx+dy*dy);char magnitude[64];snprintf(magnitude,sizeof(magnitude),"Impulse dv %.2f",fminf(1.5f,len/scale*s->impulse_strength));draw->AddText(ImVec2(end.x+10,end.y-24),IM_COL32(140,255,221,255),magnitude);if(len>8){dx/=len;dy/=len;draw->AddTriangleFilled(end,ImVec2(end.x-dx*15-dy*7,end.y-dy*15+dx*7),ImVec2(end.x-dx*15+dy*7,end.y-dy*15-dx*7),IM_COL32(89,235,207,255));}}
 }
 ImGui::Render();auto data=ImGui::GetDrawData();if(data->TotalVtxCount>20000||data->TotalIdxCount>60000)return 0;auto cmd=(ID3D12GraphicsCommandList*)list;cmd->SetDescriptorHeaps(1,&u->heap);ImGui_ImplDX12_RenderDrawData(data,cmd);return 1;
}
uint64_t play_ui_memory(PlayUI *u){context(u);auto b=ImGui_ImplDX12_GetBackendData();uint64_t total=0;auto charge=[&](ID3D12Resource *p){if(p){auto desc=p->GetDesc();total+=u->device->GetResourceAllocationInfo(0,1,&desc).SizeInBytes;}};if(b){charge(b->pFontTextureResource);for(unsigned i=0;i<b->numFramesInFlight;i++){charge(b->pFrameResources[i].IndexBuffer);charge(b->pFrameResources[i].VertexBuffer);}}return total;}
void play_ui_close(PlayUI *u){if(!u)return;context(u);if(ImGui::GetIO().BackendRendererUserData)ImGui_ImplDX12_Shutdown();if(ImGui::GetIO().BackendPlatformUserData)ImGui_ImplWin32_Shutdown();if(u->heap)u->heap->Release();ImGui::DestroyContext(u->context);delete u;}
