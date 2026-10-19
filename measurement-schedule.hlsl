// Bounded measurement-only canonicalization. No new buffers or production cap.
#ifndef G5_DETERMINISTIC_MEASURE
#define G5_DETERMINISTIC_MEASURE 0
#endif
#if G5_DETERMINISTIC_MEASURE
static const uint G5_MEASURE_MAX_BODIES=1024;
static const uint G5_MEASURE_MAX_CONTACTS=2048;
bool g5MeasureAllowed(){if(n>G5_MEASURE_MAX_BODIES||m.Load(8)>G5_MEASURE_MAX_CONTACTS||fixture!=0||(flags&~2u)!=0){fail(64);return false;}return true;}
bool g5KeyLess(uint4 a,uint4 b){return a.x!=b.x?a.x<b.x:a.y!=b.y?a.y<b.y:a.z!=b.z?a.z<b.z:a.w<b.w;}
void g5CanonicalContacts(){
 uint count=m.Load(8);
 // Insertion sort is intentionally bounded and timed, not a scalable engine
 // sort. Move complete records AND FP64 accumulated impulses together.
 for(uint i=1;i<count;i++){
  uint o=CT(CONTACT,i);uint4 r0=c.Load4(o),r1=c.Load4(o+16),r2=c.Load4(o+32),r3=c.Load4(o+48),r4=c.Load4(o+64);
  uint2 ln=c.Load2(CT(LAMBDA_N,i)),lt=c.Load2(CT(LAMBDA_T,i));uint j=i;
  while(j>0){
   if(!g5KeyLess(r4,c.Load4(CT(CONTACT,j-1)+64)))break;
   uint from=CT(CONTACT,j-1),to=CT(CONTACT,j);
   for(uint w=0;w<80;w+=16)c.Store4(to+w,c.Load4(from+w));
   c.Store2(CT(LAMBDA_N,j),c.Load2(CT(LAMBDA_N,j-1)));c.Store2(CT(LAMBDA_T,j),c.Load2(CT(LAMBDA_T,j-1)));j--;
  }
  o=CT(CONTACT,j);c.Store4(o,r0);c.Store4(o+16,r1);c.Store4(o+32,r2);c.Store4(o+48,r3);c.Store4(o+64,r4);
  c.Store2(CT(LAMBDA_N,j),ln);c.Store2(CT(LAMBDA_T,j),lt);
 }
}
void g5CanonicalMembers(){
 uint roots=0;
 for(uint i=0;i<n;i++)if(m.Load(AT(SIZE,i)))roots++;
 // The measurement contract is a single connected collision island. Other
 // shapes fail explicitly before publication instead of silently varying.
 if(roots!=1){fail(64);return;}
 for(uint i=0;i<n;i++)if(m.Load(AT(DEGREE,i))){
  uint r=m.Load(AT(PARENT,i)),rank=m.Load(AT(MEMBER_CURSOR,r));m.Store(AT(MEMBER_CURSOR,r),rank+1);
  uint64_t dst=get64(AT(MEMBER_START,r))+rank;if(dst>=n){fail(64);return;}
  m.Store(AT(MEMBERS,uint(dst)),i);m.Store(AT(LOCAL,i),rank);
 }
 for(uint r=0;r<n;r++)if(m.Load(AT(SIZE,r))){
  uint size=m.Load(AT(SIZE,r));if(size>max_bodies||m.Load(AT(CONTACT_COUNT,r))>max_work){fail(1);return;}
  m.Store(AT(ROOTS,0),r);m.Store(16,1);m.Store(24,1);m.Store(28,size);
 }
}
void g5CanonicalColorRanges(uint r){
 uint base=uint(get64(AT(COLOR_BASE,r))),colors=m.Load(AT(COLORS,r)),start=uint(get64(AT(CONTACT_START,r))),length=m.Load(AT(CONTACT_COUNT,r));
 if(base+colors+1>2*contact_capacity||start+length>contact_capacity){fail(64);return;}
 for(uint col=0;col<=colors;col++)c.Store(CT(COLOR_CURSOR,base+col),0);
 for(uint ci=start;ci<start+length;ci++){uint k=c.Load(CT(ROOT_CONTACTS,ci)),col=c.Load(CT(CONTACT,k)+52);if(col>=colors){fail(64);return;}uint at=CT(COLOR_CURSOR,base+col);c.Store(at,c.Load(at)+1);}
 uint prefix=start;
 for(uint col=0;col<colors;col++){uint len=c.Load(CT(COLOR_CURSOR,base+col));c.Store(CT(COLOR_START,base+col),prefix);c.Store(CT(COLOR_CURSOR,base+col),prefix);prefix+=len;}
 c.Store(CT(COLOR_START,base+colors),prefix);
 for(uint ci=start;ci<start+length;ci++){uint k=c.Load(CT(ROOT_CONTACTS,ci)),col=c.Load(CT(CONTACT,k)+52),cursor=CT(COLOR_CURSOR,base+col),at=c.Load(cursor);if(at>=contact_capacity){fail(64);return;}c.Store(cursor,at+1);c.Store(CT(COLORED,at),k);}
}
#endif
