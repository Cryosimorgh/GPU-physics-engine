from pathlib import Path
import sys
from windows_sdk import run,compiler,headers
run(sys.executable,'generate_playground.py')
if '--tests-only' not in sys.argv:
 run(sys.executable,'build_physics.py')
 run(sys.executable,'build_viewer.py','--playground')
if '--tests' in sys.argv or '--tests-only' in sys.argv:
 run(compiler(),'build-exe','playground_gpu_tests.zig','-cflags','-O2','--','runtime.c','spatial.c','physics.c','physics_verify.c','physics_tests.c','-I.',*headers(),'-ld3d12','-ldxgi','-ldxguid','-lkernel32','-lc','-O','ReleaseSafe','-target','x86_64-windows-gnu','-mcpu=baseline','-femit-bin=zig-out/bin/playground_gpu_tests.exe')
