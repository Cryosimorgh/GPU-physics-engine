from pathlib import Path
import sys
from windows_sdk import sdk,run,headers,compiler,copy_shaders
r=Path(__file__).parent
(r/'zig-out/bin').mkdir(parents=True,exist_ok=True)
if '--host-only' not in sys.argv:
 run(sys.executable,'generate_viewer.py')
 for name,profile in [('ball_vs','vs_6_0'),('ball_ps','ps_6_0'),('felt_vs','vs_6_0'),('felt_ps','ps_6_0'),('render_clear','cs_6_0'),('render_verify','cs_6_0'),('hud_vs','vs_6_0'),('hud_ps','ps_6_0'),('play_pick','cs_6_0'),('play_pick_resolve','cs_6_0')]:
  run(sdk()[1],'-T',profile,'-E',name,'-Fo',name+'.dxil','hud.hlsl' if name.startswith('hud_') else 'render.hlsl')
main='playground_main.zig' if '--playground' in sys.argv else 'g4_lifecycle_main.zig' if '--lifecycle' in sys.argv else 'viewer_main.zig' if '--reference-cli' in sys.argv else 'bench_main.zig'
name='GPUPhysicsPlayground.exe' if '--playground' in sys.argv else 'g4_lifecycle.exe' if '--lifecycle' in sys.argv else 'viewer.exe' if '--reference-cli' in sys.argv else 'GPUPhysicsBench.exe'
cpp=['-cflags','-O2','-std=c++17','-Wno-nontrivial-memaccess','--','play_ui.cpp',*[str(p) for p in (r/'third_party/imgui').glob('imgui*.cpp') if p.name!='imgui_demo.cpp'],'third_party/imgui/backends/imgui_impl_win32.cpp']
run(compiler(),'build-exe',main,'-cflags','-O2','--','viewer_runtime.c','bench_support.c','spatial.c','physics.c','physics_verify.c','physics_tests.c',*cpp,'-I.','-Ithird_party/imgui',*headers(),'-ld3d12','-ldxgi','-ldxguid','-lkernel32','-luser32','-lgdi32','-L'+str(sdk()[0].parents[1]/'Lib'/sdk()[0].name/'um/x64'),'-ld3dcompiler','-ldwmapi','-lc++','-lc','-O','ReleaseSafe','-target','x86_64-windows-gnu','-mcpu=baseline','-femit-bin=zig-out/bin/'+name)
copy_shaders()
