// Device tests for G3 ownership; no simulated allocation success.
#include "physics.h"
#include <limits.h>
#include <math.h>
#include <stdio.h>
#define REQUIRE(x) do{if(!(x)){fprintf(stderr,"G3 device test line %d\n",__LINE__);return 0;}}while(0)
int ph_device_tests(StorageDevice *d,const uint64_t *base){
 PhysicsConfig c={32,32,64,64,1,2,4096,20,4096,8388608,1,UINT32_MAX,1.f/128,0};
 Memory before,after;REQUIRE(s_memory(d,&before));
 for(uint32_t index=0;index<10;index++){
  s_fail_after(d,index);Physics *p=ph_open(d,base,&c);REQUIRE(!p);s_fail_after(d,UINT32_MAX);
  REQUIRE(s_memory(d,&after)&&after.committed==before.committed&&s_retired_bytes(d)==0);
 }
 PhysicsConfig invalid=c;invalid.budget=1;REQUIRE(!ph_open(d,base,&invalid)&&ph_error()==2);
 invalid=c;invalid.contacts=UINT32_MAX;REQUIRE(!ph_open(d,base,&invalid));
 invalid=c;invalid.capacity=UINT32_MAX;REQUIRE(!ph_open(d,base,&invalid));
 invalid=c;invalid.dt=NAN;REQUIRE(!ph_open(d,base,&invalid));
 invalid=c;invalid.dt=0x1p-149f;REQUIRE(!ph_open(d,base,&invalid));
 REQUIRE(s_memory(d,&after)&&after.committed==before.committed);
 Physics *p=ph_open(d,base,&c);REQUIRE(p);REQUIRE(ph_scene(p));REQUIRE(ph_indirect_rejection_tests(p));
 PhysicsResult r={0};REQUIRE(!ph_tick(p,UINT32_MAX,&r));REQUIRE(ph_tick(p,0,&r));
 REQUIRE(!ph_tick(p,0,&r)&&!ph_tick(p,2,&r));REQUIRE(ph_tick(p,1,&r));
 REQUIRE(ph_fence_test(p));ph_close(p);
 REQUIRE(s_memory(d,&after)&&after.committed==before.committed&&s_retired_bytes(d)==0);
 return s_errors(d)==0;
}
