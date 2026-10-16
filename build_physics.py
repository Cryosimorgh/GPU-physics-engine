from pathlib import Path
import subprocess,sys
r=Path(__file__).parent
def run(*args):subprocess.run(['rtk','proxy',*args],cwd=r,check=True)
names=['ph_scene','ph_guards','ph_clear','ph_prepare','ph_round','ph_append','ph_walls','ph_admit_round','ph_graph_clear','ph_union','ph_compress','ph_contact_counts','ph_scan','ph_add','ph_members','ph_contact_scatter','ph_args','ph_color','ph_color_counts','ph_color_ranges','ph_ready','ph_solve','ph_check_contacts','ph_check_bodies','ph_check_pairs','ph_check_guards','ph_publish','ph_execution_config','ph_retry_admission','ph_scene_one','ph_source_epoch']
if '--host-only' not in sys.argv:
 run('python','generate_execution.py');run('python','generate_billiards.py');run('python','generate_physics.py');run('python','build_spatial.py')
 for name in names:run(r'C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\dxc.exe','-T','cs_6_0','-Gis','-E',name,'-Fo',name+'.dxil','physics.hlsl')
cmd=['zig','build-exe','physics_main.zig','-cflags','-O2','--','runtime.c','spatial.c','physics.c','physics_verify.c','physics_tests.c','-I.']
for x in ['um','shared','ucrt']:cmd+=['-isystem','C:/Program Files (x86)/Windows Kits/10/Include/10.0.26100.0/'+x]
run(*cmd,'-ld3d12','-ldxgi','-ldxguid','-lkernel32','-lc','-O','ReleaseSafe','-target','x86_64-windows-gnu','-mcpu=native','-femit-bin=zig-out/bin/physics.exe')
