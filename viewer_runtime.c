// Specialized native viewer shares the existing allocator and D3D12 ABI.
// It is compiled instead of runtime.c, never together with it.
#include "runtime.c"
#include "viewer.c"
