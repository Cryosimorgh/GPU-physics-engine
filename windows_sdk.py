"""Discover SDK tools and headers without developer-machine paths or RTK."""
from pathlib import Path
import os,shutil,subprocess
def sdk():
 roots=[]
 if os.environ.get('WindowsSdkDir'):roots.append(Path(os.environ['WindowsSdkDir']))
 try:
  import winreg
  with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'SOFTWARE\Microsoft\Windows Kits\Installed Roots') as key:roots.append(Path(winreg.QueryValueEx(key,'KitsRoot10')[0]))
 except OSError:pass
 roots.append(Path(os.environ.get('ProgramFiles(x86)',r'C:\Program Files (x86)'))/'Windows Kits/10')
 for root in dict.fromkeys(roots):
  for inc in sorted((root/'Include').glob('10.*'),key=lambda p:tuple(map(int,p.name.split('.'))),reverse=True):
   dxc=root/'bin'/inc.name/'x64/dxc.exe'
   if (inc/'um/d3d12.h').is_file() and (inc/'ucrt/stdlib.h').is_file() and dxc.is_file():return inc,dxc
 raise RuntimeError('Install a Windows 10/11 SDK with D3D12 headers, UCRT and DXC.')
def run(*args):subprocess.run([str(x) for x in args],cwd=Path(__file__).parent,check=True)
def compiler():
 p=shutil.which('zig')
 if not p:raise RuntimeError('Zig 0.15.2 must be on PATH for source builds.')
 return p
def headers():
 inc,_=sdk();return [x for part in ('um','shared','ucrt') for x in ('-isystem',str(inc/part))]
def copy_shaders():
 root=Path(__file__).parent;dest=root/'zig-out/bin';dest.mkdir(parents=True,exist_ok=True)
 for p in root.glob('*.dxil'):shutil.copyfile(p,dest/p.name)
