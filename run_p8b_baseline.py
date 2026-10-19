"""Run in an isolated P8a source checkout BEFORE applying the P8b patch."""
from pathlib import Path
import json,subprocess,time
from dev_test import Workflow,digest,dependencies
R=Path(__file__).resolve().parent;E=R/'evidence/g6-p8b'
def main():
    E.mkdir(parents=True,exist_ok=True)
    assert digest(R/'physics.hlsl')==digest(E/'baseline-physics.hlsl'),'Use the recorded unchanged P8a source checkout'
    assert not (E/'control.json.jsonl').exists(),'Preserve existing control evidence'
    out=E/'control-build';out.mkdir(exist_ok=True);w=Workflow(out);exe=w.gpu('physics')
    cmd=[str(exe),'--n','16','--fixture','13','--flags','7','--contacts','256','--pairs','256','--cell-mode','1','--seconds','30','--out',str(E/'control.json')]
    start=time.monotonic()
    with (E/'control.log').open('wb') as f:p=subprocess.run(cmd,cwd=R,stdout=f,stderr=subprocess.STDOUT,timeout=40)
    ticks=[json.loads(x) for x in (E/'control.json.jsonl').read_text().splitlines() if json.loads(x)['type']=='TICK'];last=ticks[-1]
    record={'command':cmd,'exit':p.returncode,'wall_s':time.monotonic()-start,'binary_sha256':digest(exe),'source_sha256':{n:digest(R/n) for n in dependencies(['physics_main.zig','sustained_physics.zig','runtime.c','spatial.c','physics.c','physics_verify.c','physics_tests.c'])},'shader_sha256':{p.name:digest(p) for p in R.glob('*.dxil')},'tools':w.tool_hashes,'reused':w.reused,'builds':w.actions,'failure_tick':last['tick'],'error_flags':last['error_flags'],'rollback_verified':last['rollback_verified'],'shots':[r['tick'] for r in ticks if r['shot']]}
    (E/'control-provenance.json').write_text(json.dumps(record,indent=2))
    assert (p.returncode,last['tick'],last['error_flags'],last['rollback_verified'])==(1,4072,32,True)
    print('REPRODUCED unchanged P8a: tick 4072, flag32, exact rollback')
if __name__=='__main__':main()
