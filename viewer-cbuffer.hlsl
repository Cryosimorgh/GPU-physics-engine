// Generated viewer ABI SHA256 d94002db158c8103c59416988312cff095e8527bb603be0b989f0a7a659c37b1
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
float arenaWidth;
float arenaHeight;
float pickX;
float pickY;
uint selectedID;
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
uint values[G4_V_CAMERA_WORDS]={objectCount,entityCapacity,visualStride,instanceCount,asuint(cameraX),asuint(cameraY),asuint(halfWidth),asuint(halfHeight),pixelWidth,pixelHeight,expectedGeneration,renderFlags,tableColumns,tableCount,expectedEpoch,attemptTick,asuint(minPixelRadius),asuint(arenaWidth),asuint(arenaHeight),asuint(pickX),asuint(pickY),selectedID,unused22,unused23,unused24,unused25,unused26,unused27,unused28,unused29,unused30,unused31};return values[index];
}
