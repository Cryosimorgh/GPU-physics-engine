// Hand-defined 3x5 control font. Fixed bounded per-frame upload; no entity data.
#include "hud-digits.h"
#include "viewer-layout.h"
#define G4_HUD_PIXELS G4_V_HUD_PIXELS
#define G4_HUD_BYTES ((uint64_t)G4_V_HUD_PIXEL_STRIDE*G4_HUD_PIXELS)
typedef struct HudPixel {uint32_t position,color;} HudPixel;
_Static_assert(sizeof(HudPixel)==G4_V_HUD_PIXEL_STRIDE,"HUD ABI");
static uint32_t hud_glyph(char ch){static const uint32_t digits[10]=G4_HUD_DIGIT_BITS;if(ch>='0'&&ch<='9')return digits[ch-'0'];
 const char *alphabet="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ.-/:=+";
 const char *rows[]={"111101101101111","010110010010111","111001111100111","111001111001111","101101111001001","111100111001111","111100111101111","111001010010010","111101111101111","111101111001111",
 "010101111101101","110101110101110","011100100100011","110101101101110","111100110100111","111100110100100","011100101101011","101101111101101","111010010010111","001001001101010","101101110101101","100100100100111","101111111101101","101111111111101","010101101101010","110101110100100","010101101111011","110101110101101","011100010001110","111010010010010","101101101101111","101101101101010","101101111111101","101101010101101","101101010010010","111001010100111",
 "000000000000010","000000111000000","001001010100100","000010000010000","000111000111000","000010111010000"};
 const char *found=strchr(alphabet,ch);if(!found)return 0;uint32_t bits=0;const char *s=rows[found-alphabet];for(UINT i=0;i<15;i++)if(s[i]=='1')bits|=1u<<i;return bits;
}
static uint32_t hud_text(HudPixel *pixels,uint32_t count,uint32_t x,uint32_t y,const char *text){
 for(const char *s=text;*s;s++,x+=8){uint32_t bits=hud_glyph(*s);for(UINT i=0;i<15;i++)if(bits&(1u<<i)){if(count>=G4_HUD_PIXELS)return 0;uint32_t px=x+2*(i%3),py=y+2*(i/3);if(px>65534||py>65534)return 0;pixels[count++]=(HudPixel){px|(py<<16),0xe8e8d8u};}}
 return count;
}
