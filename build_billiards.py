from pathlib import Path
import shutil,sys
from windows_sdk import run
r=Path(__file__).parent
run(sys.executable,'build_playground.py',*(['--tests'] if '--tests' in sys.argv else []))
shutil.copy2(r/'zig-out/bin/GPUPhysicsPlayground.exe',r/'zig-out/bin/GPUPhysicsBilliards.exe')
