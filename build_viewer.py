from pathlib import Path
import subprocess,sys
r=Path(__file__).parent
def run(*args):subprocess.run(['rtk','proxy',*args],cwd=r,check=True)
if '--host-only' not in sys.argv:
 run('python','generate_viewer.py')
 for name,profile in [('ball_vs','vs_6_0'),('ball_ps','ps_6_0'),('felt_vs','vs_6_0'),('felt_ps','ps_6_0'),('render_clear','cs_6_0'),('render_verify','cs_6_0'),('hud_vs','vs_6_0'),('hud_ps','ps_6_0')]:
  run(r'C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\dxc.exe','-T',profile,'-E',name,'-Fo',name+'.dxil','hud.hlsl' if name.startswith('hud_') else 'render.hlsl')
main='g4_lifecycle_main.zig' if '--lifecycle' in sys.argv else 'viewer_main.zig'
cmd=['zig','build-exe',main,'-cflags','-O2','--','viewer_runtime.c','spatial.c','physics.c','physics_verify.c','physics_tests.c','-I.']
for x in ['um','shared','ucrt']:cmd+=['-isystem','C:/Program Files (x86)/Windows Kits/10/Include/10.0.26100.0/'+x]
run(*cmd,'-ld3d12','-ldxgi','-ldxguid','-lkernel32','-luser32','-lgdi32','-lc','-O','ReleaseSafe','-target','x86_64-windows-gnu','-mcpu=native','-femit-bin=zig-out/bin/'+('g4_lifecycle.exe' if '--lifecycle' in sys.argv else 'viewer.exe'))
