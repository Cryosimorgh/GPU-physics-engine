from pathlib import Path
import subprocess
root=Path(__file__).parent
subprocess.run(['rtk','proxy','python','generate.py'],cwd=root,check=True)
names=['initialize','classify','scan_counts','add_prefix','scatter_safe','integrate','keys','update_motion','gather','full_state','pack_render','consume_render','convert','mutate','grow_maps','full_state_vector','empty_active','clear_coverage']
for name in names:subprocess.run(['rtk','proxy',r'C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\dxc.exe','-T','cs_6_0','-E',name,'-Fo',name+'.dxil','storage.hlsl'],cwd=root,check=True)
subprocess.run(['rtk','proxy','zig','build','-Doptimize=ReleaseSafe'],cwd=root,check=True)
