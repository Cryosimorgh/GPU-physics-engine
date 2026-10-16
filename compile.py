from pathlib import Path
import subprocess,sys
from windows_sdk import sdk,headers,compiler,copy_shaders
root=Path(__file__).parent
subprocess.run([sys.executable,'generate.py'],cwd=root,check=True)
names=['initialize','classify','scan_counts','add_prefix','scatter_safe','integrate','keys','update_motion','gather','full_state','pack_render','consume_render','convert','mutate','grow_maps','full_state_vector','empty_active','clear_coverage']
for name in names:subprocess.run([str(sdk()[1]),'-T','cs_6_0','-E',name,'-Fo',name+'.dxil','storage.hlsl'],cwd=root,check=True)
subprocess.run([compiler(),'build','-Doptimize=ReleaseSafe','-Dsdk-include='+str(sdk()[0])],cwd=root,check=True)

copy_shaders()
