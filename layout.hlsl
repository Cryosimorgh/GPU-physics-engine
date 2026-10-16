// generated d22e4449ef31ef1fc3ab27fd610037cbd1f8c56ee864b4d2f1443aa18156a272
#define FIELDS 16u
#define TILE 32u
#define THREADS 256
#define COMMAND_CAPACITY 1024u
cbuffer C:register(b0){uint n;uint capacity;uint layout;uint strideActive;uint verify;uint stage;uint inputLayout;uint inputCapacity;uint scanCount;uint scanInput;uint scanOutput;uint scanParent;uint commandCount;uint epoch;uint unused0;uint unused1;};
uint address(uint kind,uint cap,uint i,uint field){return 4*(kind==0?i*FIELDS+field:kind==1?field*cap+i:(i/TILE)*(TILE*FIELDS)+field*TILE+i%TILE);}
uint item(uint3 group,uint lane){return (group.x+65535u*group.y)*THREADS+lane;}
uint prefixWords(uint cap){uint k=(cap+255)/256,sum=0;for(;;){sum+=2*k;if(k<=256)break;k=(k+255)/256;}return sum;}
static const uint record_bytes=64u;
static const uint guard_words=64u;
static const uint guard_bytes=256u;
static const uint command_capacity=1024u;
static const uint command_words=8u;
uint resourceBytes(uint slot,uint cap){switch(slot){case 0:return record_bytes*cap+guard_bytes;case 1:return 12*cap+guard_bytes;case 2:return 4*(2*cap+1)+guard_bytes;case 3:return 4*(prefixWords(cap)+guard_words+cap)+guard_bytes;case 4:return 32*cap+guard_bytes;case 5:return 28*cap+guard_bytes;case 6:return 4*(4+command_capacity)+guard_bytes;case 7:return max(record_bytes*cap,4*(4+command_capacity))+guard_bytes;case 8:return command_words*4*command_capacity;case 9:return record_bytes*cap;default:return 0;}}
