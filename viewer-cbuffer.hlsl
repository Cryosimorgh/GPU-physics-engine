// Generated viewer ABI SHA256 9c33e204f5e9cc0df35e8c1ca730cd5a811c061b0103e4cabbb7560aedb2e20f
#include "viewer-layout.h"
cbuffer Camera:register(b0){
uint objectCount;
uint entityCapacity;
uint visualStride;
uint instanceCount;
float cameraX;
float cameraY;
float halfWidth;
float halfHeight;
uint pixelWidth;
uint pixelHeight;
uint expectedGeneration;
uint renderFlags;
uint tableColumns;
uint tableCount;
uint expectedEpoch;
uint attemptTick;
float minPixelRadius;
float unused17;
float unused18;
float unused19;
uint unused20;
uint unused21;
uint unused22;
uint unused23;
uint unused24;
uint unused25;
uint unused26;
uint unused27;
uint unused28;
uint unused29;
uint unused30;
uint unused31;
};
uint cameraWord(uint index){
uint values[G4_V_CAMERA_WORDS]={objectCount,entityCapacity,visualStride,instanceCount,asuint(cameraX),asuint(cameraY),asuint(halfWidth),asuint(halfHeight),pixelWidth,pixelHeight,expectedGeneration,renderFlags,tableColumns,tableCount,expectedEpoch,attemptTick,asuint(minPixelRadius),asuint(unused17),asuint(unused18),asuint(unused19),unused20,unused21,unused22,unused23,unused24,unused25,unused26,unused27,unused28,unused29,unused30,unused31};return values[index];
}
