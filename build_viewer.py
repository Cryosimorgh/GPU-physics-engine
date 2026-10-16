from pathlib import Path
import sys
from windows_sdk import sdk,run,headers,compiler,copy_shaders
r=Path(__file__).parent
(r/'zig-out/bin').mkdir(parents=True,exist_ok=True)
if '--host-only' not in sys.argv:
 run(sys.executable,'generate_viewer.py')
 for name,profile in [('ball_vs','vs_6_0'),('ball_ps','ps_6_0'),('felt_vs','vs_6_0'),('felt_ps','ps_6_0'),('render_clear','cs_6_0'),('render_verify','cs_6_0'),('hud_vs','vs_6_0'),('hud_ps','ps_6_0')]:
  run(sdk()[1],'-T',profile,'-E',name,'-Fo',name+'.dxil','hud.hlsl' if name.startswith('hud_') else 'render.hlsl')
main='g4_lifecycle_main.zig' if '--lifecycle' in sys.argv else 'viewer_main.zig' if '--reference-cli' in sys.argv else 'bench_main.zig'
name='g4_lifecycle.exe' if '--lifecycle' in sys.argv else 'viewer.exe' if '--reference-cli' in sys.argv else 'GPUPhysicsBench.exe'
run(compiler(),'build-exe',main,'-cflags','-O2','--','viewer_runtime.c','bench_support.c','spatial.c','physics.c','physics_verify.c','physics_tests.c','-I.',*headers(),'-ld3d12','-ldxgi','-ldxguid','-lkernel32','-luser32','-lgdi32','-lc','-O','ReleaseSafe','-target','x86_64-windows-gnu','-mcpu=baseline','-femit-bin=zig-out/bin/'+name)
copy_shaders()
