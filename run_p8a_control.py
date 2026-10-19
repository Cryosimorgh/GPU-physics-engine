from pathlib import Path
import subprocess,json,time
from dev_test import Workflow,digest,dependencies
R=Path(__file__).resolve().parent;E=R/'evidence/g6-p8a';B=E/'control-build';B.mkdir(exist_ok=True)
assert not (E/'control.json.jsonl').exists()
w=Workflow(B);exe=w.gpu('physics');cmd=[str(exe),'--n','16','--fixture','13','--flags','7','--contacts','256','--pairs','256','--cell-mode','1','--seconds','30','--out',str(E/'control.json')]
start=time.monotonic()
with (E/'control.log').open('wb') as f:p=subprocess.run(cmd,cwd=R,stdout=f,stderr=subprocess.STDOUT,timeout=40)
rows=[json.loads(x) for x in (E/'control.json.jsonl').read_text().splitlines()];ticks=[r for r in rows if r['type']=='TICK'];last=ticks[-1]
record={'command':cmd,'exit':p.returncode,'wall_s':time.monotonic()-start,'binary_sha256':digest(exe),'source_sha256':{n:digest(R/n) for n in dependencies(['physics_main.zig','sustained_physics.zig','runtime.c','spatial.c','physics.c','physics_verify.c','physics_tests.c'])},'shader_sha256':{p.name:digest(p) for p in R.glob('*.dxil')},'tools':w.tool_hashes,'reused':w.reused,'builds':w.actions,'failure_tick':last['tick'],'error_flags':last['error_flags'],'rollback_verified':last['rollback_verified'],'shots':[r['tick'] for r in ticks if r['shot']]}
(E/'control-provenance.json').write_text(json.dumps(record,indent=2));print(json.dumps({k:record[k] for k in ['exit','wall_s','failure_tick','error_flags','rollback_verified','shots','reused']}))
