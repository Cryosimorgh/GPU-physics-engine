"""Exercise the shipped binary, native controls and retirement from foreign CWD."""
from pathlib import Path
import ctypes as C
from ctypes import wintypes as W
import argparse,datetime,hashlib,json,os,subprocess,tempfile,time,zipfile
r=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--package',type=Path,required=True,help='Exact versioned portable to verify; never silently test a historical ZIP');parser.add_argument('--reuse-lifecycle',type=Path,help='Reuse a completed lifecycle proof only for an identical full runtime payload; still verify and launch this exact ZIP');args=parser.parse_args();package=args.package.resolve()
out=r/'billiards-test-results'/('package-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True)
extract=Path(tempfile.mkdtemp(prefix='GPU Physics Billiards extracted '));caller=Path(tempfile.mkdtemp(prefix='Foreign working directory '))
with zipfile.ZipFile(package) as z:
 assert z.testzip() is None;z.extractall(extract)
 hashes=json.loads(z.read('SHA256.json'))
 for n,h in hashes.items():assert hashlib.sha256((extract/n).read_bytes()).hexdigest()==h
 runtime_hashes={n:h for n,h in hashes.items() if n.endswith(('.exe','.dxil')) or n=='Launch.bat'}
env=dict(os.environ);env['PATH']=str(Path(os.environ['SystemRoot'])/'System32')
if args.reuse_lifecycle:
 proof=json.loads(args.reuse_lifecycle.read_text())
 assert proof['status']=='PASS' and proof['gbv_depths']==[1,2,3] and proof['controls'] and proof['explicit_failure_source_hash_preserved']
 assert proof['runtime_sha256']==runtime_hashes,'Runtime changed: rerun complete lifecycle test'
 cmd='cmd.exe /d /s /c ""'+str(extract/'Launch.bat')+'" --steps 8 --automated --quiet"'
 p=subprocess.run(cmd,cwd=caller,env=env,capture_output=True,timeout=120);assert p.returncode==0,p.stderr
 session=next((extract/'results').glob('session-*'));records=json.loads((session/'samples.json').read_text())['records'];frames=[x for x in records if x['type']=='FRAME' and x['simulated']]
 assert len(frames)==8 and all(x['n']==16 and x['profile']==13 and x['active']==0 and x['errors']==0 for x in frames)
 result=dict(status='PASS',package=str(package),package_sha256=hashlib.sha256(package.read_bytes()).hexdigest(),runtime_sha256=runtime_hashes,executable_sha256=runtime_hashes['GPUPhysicsBilliards.exe'],launch_bat_foreign_cwd_system_path='PASS',final_zip_launch_ticks=8,
             lifecycle_reused_from=str(args.reuse_lifecycle),lifecycle_proof_sha256=hashlib.sha256(args.reuse_lifecycle.read_bytes()).hexdigest(),same_complete_runtime_payload=True,gpu02='UNVERIFIED',g5_qualified=False)
 (out/'verification.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='runtime_sha256'},indent=2));raise SystemExit(0)
u=C.windll.user32;u.PostMessageW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM];u.IsWindowVisible.argtypes=[W.HWND];u.SetWindowPos.argtypes=[W.HWND,W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.UINT];u.ShowWindow.argtypes=[W.HWND,C.c_int]
cb=C.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
def find(p,old=0):
 for _ in range(1200):
  found=[]
  @cb
  def visit(h,_):
   pid=W.DWORD();u.GetWindowThreadProcessId(h,C.byref(pid))
   if pid.value==p.pid and h!=old and u.IsWindowVisible(h):found.append(h)
   return True
  u.EnumWindows(visit,0)
  if found:return found[-1]
  assert p.poll() is None,p.returncode;time.sleep(.05)
 raise TimeoutError('window')
def command(h,n):assert u.PostMessageW(h,0x111,n,0)
def parse(base):
 session=next(base.glob('session-*'));j=json.loads((session/'samples.json').read_text());s=json.loads((session/'summary.json').read_text());f=[x for x in j['records'] if x['type']=='FRAME']
 assert s['dropped_telemetry_samples']==0 and not s['writer_failed'];assert all(x['errors']==0 for x in f);assert sum(x['simulated'] for x in f)==s['simulation_ticks_recorded']
 return session,j,s,f
for depth in [1,2,3]:
 base=out/f'debug-{depth}';base.mkdir()
 with (base/'run.log').open('w') as log:
  p=subprocess.run([str(extract/'GPUPhysicsBilliards.exe'),'--steps','32','--depth',str(depth),'--debug','--quiet','--automated','--output-dir',str(base)],cwd=caller,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180)
 assert p.returncode==0,p.returncode
 _,_,s,f=parse(base);assert s['simulation_ticks_recorded']==32;assert all(x['n']==16 and x['profile']==13 and x['active']==0 and x['contacts']==0 for x in f if x['simulated']);print('GBV depth',depth,'PASS',flush=True)
base=out/'controls';base.mkdir();log=(base/'run.log').open('w');p=subprocess.Popen([str(extract/'GPUPhysicsBilliards.exe'),'--quiet','--self-test','20','--output-dir',str(base)],cwd=caller,env=env,stdout=log,stderr=subprocess.STDOUT)
try:
 h=find(p);time.sleep(.3);command(h,100);time.sleep(.2);command(h,101);time.sleep(.2);command(h,100);time.sleep(.2)
 command(h,102);h=find(p,h);time.sleep(.3);command(h,199);time.sleep(.5)
 # Depth replacement, explicit synthetic scene switch and return to fixed rack.
 for cmd in [141,142,143,121,162]:
  command(h,cmd);h=find(p,h);time.sleep(.3)
 u.SetWindowPos(h,None,0,0,1050,720,0x0002|0x0004);time.sleep(.25);u.ShowWindow(h,6);time.sleep(.25);u.ShowWindow(h,9);time.sleep(.25);u.PostMessageW(h,0x10,0,0);assert p.wait(timeout=90)==0
finally:
 if p.poll() is None:p.kill();p.wait()
 log.close()
session,j,s,f=parse(base);events=[x['type'] for x in j['records']];assert 'REJECTION_STATE_HASH_VERIFIED' in events and 'SCENE_REJECTED_ACTIVE_PRESERVED' in events;assert 'SINGLE_STEP' in events
scenes=[json.loads(p.read_text()) for p in sorted(session.glob('scene-*.json'))];pool=[x for x in scenes if x['n']==16 and x['profile']==13];assert len(pool)>=3 and len({x['initial_state_sha256'] for x in pool})==1;assert any(x['profile']==9 and x['n']==10000 for x in f)
cmd='cmd.exe /d /s /c ""'+str(extract/'Launch.bat')+'" --steps 8 --automated --quiet"'
p=subprocess.run(cmd,cwd=caller,env=env,capture_output=True,timeout=120);assert p.returncode==0,p.stderr
result=dict(status='PASS',gbv_depths=[1,2,3],gbv_ticks_per_depth=32,controls=True,resize_minimize_restore=True,explicit_failure_source_hash_preserved=True,reset_initial_hash_identical=True,scene_replacements=events.count('SCENE_REPLACED'),launch_bat_foreign_cwd_system_path='PASS',executable_sha256=hashlib.sha256((extract/'GPUPhysicsBilliards.exe').read_bytes()).hexdigest(),runtime_sha256=runtime_hashes,extracted_path=str(extract),package=str(package),package_sha256=hashlib.sha256(package.read_bytes()).hexdigest(),gpu02='UNVERIFIED',g5_qualified=False)
(out/'verification.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='runtime_sha256'},indent=2))
