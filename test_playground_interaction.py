"""Drive actual native picking/impulses, then independently inspect GPU state."""
from pathlib import Path
import ctypes as C
from ctypes import wintypes as W
import json,subprocess,time,struct,math,datetime
from PIL import ImageGrab
r=Path(__file__).parent.resolve();out=r/'playground-test-results'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ');out.mkdir(parents=True)
u=C.windll.user32;u.PostMessageW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM];u.IsWindowVisible.argtypes=[W.HWND];u.GetClientRect.argtypes=[W.HWND,C.POINTER(W.RECT)];u.GetWindowRect.argtypes=[W.HWND,C.POINTER(W.RECT)];u.SetForegroundWindow.argtypes=[W.HWND];u.ClientToScreen.argtypes=[W.HWND,C.POINTER(W.POINT)]
cb=C.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
def find(p):
 for _ in range(400):
  found=[]
  @cb
  def f(h,_):
   pid=W.DWORD();u.GetWindowThreadProcessId(h,C.byref(pid))
   if pid.value==p.pid and u.IsWindowVisible(h):found.append(h)
   return True
  u.EnumWindows(f,0)
  if found:return found[-1]
  assert p.poll() is None;time.sleep(.05)
 raise TimeoutError('window')
def shot(h,name):
 u.SetForegroundWindow(h);time.sleep(.2);rect=W.RECT();u.GetWindowRect(h,C.byref(rect));ImageGrab.grab(bbox=(rect.left,rect.top,rect.right,rect.bottom)).save(out/(name+'.png'))
states=[]
for impulse in [False,True]:
 base=out/('impulse' if impulse else 'control');base.mkdir();f=(base/'run.log').open('w');p=subprocess.Popen([str(r/'zig-out/bin/GPUPhysicsPlayground.exe'),'--quiet','--self-test','30','--output-dir',str(base)],cwd=r,stdout=f,stderr=subprocess.STDOUT)
 try:
  h=find(p);time.sleep(.6)
  if impulse:
   shot(h,'first-launch-paused');rect=W.RECT();u.GetClientRect(h,C.byref(rect));w,hg=rect.right,rect.bottom;half=max(2.375*.67,2.375*.64*hg/max(200,w-330));cx=2.375*.5+310*half/hg;cy=2.375*.5-100*half/hg;scale=hg/(2*half);x=round((.25-cx)*scale+w*.5);y=round((cy-.25)*scale+hg*.5)
   point=W.POINT(x,y);u.ClientToScreen(h,C.byref(point));u.SetCursorPos(point.x,point.y);time.sleep(.2)
   u.PostMessageW(h,0x201,1,x|(y<<16));time.sleep(.35);u.SetCursorPos(point.x+200,point.y);u.PostMessageW(h,0x200,1,(x+200)|(y<<16));time.sleep(.3);shot(h,'aiming');u.PostMessageW(h,0x202,0,(x+200)|(y<<16));time.sleep(.3)
  u.PostMessageW(h,0x100,0xbe,0);time.sleep(.4)
  if impulse:u.PostMessageW(h,0x100,0x46,0);time.sleep(.25)
  shot(h,'collision-after-impulse' if impulse else 'control');u.PostMessageW(h,0x10,0,0);assert p.wait(timeout=60)==0
 finally:
  if p.poll() is None:p.kill();p.wait()
  f.close()
 session=next(base.glob('session-*'));scene=json.loads((session/'scene-1.json').read_text());data=(session/'final-state.bin').read_bytes();floats=struct.unpack('<'+'f'*(len(data)//4),data);records=json.loads((session/'samples.json').read_text())['records'];frames=[x for x in records if x['type']=='FRAME'];assert sum(x['simulated'] for x in frames)==1
 completed=next(i for i,x in enumerate(frames) if x['simulated']);assert all(x['contacts']==frames[completed]['contacts'] and x['active']==100 for x in frames[completed:]),'Paused workload statistics must retain the last completed physics tick'
 states.append((scene['capacity'],floats,records,scene))
cap,a,_,_=states[0];cap2,b,records,_=states[1];assert cap==cap2
events=[x['type'] for x in records];assert 'BALL_SELECTED' in events and 'IMPULSE_COMMITTED' in events,events
delta=[b[2*cap+i]-a[2*cap+i] for i in range(100)];assert delta[0]>.1 and delta[1]>.05,delta[:4]
momentum=sum(delta);assert .5<momentum<1.51,momentum
packet=next(x for x in records if x['type']=='IMPULSE_COMMITTED');assert packet['impulse_entity']==0 and packet['impulse_generation']==1
assert abs(momentum-packet['impulse_x'])<2e-6,(momentum,packet)
assert abs(delta[0]+delta[1]-packet['impulse_x'])<2e-6
assert all(abs(x)<2e-6 for x in delta[2:]),delta[2:]
# Both bodies must move according to their solved final velocity and one dt.
for i in range(100):
 col=i%10;row=i//10;x=.25+(col//2)*.375+(col%2)*.1328125;y=.25+row*.1875
 assert abs(b[i]-(x+b[2*cap+i]/128))<1e-6
 assert abs(b[cap+i]-(y+b[3*cap+i]/128))<1e-6
for i in range(100):
 for j in range(i):assert math.hypot(b[i]-b[j],b[cap+i]-b[cap+j])>=.125-2e-6
result=dict(status='PASS',n=100,actual_ticks_per_case=1,selected_body_velocity_delta=delta[0],neighbor_velocity_delta=delta[1],total_external_x_momentum=momentum,full_position_update_coverage=100,exhaustive_no_overlap_pairs=4950,impulse_events=events.count('IMPULSE_COMMITTED'),screenshots=[str(p) for p in out.glob('*.png')]);(out/'verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
