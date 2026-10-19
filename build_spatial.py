from pathlib import Path
import subprocess,sys
from windows_sdk import sdk,headers,compiler,copy_shaders
root=Path(__file__).parent
subprocess.run([sys.executable,'generate.py'],cwd=root,check=True)
subprocess.run([sys.executable,'generate_spatial.py'],cwd=root,check=True)
storage_entries=['initialize','classify','scan_counts','add_prefix','scatter_safe','integrate','keys','update_motion','gather','full_state','pack_render','consume_render','convert','mutate','grow_maps','full_state_vector','empty_active','clear_coverage']
for name in storage_entries:
 subprocess.run([str(sdk()[1]),'-T','cs_6_0','-E',name,'-Fo',name+'.dxil','storage.hlsl'],cwd=root,check=True)
names=['sp_fixture','sp_clear','sp_keys','sp_hash','sp_hash_counts','sp_scan','sp_add','sp_hash_offsets','sp_hash_scatter','sp_radix_local','sp_radix_scatter','sp_ranges','sp_count','sp_admit','sp_emit','sp_guards','sp_synthetic_counts','sp_union','sp_compress','sp_graph_stats','sp_validate','sp_poison','sp_mapping','sp_g4_occupancy']
for name in names:
 subprocess.run([str(sdk()[1]),'-T','cs_6_0','-E',name,'-Fo',name+'.dxil','spatial.hlsl'],cwd=root,check=True)
cmd=[compiler(),'build-exe','spatial_main.zig','-cflags','-O2','--','runtime.c','spatial.c','-I.']
cmd+=headers()
cmd+=['-ld3d12','-ldxgi','-ldxguid','-lkernel32','-lc','-O','ReleaseSafe','-target','x86_64-windows-gnu','-mcpu=baseline','-femit-bin=zig-out/bin/spatial.exe']
subprocess.run(cmd,cwd=root,check=True)

copy_shaders()
