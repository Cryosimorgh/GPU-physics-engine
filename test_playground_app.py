"""Native packaged-app acceptance A-G; serial GPU work and actual screenshots."""
from pathlib import Path
import ctypes as C
from ctypes import wintypes as W
import csv,datetime,hashlib,json,os,subprocess,tempfile,time,zipfile
from PIL import ImageGrab
import math,struct
def early_contacts(n):
 # Independent source-equation fixture oracle. Odd row widths change the
 # stable-ID pair hashes, so not every positional pair reaches contact at t2.
 f32=lambda x:struct.unpack('<f',struct.pack('<f',x))[0]
 def velocity(i,col):
  h=(i//2)^18228;h^=h>>16;h=(h*0x7feb352d)&0xffffffff;h^=h>>15;h=(h*0x846ca68b)&0xffffffff;h^=h>>16
  return f32(((h&255)-128)/1024+f32(-.35 if col&1 else .35)),((h>>8)&255)-128
 cols=math.ceil(math.sqrt(n));eligible=0
 for row in range((n+cols-1)//cols):
  for col in range(0,min(cols,n-row*cols)-1,2):
   i=row*cols+col;vx,a=velocity(i,col);wx,b=velocity(i+1,col+1);vy=a/1024;wy=b/1024
   x=.25+(col//2)*.375;y=.25+row*.1875
   dx=f32(x+vx/128)-f32(x+.1328125+wx/128);dy=f32(y+vy/128)-f32(y+wy/128)
   distance=math.hypot(dx,dy);gap=distance-.125;vn=((vx-wx)*dx+(vy-wy)*dy)/distance
   eligible+=gap<=0 or vn < -gap*128
 return eligible
r=Path(__file__).parent.resolve();out=r/'playground-test-results'/('app-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True)
package=r/'dist/GPUPhysicsPlayground-Windows-x64.zip';extract=Path(tempfile.mkdtemp(prefix='GPU Physics Playground extracted '));caller=Path(tempfile.mkdtemp(prefix='Foreign working directory '))
with zipfile.ZipFile(package) as z:
 assert z.testzip() is None;z.extractall(extract)
 for n,h in json.loads(z.read('SHA256.json')).items():assert hashlib.sha256((extract/n).read_bytes()).hexdigest()==h
env=dict(os.environ);env['PATH']=str(Path(os.environ['SystemRoot'])/'System32')
u=C.windll.user32;u.PostMessageW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM];u.IsWindowVisible.argtypes=[W.HWND];u.GetClientRect.argtypes=[W.HWND,C.POINTER(W.RECT)];u.GetWindowRect.argtypes=[W.HWND,C.POINTER(W.RECT)];u.SetForegroundWindow.argtypes=[W.HWND];u.SetWindowPos.argtypes=[W.HWND,W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.UINT];u.ShowWindow.argtypes=[W.HWND,C.c_int];u.ClientToScreen.argtypes=[W.HWND,C.POINTER(W.POINT)]
cb=C.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
def find(p,old=None):
 for _ in range(1200):
  found=[]
  @cb
  def f(h,_):
   pid=W.DWORD();u.GetWindowThreadProcessId(h,C.byref(pid))
   if pid.value==p.pid and h!=old and u.IsWindowVisible(h):found.append(h)
   return True
  u.EnumWindows(f,0)
  if found:return found[-1]
  assert p.poll() is None,p.returncode;time.sleep(.05)
 raise TimeoutError('scene window')
def command(h,n):assert u.PostMessageW(h,0x111,n,0)
def shot(h,name):
 u.SetForegroundWindow(h);time.sleep(.2);rect=W.RECT();u.GetWindowRect(h,C.byref(rect));ImageGrab.grab(bbox=(rect.left,rect.top,rect.right,rect.bottom)).save(out/(name+'.png'))
def parse(base):
 p=next(base.glob('session-*'));j=json.loads((p/'samples.json').read_text());s=json.loads((p/'summary.json').read_text());rows=list(csv.DictReader((p/'samples.csv').open()));assert len(rows)==len(j['records'])==s['records_written'];assert s['dropped_telemetry_samples']==0 and not s['writer_failed'];frames=[x for x in j['records'] if x['type']=='FRAME'];assert len(frames)==s['frame_samples_written'];assert sum(x['simulated'] for x in frames)==s['simulation_ticks_recorded'];assert all(x['errors']==0 for x in frames)
 for a,b in zip(rows,j['records']):
  for key in ['qpc','frame','n','profile','generation','simulated','simulation_start_qpc','impulse_entity','impulse_generation','impulse_serial']:assert int(a[key])==b[key]
 return p,j,s,frames
results=[]
# Exactly two early ticks have analytically known independent pairs in each row.
for n in [100,1000,10000,100000,1000000]:
 base=out/str(n);base.mkdir();log=(base/'run.log').open('w');p=subprocess.Popen([str(extract/'GPUPhysicsPlayground.exe'),'--n',str(n),'--quiet','--automated','--output-dir',str(base)],cwd=caller,env=env,stdout=log,stderr=subprocess.STDOUT)
 try:
  h=find(p);time.sleep(1.1 if n<1000000 else 2)
  if n==100:shot(h,'first-launch')
  if n==1000000:shot(h,'million-balls')
  if n==100:
   # Expand the actual ImGui memory/safety header with a real cursor position.
   point=W.POINT(1100,507);u.ClientToScreen(h,C.byref(point));u.SetCursorPos(point.x,point.y);time.sleep(.12);u.PostMessageW(h,0x201,1,1100|(507<<16));time.sleep(.1);u.PostMessageW(h,0x202,0,1100|(507<<16));time.sleep(.2);shot(h,'statistics-expanded')
   command(h,170);time.sleep(.3)
  u.PostMessageW(h,0x10,0,0);assert p.wait(timeout=90)==0
 finally:
  if p.poll() is None:p.kill();p.wait()
  log.close()
 session,j,s,frames=parse(base);expected=early_contacts(n);second=next(x for x in frames if x['simulated'] and x['generation']==2);assert second['contacts']==second['islands']==expected and second['largest']==2,(n,second,expected)
 assert second['active']==n and all(0<=x['active']<=n for x in frames if x['simulated']);results.append(dict(n=n,status='PASS',actual_ticks=s['simulation_ticks_recorded'],exact_tick2_pairs=expected,actual_tick2_pairs=second['contacts'],max_contacts=max(x['contacts'] for x in frames),minimum_active=min(x['active'] for x in frames if x['simulated']),peak_usage=max(x['peak'] for x in frames)))
 if n==100:assert list(session.glob('screenshot-epoch*.bmp')),'F12 must save the actual backbuffer'
 print(n,'PASS',flush=True)
# Same extracted executable under GBV at each bounded frame depth.
for depth in [1,2,3]:
 base=out/f'debug-{depth}';base.mkdir();f=(base/'run.log').open('w');p=subprocess.run([str(extract/'GPUPhysicsPlayground.exe'),'--n','1000','--steps','32','--depth',str(depth),'--debug','--quiet','--automated','--output-dir',str(base)],cwd=caller,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=180);f.close();assert p.returncode==0;(parse(base));print('GBV depth',depth,'PASS',flush=True)
# Controls, scene families, admitted replacements and explicit failed admission.
base=out/'controls';base.mkdir();log=(base/'run.log').open('w');p=subprocess.Popen([str(extract/'GPUPhysicsPlayground.exe'),'--quiet','--self-test','20','--output-dir',str(base)],cwd=caller,env=env,stdout=log,stderr=subprocess.STDOUT)
try:
 h=find(p);time.sleep(.3);command(h,100);time.sleep(.2);command(h,101);time.sleep(.2);command(h,101);time.sleep(.2);command(h,100)
 for cmd in [103,103,130,131,104,104,105,152,152,150]:command(h,cmd);time.sleep(.06)
 command(h,102);h=find(p,h);time.sleep(.3);command(h,199);time.sleep(.5)
 for cmd in [114,110,111,112,121,123,160,113,141,142,143]:
  command(h,cmd);h=find(p,h);time.sleep(.3)
 u.SetWindowPos(h,None,0,0,1050,720,0x0002|0x0004);time.sleep(.25);u.ShowWindow(h,6);time.sleep(.25);u.ShowWindow(h,9);time.sleep(.25);command(h,105);u.PostMessageW(h,0x10,0,0);assert p.wait(timeout=90)==0
finally:
 if p.poll() is None:p.kill();p.wait()
 log.close()
session,j,s,frames=parse(base);events=[x['type'] for x in j['records']];assert 'REJECTION_STATE_HASH_VERIFIED' in events and 'SCENE_REJECTED_ACTIVE_PRESERVED' in events;assert events.count('SCENE_REPLACED')==12;scenes=[json.loads(p.read_text()) for p in session.glob('scene-*.json')];initial=[x for x in scenes if x['n']==100 and x['profile']==12];assert initial[0]['initial_state_sha256']==initial[1]['initial_state_sha256'];assert any(x['n']==1000000 and x['profile']==12 and x['simulated'] for x in frames);assert any(x['profile'] in [9,10,11] for x in frames)
# Launch.bat itself is run with an unrelated CWD and the restricted PATH.
cmd='cmd.exe /d /s /c ""'+str(extract/'Launch.bat')+'" --steps 8 --automated --quiet"';p=subprocess.run(cmd,cwd=caller,env=env,capture_output=True,timeout=120);assert p.returncode==0,p.stderr
verification=dict(status='PASS',populations=results,gbv_frame_depths=[1,2,3],controls=True,scene_replacements=events.count('SCENE_REPLACED'),rejection_source_hash_preserved=True,reset_initial_hash_identical=True,csv_json_counts_agree=True,launch_bat_foreign_cwd_system_path='PASS',extracted_path=str(extract),executable_sha256=hashlib.sha256((extract/'GPUPhysicsPlayground.exe').read_bytes()).hexdigest(),display_fps='UNVERIFIED',g4_formally_closed=False,g5_started=False,screenshots=[p.name for p in out.glob('*.png')]);(out/'verification.json').write_text(json.dumps(verification,indent=2));print(json.dumps(verification,indent=2))
