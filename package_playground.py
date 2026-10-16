from pathlib import Path
import hashlib,json,zipfile,struct
r=Path(__file__).parent
files={'GPUPhysicsPlayground.exe':r/'zig-out/bin/GPUPhysicsPlayground.exe','Launch.bat':r/'LaunchPlayground.bat','README.txt':r/'PLAYGROUND_README.txt','LICENSE-ImGui.txt':r/'third_party/imgui/LICENSE.txt'}
files.update({p.name:p for p in r.glob('*.dxil')})
for directory in ['docs/screenshots','examples/playground']:
 for p in (r/directory).rglob('*'):
  if p.is_file():files[p.relative_to(r).as_posix()]=p
if (r/'PLAYGROUND_VERIFICATION.json').is_file():files['TEST_RESULTS.json']=r/'PLAYGROUND_VERIFICATION.json'
hashes={n:hashlib.sha256(p.read_bytes()).hexdigest() for n,p in files.items()}
exe=files['GPUPhysicsPlayground.exe'].read_bytes();pe=struct.unpack_from('<I',exe,0x3c)[0];assert struct.unpack_from('<H',exe,pe+4)[0]==0x8664;op=pe+24;sec=op+struct.unpack_from('<H',exe,pe+20)[0]
def offset(rva):
 for i in range(struct.unpack_from('<H',exe,pe+6)[0]):
  size,va,rawsize,raw=struct.unpack_from('<IIII',exe,sec+40*i+8)
  if va<=rva<va+max(size,rawsize):return raw+rva-va
 raise ValueError(rva)
at=offset(struct.unpack_from('<I',exe,op+120)[0]);imports=[]
while any(exe[at:at+20]):
 name=offset(struct.unpack_from('<I',exe,at+12)[0]);imports.append(exe[name:exe.index(b'\0',name)].decode());at+=20
allowed={'d3d12.dll','dxgi.dll','d3dcompiler_47.dll','dwmapi.dll','kernel32.dll','user32.dll','gdi32.dll','ntdll.dll','msvcrt.dll','ucrtbase.dll','imm32.dll','ole32.dll','advapi32.dll','shell32.dll','version.dll'}
assert all(n.lower() in allowed or n.lower().startswith(('api-ms-win-','ext-ms-win-')) for n in imports),imports
build=dict(cpu_target='x86_64 baseline',optimization='ReleaseSafe',imported_windows_system_dlls=imports,imgui_version='v1.90.9 cb16be3a3fc1f9cd146ae24d52b615f8a05fa93d',source_sha256={p.relative_to(r).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in r.iterdir() if p.is_file() and p.suffix in {'.c','.cpp','.h','.hlsl','.inc','.zig','.json','.py'}},gpu02='UNVERIFIED',g5_started=False)
build['source_sha256'].update({p.relative_to(r).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (r/'third_party/imgui').rglob('*') if p.is_file()})
target=r/'dist/GPUPhysicsPlayground-Windows-x64.zip';target.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for n,p in sorted(files.items()):z.writestr(n,p.read_bytes())
 z.writestr('results/',b'');z.writestr('SHA256.json',json.dumps(hashes,indent=2));z.writestr('BUILD.json',json.dumps(build,indent=2))
with zipfile.ZipFile(target) as z:
 assert z.testzip() is None;assert all(hashlib.sha256(z.read(n)).hexdigest()==h for n,h in hashes.items())
print(json.dumps(dict(zip=str(target.resolve()),bytes=target.stat().st_size,sha256=hashlib.sha256(target.read_bytes()).hexdigest(),files=len(files),status='PASS'),indent=2))
