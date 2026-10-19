// Spare bytes 448..511 of the existing pool extension; no allocation growth.
// Off in normal builds, no writes during accepted ticks. The init kernel clears
// the latch once. The first failing GPU atomic claimant owns the entire payload.
#ifndef G6_POOL_FAILURE_DIAGNOSTICS
#define G6_POOL_FAILURE_DIAGNOSTICS 0
#endif
void poolFault(uint code,uint a,uint b,uint contact,uint detail,double value,double limit,double auxiliary0,double auxiliary1,uint extra0,uint extra1){
#if G6_POOL_FAILURE_DIAGNOSTICS
 if(fixture!=13u)return;uint at=poolBase()+POOL_FAILURE_DIAGNOSTIC_OFFSET,previous;
 m.InterlockedCompareExchange(at,0,code,previous);if(previous!=0)return;
 m.Store4(at+4,uint4(tick,a,b,contact));m.Store(at+20,detail);
 mdstore(at+24,value);mdstore(at+32,limit);mdstore(at+40,auxiliary0);mdstore(at+48,auxiliary1);
 m.Store2(at+56,uint2(extra0,extra1));
#endif
}
