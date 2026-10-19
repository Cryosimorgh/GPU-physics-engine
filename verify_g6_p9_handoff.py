"""Read-only source/evidence verifier. Never launches an executable or GPU test."""
from pathlib import Path
import hashlib,json,re,struct,sys,zipfile
def verify(target):
    archive=zipfile.ZipFile(target) if target.is_file() else None
    def read(name):return archive.read(name) if archive else (target/name).read_bytes()
    def rows(name):
        stream=archive.open(name) if archive else (target/name).open('rb')
        with stream:
            for line in stream:yield json.loads(line)
    manifest=json.loads(read('manifest.json'))
    for name,h in manifest['sha256'].items():
        assert not Path(name).is_absolute() and '..' not in Path(name).parts
        assert hashlib.sha256(read(name)).hexdigest()==h,name
    result=json.loads(read('evidence/g6-p9/results.json'))
    assert result['G6']=='NOT QUALIFIED' and result['GPU-02']=='UNVERIFIED' and result['G5']=='DEFERRED'
    good=result['functional']=='PASS IN TESTED ENVELOPE'
    if good:
        assert len(result['scenarios'])==6 and len(result['tests'])==29
        assert all(t['exit']==0 for t in result['tests'])
        assert len(result['determinism'])==3 and all(d['bitwise_equal'] for d in result['determinism'].values())
    else:assert result.get('first_failure'),'Failure cannot be hidden as an empty qualification'
    counts=[]
    for s in result['scenarios']:
        prefix='evidence/g6-p9/'+s['name']+'.json';count=0;contacts=0;deadline=0
        for row in rows(prefix+'.jsonl'):
            if row['type']!='TICK':continue
            if good:assert row['accepted'] and row['valid'] and row['energy_ok'] and row['error_flags']==0 and row['published']==s['n']
            count+=int(row['accepted']);contacts+=int(row['contacts']>0)
            deadline+=int(row['gpu_us'][39]>s['deadline_us'])
        assert count==s['accepted_ticks'] and contacts==s['contact_ticks']
        assert deadline==s['deadline_misses']['gpu_tick']
        cleanup=json.loads(read(prefix))
        if good:assert cleanup['cleanup_ok'] and cleanup['validation_errors']==0 and cleanup['retired_bytes']==0
        counts.append((s['name'],count,deadline))
    for scene,d in result['determinism'].items():
        def states(repeat):return (r['state_hash'] for r in rows(f'evidence/g6-p9/{scene}-{repeat}.json.jsonl') if r['type']=='TICK')
        first=None;common=0
        for i,(a,b) in enumerate(zip(states(0),states(1))):
            if a!=b and first is None:first=i
            common+=1
        assert common==d['common_ticks'] and first==d['first_difference']
    # Independently recompute the stopped-gate diagnosis from native trace bytes.
    diag=json.loads(read('evidence/g6-p9/isolation/result.json'))
    assert diag['status']=='LOCALIZED' and diag['same_input'] and diag['same_contact_set']
    states=[];inputs=[];contacts=[];assignments=[]
    header=read('source/physics-layout.h').decode().replace('\r\n','\n')
    for repeat in range(2):
        prefix=f'evidence/g6-p9/isolation/trace-{repeat}.json'
        payload=json.loads(read(prefix));cap=payload['capacity'];n=payload['n']
        assert payload['status']=='PASS' and payload['validation_errors']==0
        meta=read(prefix+'-meta-33.bin');arena=read(prefix+'-contacts-33.bin');trial=read(prefix+'-trial-33.bin')
        states.append(read(prefix+'-state-33.bin'))
        u32=lambda data,at:struct.unpack_from('<I',data,at)[0]
        def mv(name,i):
            match=re.search(rf'^#define G3_{name}\(c,i\) \(256u\+(\d+)u\*\(c\)\+(\d+)u\*\(i\)\)$',header,re.M);assert match
            a,b=map(int,match.groups());return u32(meta,256+a*cap+b*i)
        inputs.append([[u32(trial,64*i+4*f) for f in [0,1,4,6,7,8,9,12,15]]+[mv('FREE_'+axis,i) for axis in ['VX','VY','OMEGA','SLEEP']] for i in range(n)])
        records=[struct.unpack_from('<20I',arena,80*k) for k in range(u32(meta,8))]
        keys=[tuple(r[:2]+r[3:10]+(r[12],)+r[16:20]) for r in records]
        contacts.append(sorted(keys));assignments.append(sorted((key,r[13]) for key,r in zip(keys,records)))
    assert inputs[0]==inputs[1] and contacts[0]==contacts[1] and assignments[0]!=assignments[1]
    changed=[]
    for i in range(1024):
        for field in range(16):
            at=64*i+4*field
            if states[0][at:at+4]!=states[1][at:at+4]:changed.append((field,abs(struct.unpack_from('<f',states[0],at)[0]-struct.unpack_from('<f',states[1],at)[0])))
    assert len(changed)==48 and {f for f,_ in changed}=={2}
    assert max(delta for _,delta in changed)==4.76837158203125e-7
    print('PASS integrity',len(manifest['sha256']),'hashes;',result['functional'],'; G6 NOT QUALIFIED')
    print('case / accepted ticks / GPU deadline misses:',counts)
    if archive:archive.close()
if __name__=='__main__':verify(Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parent)
