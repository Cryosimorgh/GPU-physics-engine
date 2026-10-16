#pragma once
#define WIDL_C_INLINE_WRAPPERS
#define CINTERFACE
#define COBJMACROS
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <d3d12.h>
#include <d3d12sdklayers.h>
#include <dxgi1_6.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
/* Local ABI shim: no scheduling, simulation, containers, or third-party library. */
typedef struct GP {
 ID3D12Device *device; IDXGIAdapter1 *adapter; ID3D12CommandQueue *queue;
 ID3D12RootSignature *root; ID3D12PipelineState *pso[3];
 ID3D12Fence *fence; HANDLE event; UINT64 frequency; HRESULT err_hr;
 char name[256]; UINT vendor, device_id; UINT64 dedicated, budget;
 UINT feature_level, shader_model; ID3D12InfoQueue *info;
} GP;
typedef struct Slot {
 ID3D12CommandAllocator *allocator; ID3D12GraphicsCommandList *list;
 ID3D12QueryHeap *queries; ID3D12Resource *timestamps; ID3D12Resource *readback;
} Slot;
static inline void gp_release(void *p) { if(p) IUnknown_Release((IUnknown*)p); }
static inline int gp_ok(GP *g, HRESULT hr) { g->err_hr=hr; return SUCCEEDED(hr); }
static inline void gp_destroy(GP *g) {
 gp_release(g->info); for(int i=0;i<3;i++) gp_release(g->pso[i]);
 gp_release(g->root); gp_release(g->fence); gp_release(g->queue);
 gp_release(g->device); gp_release(g->adapter); if(g->event) CloseHandle(g->event);
 memset(g,0,sizeof(*g));
}
static inline int gp_init(GP *g, int requested, int debug) {
 memset(g,0,sizeof(*g)); IDXGIFactory6 *factory=NULL;
 if(debug) { ID3D12Debug *d=NULL; if(SUCCEEDED(D3D12GetDebugInterface(&IID_ID3D12Debug,(void**)&d))) {ID3D12Debug_EnableDebugLayer(d);ID3D12Debug1 *d1=NULL;if(SUCCEEDED(ID3D12Debug_QueryInterface(d,&IID_ID3D12Debug1,(void**)&d1))){ID3D12Debug1_SetEnableGPUBasedValidation(d1,debug!=0);gp_release(d1);}else{gp_release(d);g->err_hr=E_NOINTERFACE;return 0;}gp_release(d);} else {g->err_hr=E_NOINTERFACE;return 0;} }
 if(!gp_ok(g,CreateDXGIFactory2(0,&IID_IDXGIFactory6,(void**)&factory))) return 0;
 for(UINT i=0;;i++) {
  IDXGIAdapter1 *a=NULL; HRESULT hr=IDXGIFactory6_EnumAdapterByGpuPreference(factory,i,DXGI_GPU_PREFERENCE_HIGH_PERFORMANCE,&IID_IDXGIAdapter1,(void**)&a);
  if(hr==DXGI_ERROR_NOT_FOUND) break;
  if(FAILED(hr)) {g->err_hr=hr;break;}
  DXGI_ADAPTER_DESC1 desc; IDXGIAdapter1_GetDesc1(a,&desc);
  if((desc.Flags & DXGI_ADAPTER_FLAG_SOFTWARE) || (requested>=0 && i!=(UINT)requested)) {gp_release(a);continue;}
  hr=D3D12CreateDevice((IUnknown*)a,D3D_FEATURE_LEVEL_11_0,&IID_ID3D12Device,(void**)&g->device);
  if(FAILED(hr)) {gp_release(a);g->err_hr=hr;continue;}
  g->adapter=a; g->vendor=desc.VendorId;g->device_id=desc.DeviceId;g->dedicated=desc.DedicatedVideoMemory;
  WideCharToMultiByte(CP_UTF8,0,desc.Description,-1,g->name,sizeof(g->name),NULL,NULL); break;
 }
 gp_release(factory); if(!g->device) {if(SUCCEEDED(g->err_hr))g->err_hr=DXGI_ERROR_UNSUPPORTED;return 0;}
 IDXGIAdapter3 *a3=NULL; if(SUCCEEDED(IDXGIAdapter1_QueryInterface(g->adapter,&IID_IDXGIAdapter3,(void**)&a3))) {
  DXGI_QUERY_VIDEO_MEMORY_INFO m; if(SUCCEEDED(IDXGIAdapter3_QueryVideoMemoryInfo(a3,0,DXGI_MEMORY_SEGMENT_GROUP_LOCAL,&m)))g->budget=m.Budget;
  gp_release(a3);
 }
 D3D_FEATURE_LEVEL levels[]={D3D_FEATURE_LEVEL_12_2,D3D_FEATURE_LEVEL_12_1,D3D_FEATURE_LEVEL_12_0,D3D_FEATURE_LEVEL_11_1,D3D_FEATURE_LEVEL_11_0};
 D3D12_FEATURE_DATA_FEATURE_LEVELS fl={5,levels,0};
 if(!gp_ok(g,ID3D12Device_CheckFeatureSupport(g->device,D3D12_FEATURE_FEATURE_LEVELS,&fl,sizeof(fl))))return 0;
 g->feature_level=fl.MaxSupportedFeatureLevel;
 D3D12_FEATURE_DATA_SHADER_MODEL sm={D3D_SHADER_MODEL_6_0};
 if(!gp_ok(g,ID3D12Device_CheckFeatureSupport(g->device,D3D12_FEATURE_SHADER_MODEL,&sm,sizeof(sm)))||sm.HighestShaderModel<D3D_SHADER_MODEL_6_0)return 0;
 g->shader_model=sm.HighestShaderModel;
 D3D12_COMMAND_QUEUE_DESC q={0};q.Type=D3D12_COMMAND_LIST_TYPE_COMPUTE;
 if(!gp_ok(g,ID3D12Device_CreateCommandQueue(g->device,&q,&IID_ID3D12CommandQueue,(void**)&g->queue)))return 0;
 if(!gp_ok(g,ID3D12CommandQueue_GetTimestampFrequency(g->queue,&g->frequency)) || !g->frequency)return 0;
 if(!gp_ok(g,ID3D12Device_CreateFence(g->device,0,D3D12_FENCE_FLAG_NONE,&IID_ID3D12Fence,(void**)&g->fence)))return 0;
 g->event=CreateEventW(NULL,FALSE,FALSE,NULL);if(!g->event){g->err_hr=HRESULT_FROM_WIN32(GetLastError());return 0;}
 D3D12_ROOT_PARAMETER params[6]={0};
 for(UINT i=0;i<4;i++){params[i].ParameterType=D3D12_ROOT_PARAMETER_TYPE_UAV;params[i].Descriptor.ShaderRegister=i;params[i].ShaderVisibility=D3D12_SHADER_VISIBILITY_ALL;}
 params[4].ParameterType=D3D12_ROOT_PARAMETER_TYPE_32BIT_CONSTANTS;params[4].Constants.Num32BitValues=12;params[4].Constants.ShaderRegister=0;
 params[5].ParameterType=D3D12_ROOT_PARAMETER_TYPE_UAV;params[5].Descriptor.ShaderRegister=4;
 D3D12_ROOT_SIGNATURE_DESC rd={6,params,0,NULL,D3D12_ROOT_SIGNATURE_FLAG_NONE};
 ID3DBlob *blob=NULL,*err=NULL;HRESULT hr=D3D12SerializeRootSignature(&rd,D3D_ROOT_SIGNATURE_VERSION_1,&blob,&err);gp_release(err);
 if(!gp_ok(g,hr)){gp_release(blob);return 0;}
 hr=ID3D12Device_CreateRootSignature(g->device,0,ID3D10Blob_GetBufferPointer(blob),ID3D10Blob_GetBufferSize(blob),&IID_ID3D12RootSignature,(void**)&g->root);gp_release(blob);
 if(!gp_ok(g,hr))return 0;
 if(debug&&!gp_ok(g,ID3D12Device_QueryInterface(g->device,&IID_ID3D12InfoQueue,(void**)&g->info)))return 0;
 return 1;
}
static inline ID3D12Resource *gp_buffer(GP *g, UINT64 bytes, int kind) {
 D3D12_HEAP_PROPERTIES heap={0};heap.Type=kind==0?D3D12_HEAP_TYPE_DEFAULT:kind==1?D3D12_HEAP_TYPE_UPLOAD:D3D12_HEAP_TYPE_READBACK;heap.CreationNodeMask=heap.VisibleNodeMask=1;
 D3D12_RESOURCE_DESC d={0};d.Dimension=D3D12_RESOURCE_DIMENSION_BUFFER;d.Width=bytes;d.Height=1;d.DepthOrArraySize=1;d.MipLevels=1;d.SampleDesc.Count=1;d.Layout=D3D12_TEXTURE_LAYOUT_ROW_MAJOR;
 d.Flags=kind==0?D3D12_RESOURCE_FLAG_ALLOW_UNORDERED_ACCESS:D3D12_RESOURCE_FLAG_NONE;
 D3D12_RESOURCE_STATES state=kind==0?D3D12_RESOURCE_STATE_UNORDERED_ACCESS:kind==1?D3D12_RESOURCE_STATE_GENERIC_READ:D3D12_RESOURCE_STATE_COPY_DEST;
 ID3D12Resource *r=NULL; if(!gp_ok(g,ID3D12Device_CreateCommittedResource(g->device,&heap,D3D12_HEAP_FLAG_NONE,&d,state,NULL,&IID_ID3D12Resource,(void**)&r)))return NULL;return r;
}
static inline int gp_pipeline(GP *g, UINT i, const void *data, size_t size) {
 D3D12_COMPUTE_PIPELINE_STATE_DESC p={0};p.pRootSignature=g->root;p.CS.pShaderBytecode=data;p.CS.BytecodeLength=size;
 return gp_ok(g,ID3D12Device_CreateComputePipelineState(g->device,&p,&IID_ID3D12PipelineState,(void**)&g->pso[i]));
}
static inline void slot_destroy(Slot *s){gp_release(s->readback);gp_release(s->timestamps);gp_release(s->queries);gp_release(s->list);gp_release(s->allocator);memset(s,0,sizeof(*s));}
static inline int slot_init(GP *g,Slot *s,UINT64 readback_bytes) {
 memset(s,0,sizeof(*s));
 if(!gp_ok(g,ID3D12Device_CreateCommandAllocator(g->device,D3D12_COMMAND_LIST_TYPE_COMPUTE,&IID_ID3D12CommandAllocator,(void**)&s->allocator)))return 0;
 if(!gp_ok(g,ID3D12Device_CreateCommandList(g->device,0,D3D12_COMMAND_LIST_TYPE_COMPUTE,s->allocator,NULL,&IID_ID3D12GraphicsCommandList,(void**)&s->list)))return 0;
 if(!gp_ok(g,ID3D12GraphicsCommandList_Close(s->list)))return 0;
 D3D12_QUERY_HEAP_DESC q={D3D12_QUERY_HEAP_TYPE_TIMESTAMP,2,0};
 if(!gp_ok(g,ID3D12Device_CreateQueryHeap(g->device,&q,&IID_ID3D12QueryHeap,(void**)&s->queries)))return 0;
 s->timestamps=gp_buffer(g,16,2);if(!s->timestamps)return 0;
 if(readback_bytes){s->readback=gp_buffer(g,readback_bytes,2);if(!s->readback)return 0;}
 return 1;
}
static inline int slot_reset(GP *g,Slot *s){if(!gp_ok(g,ID3D12CommandAllocator_Reset(s->allocator)))return 0;return gp_ok(g,ID3D12GraphicsCommandList_Reset(s->list,s->allocator,NULL));}
static inline void gp_transition(Slot *s,ID3D12Resource *r,UINT before,UINT after){D3D12_RESOURCE_BARRIER b={0};b.Type=D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;b.Transition.pResource=r;b.Transition.Subresource=D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;b.Transition.StateBefore=before;b.Transition.StateAfter=after;ID3D12GraphicsCommandList_ResourceBarrier(s->list,1,&b);}
static inline void gp_barrier(Slot *s,ID3D12Resource *r){D3D12_RESOURCE_BARRIER b={0};b.Type=D3D12_RESOURCE_BARRIER_TYPE_UAV;b.UAV.pResource=r;ID3D12GraphicsCommandList_ResourceBarrier(s->list,1,&b);}
static inline void gp_copy(Slot *s,ID3D12Resource *to,ID3D12Resource *from,UINT64 bytes){ID3D12GraphicsCommandList_CopyBufferRegion(s->list,to,0,from,0,bytes);}
static inline void *gp_map(GP *g,ID3D12Resource *r,size_t bytes){void *p=NULL;D3D12_RANGE range={0,bytes};if(!gp_ok(g,ID3D12Resource_Map(r,0,&range,&p)))return NULL;return p;}
static inline void gp_unmap(ID3D12Resource *r,size_t written){D3D12_RANGE range={0,written};ID3D12Resource_Unmap(r,0,&range);}
static inline void gp_bind(GP *g,Slot *s,ID3D12Resource *a,ID3D12Resource *b,ID3D12Resource *c,UINT n,UINT neighbors,float dt){UINT config[4]={n,neighbors,0,0};memcpy(&config[2],&dt,4);ID3D12GraphicsCommandList_SetComputeRootSignature(s->list,g->root);ID3D12GraphicsCommandList_SetComputeRootUnorderedAccessView(s->list,0,ID3D12Resource_GetGPUVirtualAddress(a));ID3D12GraphicsCommandList_SetComputeRootUnorderedAccessView(s->list,1,ID3D12Resource_GetGPUVirtualAddress(b));ID3D12GraphicsCommandList_SetComputeRootUnorderedAccessView(s->list,2,ID3D12Resource_GetGPUVirtualAddress(c));ID3D12GraphicsCommandList_SetComputeRoot32BitConstants(s->list,3,4,config,0);}
static inline void gp_dispatch(GP *g,Slot *s,UINT pass,UINT count){ID3D12GraphicsCommandList_SetPipelineState(s->list,g->pso[pass]);ID3D12GraphicsCommandList_Dispatch(s->list,(count+255)/256,1,1);}
static inline void gp_stamp(Slot *s,UINT i){ID3D12GraphicsCommandList_EndQuery(s->list,s->queries,D3D12_QUERY_TYPE_TIMESTAMP,i);}
static inline void gp_resolve(Slot *s){ID3D12GraphicsCommandList_ResolveQueryData(s->list,s->queries,D3D12_QUERY_TYPE_TIMESTAMP,0,2,s->timestamps,0);}
static inline int gp_submit(GP *g,Slot *s,UINT64 value){if(!gp_ok(g,ID3D12GraphicsCommandList_Close(s->list)))return 0;ID3D12CommandList *lists[]={(ID3D12CommandList*)s->list};ID3D12CommandQueue_ExecuteCommandLists(g->queue,1,lists);HRESULT hr=ID3D12CommandQueue_Signal(g->queue,g->fence,value);if(!gp_ok(g,hr)){fprintf(stderr,"Queue Signal failed after Execute; fail-stop without releasing GPU-owned resources (0x%08lx).\n",(unsigned long)hr);ExitProcess(3);}return 1;}
static inline UINT64 gp_completed(GP *g){return ID3D12Fence_GetCompletedValue(g->fence);}
static inline int gp_wait(GP *g,UINT64 value){UINT64 v=gp_completed(g);if(v==UINT64_MAX){g->err_hr=ID3D12Device_GetDeviceRemovedReason(g->device);return 0;}if(v>=value)return 1;if(!gp_ok(g,ID3D12Fence_SetEventOnCompletion(g->fence,value,g->event)))return 0;DWORD result=WaitForSingleObject(g->event,30000);if(result!=WAIT_OBJECT_0){g->err_hr=result==WAIT_TIMEOUT?HRESULT_FROM_WIN32(WAIT_TIMEOUT):HRESULT_FROM_WIN32(GetLastError());return 0;}return gp_ok(g,ID3D12Device_GetDeviceRemovedReason(g->device));}
static inline UINT64 gp_validation_errors(GP *g){if(!g->info)return 0;UINT64 n=ID3D12InfoQueue_GetNumStoredMessagesAllowedByRetrievalFilter(g->info),bad=0;for(UINT64 i=0;i<n;i++){SIZE_T len=0;ID3D12InfoQueue_GetMessage(g->info,i,NULL,&len);D3D12_MESSAGE *m=(D3D12_MESSAGE*)HeapAlloc(GetProcessHeap(),0,len);if(m){if(SUCCEEDED(ID3D12InfoQueue_GetMessage(g->info,i,m,&len))&&(m->Severity==D3D12_MESSAGE_SEVERITY_ERROR||m->Severity==D3D12_MESSAGE_SEVERITY_CORRUPTION)){fprintf(stderr,"D3D12 validation: %s\n",m->pDescription);bad++;}HeapFree(GetProcessHeap(),0,m);}}return bad;}
static inline UINT64 gp_clock(void){LARGE_INTEGER t;QueryPerformanceCounter(&t);return t.QuadPart;}
static inline UINT64 gp_clock_frequency(void){LARGE_INTEGER t;QueryPerformanceFrequency(&t);return t.QuadPart;}

