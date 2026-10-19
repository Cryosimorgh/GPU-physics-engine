#pragma once
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <stdio.h>
// Native shader paths are anchored to the executable, never to caller CWD.
static FILE *bench_asset_open(const char *name) {
 wchar_t path[32768];DWORD n=GetModuleFileNameW(NULL,path,32768);
 if(!n||n>=32768)return NULL;
 while(n&&path[n-1]!=L'\\'&&path[n-1]!=L'/')n--;
 if(!n||!MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,name,-1,path+n,32768-n))return NULL;
 return _wfopen(path,L"rb");
}
