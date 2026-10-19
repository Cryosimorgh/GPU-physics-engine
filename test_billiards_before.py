"""Measure the former inelastic response using exact archived engine sources."""
from pathlib import Path
import datetime,hashlib,io,json,shutil,subprocess,zipfile
from windows_sdk import compiler,headers
r=Path(__file__).resolve().parent;out=r/'billiards-test-results'/('before-physics-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True)
with zipfile.ZipFile(io.BytesIO(subprocess.check_output(['git','archive','--format=zip','75e1b73'],cwd=r))) as z:z.extractall(out)
for p in out.glob('*.dxil'):shutil.copy2(p,out/'zig-out/bin'/p.name)
shutil.copy2(r/'pool-layout.h',out/'pool-layout.h')
text=(r/'pool_tests.zig').read_text().split('pub fn main()!void{')[0].replace('.fixture=13','.fixture=12').replace('.flags=7','.flags=1')
text+='''pub fn main()!void{var f=try F.open(false);defer f.close();try f.pair(.{1,0});var a=try f.state();for(0..16)|i|{a[i][6]=@floatCast(1.0/c.POOL_MASS);a[i][7]=@floatCast(1.0/(0.4*c.POOL_MASS*c.POOL_RADIUS*c.POOL_RADIUS));a[i][8]=@floatCast(c.POOL_RADIUS);}try f.input(a);const before=energy(a);_=try f.step();a=try f.state();try closeTo(a[0][2],0.5,0.000006);try closeTo(a[1][2],0.5,0.000006);std.debug.print("BEFORE cue_vx={d} object_vx={d} energy_before={d} energy_after={d}\\n",.{a[0][2],a[1][2],before,energy(a)});}
'''
(out/'before_impact.zig').write_text(text)
cmd=[str(compiler()),'build-exe','before_impact.zig','-cflags','-O2','--','runtime.c','spatial.c','physics.c','physics_verify.c','physics_tests.c','-I.',*headers(),'-ld3d12','-ldxgi','-ldxguid','-lkernel32','-lc','-O','ReleaseSafe','-target','x86_64-windows-gnu','-mcpu=baseline','-femit-bin=zig-out/bin/before_impact.exe']
subprocess.run(cmd,cwd=out,check=True)
p=subprocess.run([str(out/'zig-out/bin/before_impact.exe')],cwd=out,capture_output=True,text=True,timeout=90);(out/'before-impact.log').write_text(p.stdout+p.stderr);print(p.stdout+p.stderr);assert p.returncode==0
result=dict(status='PASS',baseline_revision='75e1b73',source_unchanged=True,fixture=12,flags=1,description='Isolated equal-mass pair, same SI mass/radius as correction; former normal model has no restitution',raw_result=p.stdout+p.stderr,binary_sha256=hashlib.sha256((out/'zig-out/bin/before_impact.exe').read_bytes()).hexdigest())
(out/'before-result.json').write_text(json.dumps(result,indent=2));print(out)