void c_reference(void *state,void *interactions,void *forces,uint32_t count,uint32_t neighbors,float dt);

static inline int p2_queue(GP *g,int direct){if(!direct)return 1;gp_release(g->queue);g->queue=NULL;D3D12_COMMAND_QUEUE_DESC q={0};q.Type=D3D12_COMMAND_LIST_TYPE_DIRECT;if(!gp_ok(g,ID3D12Device_CreateCommandQueue(g->device,&q,&IID_ID3D12CommandQueue,(void**)&g->queue)))return 0;return gp_ok(g,ID3D12CommandQueue_GetTimestampFrequency(g->queue,&g->frequency));}
static inline int p2_slot(GP *g,Slot *s,int direct){memset(s,0,sizeof(*s));D3D12_COMMAND_LIST_TYPE type=direct?D3D12_COMMAND_LIST_TYPE_DIRECT:D3D12_COMMAND_LIST_TYPE_COMPUTE;if(!gp_ok(g,ID3D12Device_CreateCommandAllocator(g->device,type,&IID_ID3D12CommandAllocator,(void**)&s->allocator)))return 0;if(!gp_ok(g,ID3D12Device_CreateCommandList(g->device,0,type,s->allocator,NULL,&IID_ID3D12GraphicsCommandList,(void**)&s->list)))return 0;if(!gp_ok(g,ID3D12GraphicsCommandList_Close(s->list)))return 0;D3D12_QUERY_HEAP_DESC q={D3D12_QUERY_HEAP_TYPE_TIMESTAMP,5,0};if(!gp_ok(g,ID3D12Device_CreateQueryHeap(g->device,&q,&IID_ID3D12QueryHeap,(void**)&s->queries)))return 0;s->timestamps=gp_buffer(g,40,2);return s->timestamps!=NULL;}
static inline void p2_bind(GP *g,Slot *s,ID3D12Resource *a,ID3D12Resource *b,ID3D12Resource *grid,ID3D12Resource *cpu,const UINT *constants){ID3D12GraphicsCommandList_SetComputeRootSignature(s->list,g->root);ID3D12Resource *r[]={a,b,grid,cpu};for(UINT i=0;i<4;i++)ID3D12GraphicsCommandList_SetComputeRootUnorderedAccessView(s->list,i,ID3D12Resource_GetGPUVirtualAddress(r[i]));ID3D12GraphicsCommandList_SetComputeRoot32BitConstants(s->list,4,12,constants,0);}
static inline int p2_pso(GP *g,const void *data,size_t size,ID3D12PipelineState **out){D3D12_COMPUTE_PIPELINE_STATE_DESC p={0};p.pRootSignature=g->root;p.CS.pShaderBytecode=data;p.CS.BytecodeLength=size;return gp_ok(g,ID3D12Device_CreateComputePipelineState(g->device,&p,&IID_ID3D12PipelineState,(void**)out));}
static inline void p2_dispatch(Slot *s,ID3D12PipelineState *p,UINT groups){ID3D12GraphicsCommandList_SetPipelineState(s->list,p);ID3D12GraphicsCommandList_Dispatch(s->list,groups,1,1);}
static inline int p2_calibrate(GP *g,UINT64 *gpu,UINT64 *cpu){return gp_ok(g,ID3D12CommandQueue_GetClockCalibration(g->queue,gpu,cpu));}
static inline UINT64 p2_usage(GP *g){IDXGIAdapter3 *a=NULL;DXGI_QUERY_VIDEO_MEMORY_INFO m={0};if(SUCCEEDED(IDXGIAdapter1_QueryInterface(g->adapter,&IID_IDXGIAdapter3,(void**)&a))){IDXGIAdapter3_QueryVideoMemoryInfo(a,0,DXGI_MEMORY_SEGMENT_GROUP_LOCAL,&m);gp_release(a);}return m.CurrentUsage;}
static inline ID3D12Heap *p2_heap(GP *g,UINT64 bytes){D3D12_HEAP_DESC h={0};h.SizeInBytes=bytes;h.Properties.Type=D3D12_HEAP_TYPE_DEFAULT;h.Properties.CreationNodeMask=h.Properties.VisibleNodeMask=1;h.Flags=D3D12_HEAP_FLAG_ALLOW_ONLY_BUFFERS;ID3D12Heap *out=NULL;if(!gp_ok(g,ID3D12Device_CreateHeap(g->device,&h,&IID_ID3D12Heap,(void**)&out)))return NULL;return out;}
static inline ID3D12Resource *p2_placed(GP *g,ID3D12Heap *heap,UINT64 offset,UINT64 bytes){D3D12_RESOURCE_DESC d={0};d.Dimension=D3D12_RESOURCE_DIMENSION_BUFFER;d.Width=bytes;d.Height=1;d.DepthOrArraySize=1;d.MipLevels=1;d.SampleDesc.Count=1;d.Layout=D3D12_TEXTURE_LAYOUT_ROW_MAJOR;d.Flags=D3D12_RESOURCE_FLAG_ALLOW_UNORDERED_ACCESS;ID3D12Resource *out=NULL;if(!gp_ok(g,ID3D12Device_CreatePlacedResource(g->device,heap,offset,&d,D3D12_RESOURCE_STATE_UNORDERED_ACCESS,NULL,&IID_ID3D12Resource,(void**)&out)))return NULL;return out;}
static inline void p2_alias(Slot *s,ID3D12Resource *before,ID3D12Resource *after){D3D12_RESOURCE_BARRIER b={0};b.Type=D3D12_RESOURCE_BARRIER_TYPE_ALIASING;b.Aliasing.pResourceBefore=before;b.Aliasing.pResourceAfter=after;ID3D12GraphicsCommandList_ResourceBarrier(s->list,1,&b);}

