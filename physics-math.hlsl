// DXIL 6.0 has no f64 sqrt intrinsic. Newton refinement remains binary64.
// The exponent seed covers the complete normal-double range; source f32
// coordinates/velocities squared are normal double (or exactly zero).
double dsqrt(double value){if(value==0.0)return 0.0;if(!(value>0.0))return value;uint low,high;asuint(value,low,high);uint exponent=(high>>20)&2047u;if(exponent==2047u)return value;bool subnormal=exponent==0;if(subnormal){value*=18446744073709551616.0;asuint(value,low,high);exponent=(high>>20)&2047u;}double x=asdouble(0u,((exponent+1023u)/2u)<<20);for(uint i=0;i<7;i++)x=.5*(x+value/x);return subnormal?x/4294967296.0:x;}
// Algebraically identical projected-KKT distances without subtracting a
// small q/kn from a much larger accumulated impulse.
double normalResidual(double q,double kn,double ln){return kn>0?(q>=0?min(q,max(0.0,ln)*kn):-q):max(0.0,-q);}
double tangentResidual(double vt,double kt,double ln,double lt){double bound=.25*ln;return kt>0?(vt>=0?min(vt,max(0.0,lt+bound)*kt):min(-vt,max(0.0,bound-lt)*kt)):abs(lt);}
