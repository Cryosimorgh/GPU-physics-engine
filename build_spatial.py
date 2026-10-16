from pathlib import Path
import subprocess
root=Path(__file__).parent
subprocess.run(['rtk','proxy','python','generate.py'],cwd=root,check=True)
subprocess.run(['rtk','proxy','python','generate_spatial.py'],cwd=root,check=True)
storage_entries=['initialize','classify','scan_counts','add_prefix','scatter_safe','integrate','keys','update_motion','gather','full_state','pack_render','consume_render','convert','mutate','grow_maps','full_state_vector','empty_active','clear_coverage']
for name in storage_entries:
 subprocess.run(['rtk','proxy',r'C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\dxc.exe','-T','cs_6_0','-E',name,'-Fo',name+'.dxil','storage.hlsl'],cwd=root,check=True)
names=['sp_fixture','sp_clear','sp_keys','sp_hash','sp_hash_counts','sp_scan','sp_add','sp_hash_offsets','sp_hash_scatter','sp_radix_local','sp_radix_scatter','sp_ranges','sp_count','sp_admit','sp_emit','sp_guards','sp_synthetic_counts','sp_union','sp_compress','sp_graph_stats','sp_validate','sp_poison','sp_mapping','sp_g4_occupancy']
for name in names:
 subprocess.run(['rtk','proxy',r'C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\dxc.exe','-T','cs_6_0','-E',name,'-Fo',name+'.dxil','spatial.hlsl'],cwd=root,check=True)
sdk='C:/Program Files (x86)/Windows Kits/10/Include/10.0.26100.0/'
cmd=['rtk','proxy','zig','build-exe','spatial_main.zig','-cflags','-O2','--','runtime.c','spatial.c','-I.']
for x in ['um','shared','ucrt']:cmd+=['-isystem',sdk+x]
cmd+=['-ld3d12','-ldxgi','-ldxguid','-lkernel32','-lc','-O','ReleaseSafe','-target','x86_64-windows-gnu','-mcpu=native','-femit-bin=zig-out/bin/spatial.exe']
subprocess.run(cmd,cwd=root,check=True)