static inline int p2_remove(GP *g){ID3D12Device5 *d=NULL;if(FAILED(ID3D12Device_QueryInterface(g->device,&IID_ID3D12Device5,(void**)&d)))return 0;ID3D12Device5_RemoveDevice(d);gp_release(d);return ID3D12Device_GetDeviceRemovedReason(g->device)!=S_OK;}

static inline UINT64 p2_cpu_time(void){FILETIME c,e,k,u;GetProcessTimes(GetCurrentProcess(),&c,&e,&k,&u);return (((UINT64)k.dwHighDateTime<<32)|k.dwLowDateTime)+(((UINT64)u.dwHighDateTime<<32)|u.dwLowDateTime);}

static inline int p2_submit(GP *g,Slot *s,UINT64 value,UINT64 *submitted){if(!gp_ok(g,ID3D12GraphicsCommandList_Close(s->list)))return 0;ID3D12CommandList *list=(ID3D12CommandList*)s->list;*submitted=gp_clock();ID3D12CommandQueue_ExecuteCommandLists(g->queue,1,&list);if(!gp_ok(g,ID3D12CommandQueue_Signal(g->queue,g->fence,value)))ExitProcess(3);return 1;}

static inline ID3D12CommandSignature *p3_signature(GP *g){D3D12_INDIRECT_ARGUMENT_DESC arg={0};arg.Type=D3D12_INDIRECT_ARGUMENT_TYPE_DISPATCH;D3D12_COMMAND_SIGNATURE_DESC desc={0};desc.ByteStride=12;desc.NumArgumentDescs=1;desc.pArgumentDescs=&arg;ID3D12CommandSignature *out=NULL;if(!gp_ok(g,ID3D12Device_CreateCommandSignature(g->device,&desc,NULL,&IID_ID3D12CommandSignature,(void**)&out)))return NULL;return out;}
static inline void p3_indirect(Slot *s,ID3D12PipelineState *p,ID3D12CommandSignature *sig,ID3D12Resource *args){ID3D12GraphicsCommandList_SetPipelineState(s->list,p);ID3D12GraphicsCommandList_ExecuteIndirect(s->list,sig,1,args,0,args,12);}
static inline void p3_args(Slot *s,ID3D12Resource *args){ID3D12GraphicsCommandList_SetComputeRootUnorderedAccessView(s->list,5,ID3D12Resource_GetGPUVirtualAddress(args));}

static inline void p3_resolve_profile(Slot *s){ID3D12GraphicsCommandList_ResolveQueryData(s->list,s->queries,D3D12_QUERY_TYPE_TIMESTAMP,2,3,s->timestamps,16);}
