"""Deterministic scene-parameter proof; explicitly PLAN ONLY, no GPU claim."""
import itertools,json,math,struct
from pathlib import Path
r=Path(__file__).parent;s=json.loads((r/'billiards-schema.json').read_text())
def hash32(v):
 v^=s['seed'];v^=v>>16;v=(v*0x7feb352d)&0xffffffff;v^=v>>15;v=(v*0x846ca68b)&0xffffffff;return v^(v>>16)
def f32(x):return struct.unpack('<f',struct.pack('<f',x))[0]
def body(slot,profile):
 table,local=divmod(slot,16);h=hash32(table);x=.125+.375*(local%4);y=.125+.25*(local//4);vx=.25;vy=.125 if (h>>4)&1 else -.125
 if profile==9:
  vx+=(((hash32(slot)>>3)&3)-1)*.03125
  if local==15:x=1.5-.0625-1/512;vx=.5
 elif profile==10:
  pair=local//2;x=.1875+.375*(pair%4)+(-1 if local%2==0 else 1)*.078125;y=.25+.5*(pair//4);vx+=-.375 if local%2 else .375
 else:
  x=.75+((local%4)-1.5)*.140625;y=.5+((local//4)-1.5)*.140625
  if local<4+4*(h&3):vx+=.375 if local%4<2 else -.375;vy+=.25 if local//4<2 else -.25
  else:vx+=.125 if local%2 else -.125
 return tuple(map(f32,[x,y,vx,vy]))
def describe(n,profile):
 assert n in s['presets'].values() and profile in s['profiles'].values();tables=n//16;cap=(n+31)//32*32;cols=1
 while cols*cols<(cap+15)//16:cols*=2
 rows=(tables+cols-1)//cols;width=(min(cols,tables)-1)*4+1.5;height=(rows-1)*4+1
 return dict(kind='PLAN ONLY',n=n,capacity=cap,profile=profile,tables=tables,columns=cols,world_width=width,world_height=height,accessible_area=tables*1.5,accessible_area_occupancy=n*math.pi*s['radius']**2/(tables*1.5),bounding_area_occupancy=n*math.pi*s['radius']**2/(width*height),initial_velocity_component_range=[-.375,.625],dt=s['dt'],candidate_pair_reservation=tables*120,contact_reservation=tables*184,maximum_topological_island=16,external_force=s['drive'])
if __name__=='__main__':
 tests=[]
 for profile in s['profiles'].values():
  separation=math.inf;maxspeed=0
  for table in range(1024):
   b=[body(16*table+i,profile) for i in range(16)]
   for x,y,vx,vy in b:assert .0625<=x<=1.4375 and .0625<=y<=.9375;maxspeed=max(maxspeed,math.hypot(vx,vy))
   for a,b in itertools.combinations(b,2):separation=min(separation,math.hypot(a[0]-b[0],a[1]-b[1])-.125)
  assert separation>=0
  for n in s['presets'].values():tests.append(describe(n,profile)|dict(initial_minimum_surface_gap=separation,checked_table_seeds=1024,initial_max_speed=maxspeed,status='PASS'))
 result=dict(status='PASS',kind='PLAN ONLY',scene_version=s['version'],seed=s['seed'],cases=tests)
 (r/'evidence/g4-billiards-scene-plans.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
