"""Create a portable, verified distribution without a development runtime."""
from pathlib import Path
import hashlib,json,subprocess,sys,zipfile,struct
from windows_sdk import run
r=Path(__file__).parent
if '--no-build' not in sys.argv:
 run(sys.executable,'build_physics.py');run(sys.executable,'build_viewer.py')
files={'GPUPhysicsBench.exe':r/'zig-out/bin/GPUPhysicsBench.exe','Launch.bat':r/'Launch.bat','README.txt':r/'PORTABLE_README.txt'}
files.update({p.name:p for p in r.glob('*.dxil')})
if (r/'APP_VERIFICATION.json').is_file():files['TEST_RESULTS.json']=r/'APP_VERIFICATION.json'
if (r/'examples').exists():
 files.update({p.relative_to(r).as_posix():p for p in (r/'examples').rglob('*') if p.is_file()})
assert all(p.is_file() for p in files.values())
manifest={n:hashlib.sha256(p.read_bytes()).hexdigest() for n,p in files.items()}
exe=files['GPUPhysicsBench.exe'].read_bytes();pe=struct.unpack_from('<I',exe,0x3c)[0];assert exe[pe:pe+4]==b'PE\0\0';assert struct.unpack_from('<H',exe,pe+4)[0]==0x8664
optional=pe+24;assert struct.unpack_from('<H',exe,optional)[0]==0x20b
sections=struct.unpack_from('<H',exe,pe+6)[0];table=optional+struct.unpack_from('<H',exe,pe+20)[0]
def offset(rva):
 for i in range(sections):
  p=table+40*i;size,va,rawsize,raw=struct.unpack_from('<IIII',exe,p+8)
  if va<=rva<va+max(size,rawsize):return raw+rva-va
 raise ValueError('invalid PE RVA')
imports=[];at=offset(struct.unpack_from('<I',exe,optional+120)[0])
while any(exe[at:at+20]):
 name=offset(struct.unpack_from('<I',exe,at+12)[0]);imports.append(exe[name:exe.index(b'\0',name)].decode('ascii'));at+=20
system={'kernel32.dll','user32.dll','gdi32.dll','d3d12.dll','dxgi.dll','ntdll.dll','msvcrt.dll','advapi32.dll','shell32.dll','ole32.dll','winmm.dll','bcrypt.dll','ucrtbase.dll'}
assert all(n.lower() in system or n.lower().startswith(('api-ms-win-','ext-ms-win-')) for n in imports),imports
build={'target':'x86_64-windows-gnu','cpu':'baseline','optimization':'ReleaseSafe','imported_system_dlls':imports,'runtime_development_tools_required':False,'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in r.iterdir() if p.is_file() and p.suffix in {'.c','.h','.hlsl','.zig','.inc','.py','.json'}},'display_fps_status':'UNVERIFIED','g4_formally_closed':False}
out=r/'dist';out.mkdir(exist_ok=True);target=out/'GPUPhysicsBench-Windows-x64.zip'
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for n,p in sorted(files.items()):z.writestr(n,p.read_bytes())
 z.writestr('results/',b'');z.writestr('SHA256.json',json.dumps(manifest,indent=2));z.writestr('BUILD.json',json.dumps(build,indent=2))
with zipfile.ZipFile(target) as z:
 assert z.testzip() is None
 for n,h in manifest.items():assert hashlib.sha256(z.read(n)).hexdigest()==h
print(json.dumps({'zip':str(target.resolve()),'files':len(files),'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'verification':'PASS'},indent=2))
