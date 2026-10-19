"""Real Win32 cue interactions and actual client-area gameplay recording."""
from pathlib import Path
import ctypes as C
from ctypes import wintypes as W
import argparse,csv,datetime,hashlib,json,math,os,shutil,struct,subprocess,time
from PIL import Image
from build_billiards import verify_build
r=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--executable',type=Path);args=parser.parse_args();executable=(args.executable or r/'zig-out/bin/GPUPhysicsBilliards.exe').resolve()
if args.executable is None:verify_build(r)
out=r/'billiards-test-results'/('gameplay-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True)
u=C.windll.user32;u.PostMessageW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM];u.GetClientRect.argtypes=[W.HWND,C.POINTER(W.RECT)];u.ClientToScreen.argtypes=[W.HWND,C.POINTER(W.POINT)];u.SetWindowPos.argtypes=[W.HWND,W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.UINT];u.SetForegroundWindow.argtypes=[W.HWND];u.IsWindowVisible.argtypes=[W.HWND]
cb=C.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
def find(p,old=0):
 for _ in range(1000):
  found=[]
  @cb
  def f(h,_):
   pid=W.DWORD();u.GetWindowThreadProcessId(h,C.byref(pid))
   if pid.value==p.pid and h!=old and u.IsWindowVisible(h):found.append(h)
   return True
  u.EnumWindows(f,0)
  if found:return found[-1]
  assert p.poll() is None,p.returncode;time.sleep(.03)
 raise TimeoutError('window')
def size(h):
 rect=W.RECT();u.GetClientRect(h,C.byref(rect));point=W.POINT(0,0);u.ClientToScreen(h,C.byref(point));return rect.right,rect.bottom,point
def place(h):
 work=W.RECT();u.SystemParametersInfoW(48,0,C.byref(work),0);u.SetWindowPos(h,None,work.left,work.top,min(1280,work.right-work.left),min(800,work.bottom-work.top),4);u.SetForegroundWindow(h);time.sleep(.25);u.PostMessageW(h,0x100,0x24,0);time.sleep(.15)
def cursor(h,x,y):
 pt=W.POINT(round(x),round(y));u.ClientToScreen(h,C.byref(pt));u.SetCursorPos(pt.x,pt.y)
def mouse(h,msg,x,y,down=0):u.PostMessageW(h,msg,down,(round(x)&65535)|((round(y)&65535)<<16))
def backbuffer(h):
 session=next(out.glob("session-*")); before=set(session.glob("screenshot-*.bmp"));u.PostMessageW(h,0x111,170,0)
 for _ in range(600):
  fresh=set(session.glob("screenshot-*.bmp"))-before
  if fresh:
   try:
    path=sorted(fresh)[-1]
    with Image.open(path) as image:result=image.convert("RGB")
    # Keep requested PNG keyframes and encoded footage, not hundreds of raw
    # multi-megabyte intermediate backbuffer copies from this bounded capture.
    path.unlink();return result
   except (OSError,ValueError):pass
  assert p.poll() is None,p.returncode;time.sleep(.005)
 raise TimeoutError("GPU backbuffer capture")
def picture(h,name):
 im=backbuffer(h);im.save(out/(name+".png"));return im
