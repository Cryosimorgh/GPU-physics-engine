"""Read-only repeat/state/provenance verification. No GPU submissions."""
import hashlib,json,subprocess
from pathlib import Path
from analyze_pool_fault import analyze
R=Path(__file__).resolve().parent;E=R/'evidence/g6-p8a'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    old=json.loads((E/'original-workspace.json').read_text());O=Path(old['original']);assert all(sha(O/n)==h for n,h in old['hashes'].items())
    assert subprocess.check_output(['git','status','--porcelain'],cwd=O).decode()==old['status']
    for n in ['physics.c','projected_solver.hlsl','physics-math.hlsl','pool.hlsl']:assert sha(R/n)==old['hashes'][n],n
    results=json.loads((E/'diagnostic-results.json').read_text());build=json.loads((E/'diagnostic-build.json').read_text())
    control=json.loads((E/'control-provenance.json').read_text())
    assert build['normal_shaders']==control['shader_sha256'],'default diagnostics must compile out byte-for-byte'
    for n,h in build['source_sha256'].items():assert sha(R/n)==h,n
    assert sha(R/'zig-out/bin/physics.exe')==build['host_sha256']
    for n,h in build['normal_shaders'].items():
        assert sha(R/n)==h,n
        if (R/'zig-out/bin'/n).exists():assert sha(R/'zig-out/bin'/n)==h,n
    for n,h in build['diagnostic_shaders'].items():assert sha(E/'diagnostic-shaders'/n)==h,n
    original=[json.loads(x) for x in (E/'original-P8/small-pool.json.jsonl').read_text().splitlines() if json.loads(x)['type']=='TICK']
    for name in ['control','diagnostic-0','diagnostic-1']:
        rows=[json.loads(x) for x in (E/(name+'.json.jsonl')).read_text().splitlines() if json.loads(x)['type']=='TICK']
        assert len(rows)==4073 and all(r['state_hash']==o['state_hash'] for r,o in zip(rows,original))
        assert all(r['valid'] for r in rows[:-1]) and not rows[-1]['accepted'] and rows[-1]['error_flags']==32 and rows[-1]['rollback_verified']
    witnesses=[analyze(E/f'diagnostic-{i}.json') for i in range(2)];assert witnesses[0]==witnesses[1]
    assert all(r['fault']['tick']==4072 and r['fault']['subcode']==1 and r['fault']['a']==7 and r['fault']['b']==17 and r['cleanup']['cleanup_ok'] and r['cleanup']['retired_bytes']==0 for r in results['runs'])
    # Full payload is untouched until an actual failed predicate. The 64-byte
    # record uses existing spare space immediately below, and not in, the guard.
    schema=json.loads((R/'pool-schema.json').read_text());assert schema['failure_diagnostic_offset']+schema['failure_diagnostic_bytes']==schema['guard_offset'] and schema['extension_bytes']==768
    result={'status':'PASS','control_plus_diagnostic_runs':3,'diagnostic_repeats':2,'matching_state_hashes_per_run':4073,'failure_tick':4072,'subcode':1,'body':7,'wall':17,'normal_residual':witnesses[0]['normal_residual_validator'],'limit':witnesses[0]['validation_threshold'],'ratio':witnesses[0]['ratio'],'published_state_sha256':witnesses[0]['published_state_sha256'],'preserved_original_files':len(old['hashes']),'default_byte_identical_DXIL':len(build['normal_shaders']),'normal_shaders_restored':True,'correction_applied':False,'G5':'DEFERRED','G6':'NOT QUALIFIED'}
    (E/'verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
