"""Serial device/package/control tests; never treats Present rate as display FPS."""
from pathlib import Path
import ctypes as C
from ctypes import wintypes as W
import csv,datetime,hashlib,json,os,shutil,subprocess,tempfile,time,uuid,zipfile
r=Path(__file__).parent.resolve();out=r/'local-test-results'/('run-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]);out.mkdir(parents=True)
extract=Path(tempfile.mkdtemp(prefix='GPU Physics Bench extracted '));caller=Path(tempfile.mkdtemp(prefix='Unrelated caller '));target=r/'dist/GPUPhysicsBench-Windows-x64.zip'
with zipfile.ZipFile(target) as z:
 assert z.testzip() is None;z.extractall(extract)
 for n,h in json.loads(z.read('SHA256.json')).items():assert hashlib.sha256((extract/n).read_bytes()).hexdigest()==h
env=dict(os.environ);env['PATH']=str(Path(os.environ['SystemRoot'])/'System32')
u=C.windll.user32;u.IsWindowVisible.argtypes=[W.HWND];u.PostMessageW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM];u.ShowWindow.argtypes=[W.HWND,C.c_int];u.SetWindowPos.argtypes=[W.HWND,W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.UINT]
callback=C.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
def window(pid,exclude=None):
 found=[]
 @callback
 def visit(h,_):
  p=W.DWORD();u.GetWindowThreadProcessId(h,C.byref(p))
  if p.value==pid and u.IsWindowVisible(h) and h!=exclude:found.append(h)
  return True
 u.EnumWindows(visit,0);return found[-1] if found else None
def wait_window(p,exclude=None,timeout=30):
 start=time.monotonic()
 while time.monotonic()-start<timeout:
  if p.poll() is not None:raise AssertionError('app exited before window: '+str(p.returncode))
  h=window(p.pid,exclude)
  if h:return h
  time.sleep(.05)
 raise TimeoutError('window')
def command(h,n):assert u.PostMessageW(h,0x111,n,0)
def exports(base):
 sessions=list(base.glob('session-*'));assert len(sessions)==1,sessions
 p=sessions[0];j=json.loads((p/'samples.json').read_text());rows=list(csv.DictReader((p/'samples.csv').open()));s=json.loads((p/'summary.json').read_text());assert len(rows)==len(j['records'])==s['records_written'];assert s['dropped_telemetry_samples']==0 and not s['writer_failed'];frames=[x for x in j['records'] if x['type']=='FRAME'];assert len(frames)==s['frame_samples_written'];assert all(bool(x['simulation_start_qpc'])==bool(x['simulated']) for x in frames);assert sum(x['simulated'] for x in frames)==s['simulation_ticks_recorded'];assert all(x['errors']==0 for x in frames);assert j['displayed_fps'] is None
 for x,y in zip(rows,j['records']):
  for name in ['qpc','frame','n','profile','generation','simulated','rendered','contacts','present_begin_qpc','present_end_qpc','simulation_start_qpc']:assert int(x[name])==y[name],(name,x,y)
 vals=sorted(x['physics_ms'] for x in frames[-4096:] if x['simulated'])
 if vals:
  import math
  assert abs(s['physics_ms_p95']-vals[math.ceil(.95*len(vals))-1])<1e-5
 return p,j,s,frames