log=(out/'run.log').open('w');p=subprocess.Popen([str(executable),'--quiet','--self-test','31','--output-dir',str(out)],cwd=r,stdout=log,stderr=subprocess.STDOUT)
encoder=None;frames=[]
try:
 h=find(p);place(h);w,height,pt=size(h);picture(h,'initial-stationary-rack')
 encoderlog=(out/'encode.log').open('w');encoder=subprocess.Popen([shutil.which('ffmpeg'),'-y','-f','rawvideo','-pixel_format','rgb24','-video_size',f'{w}x{height}','-framerate','15','-i','pipe:0','-an','-vf','pad=ceil(iw/2)*2:ceil(ih/2)*2','-c:v','libx264','-preset','fast','-crf','23','-pix_fmt','yuv420p',str(out/'gameplay.mp4')],stdin=subprocess.PIPE,stdout=encoderlog,stderr=subprocess.STDOUT)
 def capture(seconds,label):
  deadline=time.perf_counter()+seconds
  while time.perf_counter()<deadline:
   start=time.perf_counter();assert p.poll() is None,p.returncode;ww,hh,point=size(h);assert (ww,hh)==(w,height);im=backbuffer(h);encoder.stdin.write(im.tobytes());frames.append((len(frames),time.perf_counter_ns(),label));time.sleep(max(0,1/15-(time.perf_counter()-start)))
 capture(.8,'stationary rack')
 half=max(1.27*.68,2.54*.57*height/max(200,w-330));cx=1.27+310*half/height;cy=.635-100*half/height;scale=height/(2*half);x=(.635-cx)*scale+w*.5;y=(cy-.635)*scale+height*.5
 cursor(h,x,y);capture(.2,'select cue');mouse(h,0x201,x,y,1);capture(.4,'cue selected');cursor(h,x+550,y);mouse(h,0x200,x+550,y,1);capture(.6,'aiming');picture(h,'cue-aiming');mouse(h,0x202,x+550,y);capture(1.5,'break shot and rack cascade');picture(h,'rack-cascade');capture(3.0,'gradual cloth stopping');picture(h,'after-break-settled')
 # Focus uses the asynchronously completed GPU position of selected cue ID 0.
 u.PostMessageW(h,0x100,0x46,0);capture(.3,'focus cue');x=w*.5-.27*height/1.4;y=height*.5;cursor(h,x,y);capture(.15,'second cue selection');mouse(h,0x201,x,y,1);capture(.3,'second selection');cursor(h,x-760,y);mouse(h,0x200,x-760,y,1);capture(.4,'aim rail shot');mouse(h,0x202,x-760,y);capture(.3,'second strike');u.PostMessageW(h,0x100,0x24,0);capture(2.5,'rail shot');picture(h,'rail-interactions');capture(7,'rolling to rest');picture(h,'all-balls-settled')
 encoder.stdin.close();assert encoder.wait(timeout=60)==0;encoder=None;encoderlog.close()
 # Pause, one global tick, reset and one table recreated safely.
 u.PostMessageW(h,0x100,0x20,0);time.sleep(.15);u.PostMessageW(h,0x100,0xbe,0);time.sleep(.2);u.PostMessageW(h,0x100,0x52,0);old=h;h=find(p,old);place(h);time.sleep(.3);picture(h,'reset-rack');u.PostMessageW(h,0x10,0,0);assert p.wait(timeout=90)==0
finally:
 if p.poll() is None:p.kill();p.wait()
 if encoder:
  encoder.stdin.close();encoder.wait(timeout=60)
 log.close()
session=next(out.glob('session-*'));data=json.loads((session/'samples.json').read_text());summary=json.loads((session/'summary.json').read_text());events=[x['type'] for x in data['records']];f=[x for x in data['records'] if x['type']=='FRAME'];committed=[x for x in data['records'] if x['type']=='IMPULSE_COMMITTED']
assert len(committed)==2,events
assert 'RAIL_IMPACT' in events and 'BALL_IMPACT' in events,events
assert all(x['impulse_entity']==0 for x in committed)
assert all(x['errors']==0 and x['n']==16 for x in f)
assert max(x['contacts'] for x in f)>=3 and max(x['largest'] for x in f)>=3
assert summary['dropped_telemetry_samples']==0 and not summary['writer_failed']
assert 'SINGLE_STEP' in events and 'SCENE_REPLACED' in events
second_strike=[i for i,x in enumerate(data['records']) if x['type']=='IMPULSE_COMMITTED'][1]
reset=next(i for i in range(second_strike+1,len(data['records'])) if data['records'][i]['type']=='SCENE_REPLACED')
settling=[x for x in data['records'][second_strike:reset] if x['type']=='FRAME' and x['simulated']]
assert len(settling)>=8 and all(x['active']==0 for x in settling[-8:]),'Balls did not naturally settle before reset'
scenes=[json.loads(x.read_text()) for x in sorted(session.glob('scene-*.json'))];assert scenes[0]['initial_state_sha256']==scenes[1]['initial_state_sha256']
with (out/'capture-timestamps.csv').open('w',newline='') as file:
 writer=csv.writer(file);writer.writerow(['encoded_frame','capture_perf_counter_ns','phase']);writer.writerows(frames)
result=dict(status='PASS',actual_simulated_ticks=sum(x['simulated'] for x in f),cue_strikes=len(committed),max_contacts=max(x['contacts'] for x in f),max_island=max(x['largest'] for x in f),deterministic_reset=True,video_actual_client_capture=True, capture_source='D3D12 actual swapchain backbuffer, fence-completed copies',encoded_frames=len(frames),encoded_cadence=15,capture_timestamps='capture-timestamps.csv',display_fps='UNVERIFIED',screenshots=[x.name for x in out.glob('*.png')])
result.update(executable=str(executable),executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),natural_stopping_before_reset=True,last_eight_active_counts=[x['active'] for x in settling[-8:]])
(out/'verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2));print(out)
