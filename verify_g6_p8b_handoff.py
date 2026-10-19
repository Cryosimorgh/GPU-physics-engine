"""Read-only handoff verifier: python verify_g6_p8b_handoff.py <ZIP-or-directory>."""
from pathlib import Path
import hashlib,io,itertools,json,sys,zipfile
def verify(target):
    archive=zipfile.ZipFile(target) if target.is_file() else None
    def read(n):return archive.read(n) if archive else (target/n).read_bytes()
    def lines(n):
        file=archive.open(n) if archive else (target/n).open('rb')
        with file:
            for line in file:yield json.loads(line)
    def ticks(n):return (x for x in lines(n) if x['type']=='TICK')
    manifest=json.loads(read('manifest.json'));checked=0
    for name,expected in manifest['sha256'].items():
        assert not Path(name).is_absolute() and '..' not in Path(name).parts
        assert hashlib.sha256(read(name)).hexdigest()==expected,name
        checked+=1
    e='evidence/g6-p8b/';gate=json.loads(read(e+'gate-G6-P8b.json'))
    assert gate['status']=='TARGETED CORRECTION PASS' and gate['G6']=='BLOCKED / NOT QUALIFIED'
    assert gate['broader_suite']['status']=='PASS' and gate['broader_suite']['processes']==16
    baseline=list(ticks(e+'control.json.jsonl'))
    assert len(baseline)==4073 and baseline[-1]['error_flags']==32 and baseline[-1]['rollback_verified']
    archived=list(ticks('reference/P8a-control.json.jsonl'))
    assert [r['state_hash'] for r in baseline]==[r['state_hash'] for r in archived]
    counts=[]
    for i in range(3):
        count=0
        for row in ticks(e+f'sustained-{i}.json.jsonl'):
            assert row['tick']==count and row['accepted'] and row['valid'] and row['energy_ok'] and row['error_flags']==0
            assert row['memory']['committed']==1638400 and row['memory']['allocations']==25
            count+=1
        assert count==gate['sessions'][i]['accepted_ticks'] and count>4072
        other=list(x for x in lines(e+f'sustained-{i}.json.jsonl') if x['type'] in ['END','ROLLBACK_PROBE'])
        assert next(x for x in other if x['type']=='END')['wall_s']>=30
        assert next(x for x in other if x['type']=='ROLLBACK_PROBE')['rollback_verified']
        cleanup=json.loads(read(e+f'sustained-{i}.json'))
        assert cleanup['cleanup_ok'] and cleanup['retired_bytes']==0 and cleanup['validation_errors']==0
        counts.append(count)
    common=0
    for states in zip(*(ticks(e+f'sustained-{i}.json.jsonl') for i in range(3))):
        assert len({r['state_hash'] for r in states})==1
        common+=1
    assert common==gate['determinism']['common_ticks']
    current=read('source/physics.hlsl').decode().replace('\r\n','\n');before=read(e+'baseline-physics.hlsl').decode().replace('\r\n','\n')
    marker='[numthreads(256,1,1)]void ph_admit_round'
    assert current[current.index(marker):]==before[before.index(marker):]
    assert gate['changed_default_shaders']==['ph_append.dxil','ph_walls.dxil']
    assert gate['numerical']['after_focused_GPU']['normal_residual']==0
    print(f'PASS {checked} hashes; baseline flag32 reproduced; sustained ticks={counts}; {common} identical shared hashes; G6 BLOCKED / NOT QUALIFIED')
    if archive:archive.close()
if __name__=='__main__':verify(Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parent)