tests=[]
def run(name,args,timeout=180,cwd=caller):
 with (out/(name+'.log')).open('w') as f:
  p=subprocess.run(args,cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
 assert p.returncode==0,(name,p.returncode,(out/(name+'.log')).read_text())
 tests.append(dict(name=name,status='PASS',command=[str(x) for x in args]));return p

# Package can execute with a foreign CWD and without development tools on PATH.
base=out/'launch';base.mkdir()
cmd='cmd.exe /d /s /c ""'+str(extract/'Launch.bat')+'" --steps 24 --automated --quiet --output-dir "'+str(base)+'""'
run('launch-bat',cmd);_,_,s,_=exports(base);assert s['frame_samples_written']==24

# Independent original CPU physics oracle + full maps + lifecycle reconciliation.
for n in [10000,100000,1000000]:
 for profile in [9,10,11]:
  file=out/f'oracle-{n}-{profile}.json'
  args=[r/'zig-out/bin/viewer.exe','--n',str(n),'--profile',str(profile),'--steps','24','--quiet','--out',file]
  if n==10000:args+=['--debug']
  run(f'oracle-{n}-{profile}',args,cwd=r);j=json.loads(file.read_text());assert j['status']=='PASS' and j['independent_full_coverage'] and j['cleanup_memory_reconciled'] and j['actual_simulation_ticks']==24
for depth in [1,2,3]:
 base=out/f'depth-{depth}';base.mkdir();run(f'depth-{depth}',[extract/'GPUPhysicsBench.exe','--steps','40','--depth',str(depth),'--debug','--quiet','--automated','--output-dir',base]);_,_,s,_=exports(base);assert s['simulation_ticks_recorded']>0
run('native-device-regressions',[r/'zig-out/bin/physics.exe','--n','32','--device-tests','--debug','--out',out/'device-tests.json'],cwd=r)
life=out/'lifecycle';life.mkdir();run('lifecycle',[r/'zig-out/bin/g4_lifecycle.exe',life],cwd=r)

# Real Win32 controls, including replacement scene admission and preserved rejection.
base=out/'interactive';base.mkdir();f=(out/'interactive.log').open('w');p=subprocess.Popen([str(extract/'GPUPhysicsBench.exe'),'--quiet','--self-test','20','--output-dir',str(base)],cwd=caller,env=env,stdout=f,stderr=subprocess.STDOUT)
try:
 h=wait_window(p);time.sleep(.5);command(h,100);time.sleep(.4);command(h,101);time.sleep(.4);command(h,101);time.sleep(.4)
 for c in [151,103,103,130,131,152,152,105]:command(h,c);time.sleep(.06)
 u.PostMessageW(h,0x201,1,100|(200<<16));u.PostMessageW(h,0x200,1,150|(220<<16));u.PostMessageW(h,0x202,0,150|(220<<16));u.PostMessageW(h,0x20a,120<<16,0);command(h,150)
 command(h,104);time.sleep(.2);command(h,104);command(h,102);h=wait_window(p,h);time.sleep(.4)
 command(h,199);time.sleep(.6);assert p.poll() is None
 for c in [111,123,141,142,143,112,110]:
  command(h,c);h=wait_window(p,h,60);time.sleep(.6)
 u.SetWindowPos(h,None,0,0,1000,700,0x0002|0x0004);time.sleep(.3);u.ShowWindow(h,6);time.sleep(.2);u.ShowWindow(h,9);time.sleep(.3)
 command(h,105);time.sleep(.3);assert u.PostMessageW(h,0x10,0,0);assert p.wait(timeout=90)==0
finally:
 if p.poll() is None:p.kill();p.wait()
 f.close()
_,j,s,frames=exports(base);events=[x['type'] for x in j['records']];assert 'SCENE_REJECTED_ACTIVE_PRESERVED' in events;assert 'REJECTION_STATE_HASH_VERIFIED' in events;assert events.count('SCENE_REPLACED')>=8;assert any(x['n']==1000000 and x['simulated'] for x in frames);assert any(not x['simulated'] for x in frames)
scenes=[json.loads(x.read_text()) for x in sorted(next(base.glob('session-*')).glob('scene-*.json'))];same=[x for x in scenes if x['n']==10000 and x['profile']==10];assert len(same)>=2 and same[0]['initial_state_sha256']==same[1]['initial_state_sha256'];
steps=[i for i,x in enumerate(j['records']) if x['type']=='SINGLE_STEP'];assert len(steps)==2;assert sum(x['simulated'] for x in j['records'][steps[0]+1:steps[1]] if x['type']=='FRAME')==1
tests.append(dict(name='interactive-controls-rejection-resize-minimize',status='PASS',events=len(events),frames=len(frames),scene_replacements=events.count('SCENE_REPLACED')))

# Unbounded interactive branch runs past 10,000 submissions, then exits by WM_CLOSE.
base=out/'long-interactive';base.mkdir();f=(out/'long-interactive.log').open('w');p=subprocess.Popen([str(extract/'GPUPhysicsBench.exe'),'--n','10000','--profile','9','--self-test','21','--quiet','--output-dir',str(base)],cwd=caller,env=env,stdout=f,stderr=subprocess.STDOUT)
try:
 h=wait_window(p);deadline=time.monotonic()+240;maximum=0
 while time.monotonic()<deadline:
  assert p.poll() is None,'interactive exited before user close'
  command(h,105);time.sleep(.5)
  fs=list(base.glob('session-*/samples.csv'))
  if fs:
   with fs[0].open() as cf:
    for x in csv.DictReader(cf):
     if x.get('type')=='FRAME':
      try:maximum=max(maximum,int(x['frame']))
      except (ValueError,TypeError):pass
  if maximum>=10025:break
 assert maximum>=10025,maximum
 u.PostMessageW(h,0x10,0,0);assert p.wait(timeout=90)==0
finally:
 if p.poll() is None:p.kill();p.wait()
 f.close()
_,j,s,frames=exports(base);assert max(x['frame'] for x in frames)>10000;assert s['simulation_ticks_recorded']>10000
tests.append(dict(name='interactive-beyond-10000',status='PASS',actual_simulation_ticks=s['simulation_ticks_recorded'],frames=len(frames)))
result=dict(status='PASS',zip=str(target),zip_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),extracted_to=str(extract),foreign_cwd=str(caller),target_path='Windows System32 only',tests=tests,displayed_fps_status='UNVERIFIED',g4_formally_closed=False)
(out/'test-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(dict(path=str(out),status='PASS',tests=len(tests)),indent=2))
