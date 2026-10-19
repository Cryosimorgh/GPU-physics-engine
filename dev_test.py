"""Bounded headless development tests over the existing GPU runtime and tests."""
from pathlib import Path
import argparse,ast,datetime,hashlib,json,os,re,shutil,subprocess,sys,time,tempfile
from functools import lru_cache
from windows_sdk import sdk,headers,compiler
sdk=lru_cache(None)(sdk)
compiler=lru_cache(None)(compiler)

ROOT=Path(__file__).resolve().parent
SMOKE=['idle','collisions','energy','discovery','overhead']
GENERATORS={
 'generate.py':('schema.json',['layout.zig','layout.h','layout.hlsl']),
 'generate_spatial.py':('spatial-schema.json',['spatial-layout.h']),
 'generate_physics.py':('physics-schema.json',['physics-layout.h','physics-constants.hlsl']),
 'generate_execution.py':('execution-schema.json',['execution-layout.h']),
 'generate_billiards.py':('billiards-schema.json',['billiards-layout.h']),
 'generate_playground.py':('playground-schema.json',['playground-layout.h']),
 'generate_pool.py':('pool-schema.json',['pool-layout.h']),
}
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dependencies(names):
    """Transitive repository-local C/HLSL includes and Zig imports/cIncludes."""
    found=set();pending=list(names)
    while pending:
        name=pending.pop();path=ROOT/name
        if name in found or not path.is_file():continue
        found.add(name)
        for match in re.finditer(r'(?:@import|@cInclude)\("([^"\n]+)"\)|#include\s+"([^"\n]+)"',path.read_text(encoding='utf-8',errors='replace')):
            child=match[1] or match[2];candidate=(path.parent/child).resolve()
            base=ROOT.resolve()
            if candidate.is_relative_to(base) and candidate.is_file():pending.append(candidate.relative_to(base).as_posix())
    return sorted(found)
def select_cases(files):
    selected=set()
    for name in files:
        name=name.replace('\\','/');p=Path(name)
        if name in {'dev_test.py','test_dev_workflow.py','pool_tests.zig','windows_sdk.py'}:selected.update(SMOKE+['cpu','commands'])
        elif name=='tests.zig':selected.add('cpu')
        elif name=='playground_gpu_tests.zig':selected.add('commands')
        elif name=='physics_main.zig':selected.update(['cli','device'])
        elif name=='main.zig':selected.add('storage')
        elif name=='spatial_main.zig':selected.add('spatial')
        elif name in {'storage.zig','layout.zig','layout.h','layout.hlsl','runtime.c','runtime.h','api.h'}:selected.update(SMOKE+['cpu','commands','storage','spatial'])
        elif name in {'spatial.c','spatial.h','spatial.hlsl','spatial-layout.h'}:selected.update(SMOKE+['commands','spatial'])
        elif name in {'build_physics.py','build_spatial.py','build_playground.py','compile.py','build.zig'}:selected.update(SMOKE+['cpu','commands','cli'])
        elif name in {'entity.zig','transaction.zig'}:selected.update(SMOKE+['cpu','commands'])
        elif name=='projected_solver.hlsl' or name=='physics-math.hlsl':selected.update(['collisions','energy','overhead','commands'])
        elif name.startswith('generate_') or name=='generate.py' or name.endswith('-schema.json') or name=='schema.json':selected.update(SMOKE+['cpu','commands'])
        elif name in {'render.hlsl','viewer.c','viewer_runtime.c','play_ui.cpp','play_ui.h','playground_view.inc','playground_main.zig','viewer_main.zig','bench_main.zig'}:continue
        elif p.suffix in {'.c','.h','.hlsl','.zig'}:
            if name.startswith('third_party/') or name.startswith('zig-out/'):continue
            selected.update(SMOKE+['commands'])
    return [case for case in SMOKE+['cpu','commands','cli','device','storage','spatial'] if case in selected]
def changed_files():
    commands=[['git','diff','HEAD','--name-only','-z'],['git','ls-files','--others','--exclude-standard','-z']]
    names=set()
    for args in commands:
        p=subprocess.run(args,cwd=ROOT,capture_output=True,check=True)
        names.update(p.stdout.decode('utf-8').split('\0'))
    return sorted(names-{''})
def shader_jobs():
    def values(path,key):
        tree=ast.parse((ROOT/path).read_text())
        return next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id==key for t in node.targets))
    return [('storage.hlsl',n,False) for n in values('build_spatial.py','storage_entries')]+[('spatial.hlsl',n,False) for n in values('build_spatial.py','names')]+[('physics.hlsl',n,True) for n in values('build_physics.py','names')]

class Workflow:
    def __init__(self,out):
        self.out=out;self.cache=ROOT/'.dev-test-cache';self.cache.mkdir(exist_ok=True)
        path=self.cache/'build.json';self.state=json.loads(path.read_text()) if path.exists() else {}
        self.actions=[];self.reused=0;self.ready={};self.tool_hashes=None
    def run(self,name,command,timeout=180):
        start=time.perf_counter();log=self.out/(name+'.log')
        with log.open('w',encoding='utf-8') as stream:
            stream.write(json.dumps([str(x) for x in command])+'\n');stream.flush()
            try:p=subprocess.run([str(x) for x in command],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=timeout)
            except subprocess.TimeoutExpired:raise RuntimeError(f'{name}: timeout; {log}')
        raw=log.read_text(encoding='utf-8',errors='replace')
        result=dict(name=name,command=[str(x) for x in command],returncode=p.returncode,wall_seconds=time.perf_counter()-start,log=str(log))
        if p.returncode:raise RuntimeError(f'{name}: exit {p.returncode}; {log}\n'+raw[-1800:])
        return result,raw
    def key(self,names,command):
        # Rehash tool contents each invocation; timestamps are never provenance.
        # Share the two large executable hashes across targets within this run.
        if self.tool_hashes is None:
            self.tool_hashes={str(Path(tool).resolve()):digest(tool) for tool in [compiler(),sdk()[1]]}
        payload=dict(command=[str(x) for x in command],sources={name:digest(ROOT/name) for name in dependencies(names)},tools=self.tool_hashes)
        return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    def build(self,name,inputs,outputs,command):
        key=self.key(inputs,command);paths=[ROOT/n for n in outputs];previous=self.state.get(name)
        valid=all(p.is_file() for p in paths)
        if valid and previous and previous.get('verified_build')==1 and previous['key']==key and previous['outputs']=={n:digest(ROOT/n) for n in outputs}:
            self.reused+=1;return
        # Missing/legacy records may have originated in timestamp-only adoption.
        # Only a successful compiler run establishes reusable provenance.
        result,_=self.run('build-'+name,command);self.actions.append(result)
        self.state[name]=dict(verified_build=1,key=key,outputs={n:digest(ROOT/n) for n in outputs})
        self.save()
    def save(self):
        path=self.cache/'build.json';tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(self.state,indent=2));tmp.replace(path)
    def generate(self):
        for script,(schema,outputs) in GENERATORS.items():
            key=self.key([script,schema],[sys.executable,script]);previous=self.state.get(script)
            if previous and previous['key']==key and all((ROOT/n).is_file() and previous['outputs'].get(n)==digest(ROOT/n) for n in outputs):continue
            # Generate in isolation so a schema check cannot overwrite local edits.
            with tempfile.TemporaryDirectory(prefix='gpu-contract-',dir=self.cache) as directory:
                stage=Path(directory)
                for n in [script,schema]:shutil.copy2(ROOT/n,stage/n)
                result,_=self.run('generate-'+Path(script).stem,[sys.executable,stage/script]);self.actions.append(result)
                generated={n:(stage/n).read_bytes() for n in outputs}
                for n,data in generated.items():
                    path=ROOT/n
                    if path.exists() and path.read_bytes()!=data:
                        diff=subprocess.run(['git','diff','--quiet','HEAD','--',n],cwd=ROOT,capture_output=True)
                        if diff.returncode!=0:raise RuntimeError(f'Preserving edited generated file {n}; reconcile its schema before testing')
                for n,data in generated.items():
                    if not (ROOT/n).exists() or (ROOT/n).read_bytes()!=data:(ROOT/n).write_bytes(data)
            self.state[script]=dict(key=key,outputs={n:digest(ROOT/n) for n in outputs});self.save()
    def gpu(self,target='pool_tests'):
        if target in self.ready:return self.ready[target]
        self.generate();dxc=sdk()[1]
        jobs=[job for job in shader_jobs() if target not in ['storage','spatial'] or job[0]=='storage.hlsl' or (target=='spatial' and job[0]=='spatial.hlsl')]
        for source,entry,strict in jobs:
            command=[dxc,'-T','cs_6_0',*(['-Gis'] if strict else []),'-E',entry,'-Fo',entry+'.dxil',source]
            self.build(entry,[source],[entry+'.dxil'],command)
        dest=ROOT/'zig-out/bin';dest.mkdir(parents=True,exist_ok=True)
        for _,entry,_ in jobs:
            src=ROOT/(entry+'.dxil');dst=dest/src.name
            if not dst.exists() or digest(src)!=digest(dst):shutil.copy2(src,dst)
        main={'physics':'physics_main.zig','storage':'main.zig','spatial':'spatial_main.zig'}.get(target,target+'.zig')
        sources=[main,'runtime.c']+([] if target=='storage' else ['spatial.c'])+([] if target in ['storage','spatial'] else ['physics.c','physics_verify.c','physics_tests.c'])
        command=[compiler(),'build-exe',sources[0],'-cflags','-O2','--',*sources[1:],'-I.',*headers(),'-ld3d12','-ldxgi','-ldxguid','-lkernel32','-lc','-O','ReleaseSafe','-target','x86_64-windows-gnu','-mcpu=baseline','-femit-bin=zig-out/bin/'+target+'.exe']
        self.build(target,sources,['zig-out/bin/'+target+'.exe'],command)
        self.ready[target]=dest/(target+'.exe')
        return self.ready[target]
    def cpu(self):
        path='zig-out/bin/dev_cpu_tests.exe';(ROOT/path).parent.mkdir(parents=True,exist_ok=True)
        command=[compiler(),'test','tests.zig','-O','ReleaseSafe','--test-no-exec','-femit-bin='+path]
        self.build('cpu',['tests.zig'],[path],command)
        return ROOT/path

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('level',choices=['quick','affected','full'],nargs='?',default='quick')
    parser.add_argument('--files',nargs='+',help='Explicit repository-relative changed paths instead of Git diff')
    args=parser.parse_args(argv);start=time.perf_counter()
    out=ROOT/'dev-test-results'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ');out.mkdir(parents=True)
    result=dict(level=args.level,status='FAIL',tests=[],evidence=str(out),qualification=False)
    workflow=None
    try:
        changed=args.files if args.files is not None else changed_files()
        cases=SMOKE if args.level=='quick' and args.files is None else select_cases(changed)
        if args.level=='full':cases=['all','overhead','cpu','commands','cli','device','storage','spatial']
        result.update(changed_files=changed,selected_tests=cases)
        if not cases:result['status']='SKIP';print('SKIP no affected headless tests (graphics-only/docs/build artifacts)')
        else:
            workflow=Workflow(out)
            # Serialize runs in this repository: simultaneous GPU timings are invalid.
            lock=workflow.cache/'running.lock'
            try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
            except FileExistsError:raise RuntimeError(f'Another run or stale lock: {lock}; remove only after confirming it stopped')
            os.write(fd,str(os.getpid()).encode());os.close(fd)
            try:
                for case in cases:
                    if case=='cpu':command=[workflow.cpu()]
                    elif case=='commands':command=[workflow.gpu('playground_gpu_tests')]
                    elif case=='device':command=[workflow.gpu('physics'),'--n','32','--device-tests','--out',out/'device.json']
                    elif case=='cli':command=[workflow.gpu('physics'),'--n','32','--fixture','1','--steps','4','--contacts','256','--pairs','256','--verify-every-tick','--out',out/'cli.json']
                    elif case=='storage':command=[workflow.gpu('storage'),'--n','32','--layout','1','--steps','2','--out',out/'storage.json']
                    elif case=='spatial':command=[workflow.gpu('spatial'),'--n','32','--fixture','1','--pairs','1024','--steps','2','--out',out/'spatial.json']
                    else:command=[workflow.gpu(),'--case',case,*(['--quick'] if args.level!='full' else [])]
                    test,raw=workflow.run(case,command,timeout=600 if case=='all' else 180)
                    if 'PASS' not in raw and case not in ['device','cli','cpu','storage','spatial']:raise RuntimeError(f'{case}: missing PASS evidence; {test["log"]}')
                    if case in ['device','cli','storage','spatial']:
                        payload=json.loads((out/(case+'.json')).read_text())
                        if case=='storage':assert payload['status']=='PROCESSED_AND_FULLY_VERIFIED' and payload['gpu_validation_errors']==0 and payload['n']==32
                        else:assert payload['status']=='PASS' and payload['validation_errors']==0
                        if case=='cli':assert payload['actual_processed']==32 and payload['independent_every_tick']
                        if case=='spatial':assert payload['actual_processed']==32
                        test[case]=payload
                    match=re.search(r'accepted_ticks=(\d+) rejected_ticks=(\d+) processed_objects=(\d+)',raw)
                    if match:test.update(zip(['accepted_ticks','expected_rejections','processed_objects'],map(int,match.groups())))
                    test['metrics']=[json.loads(line[7:]) for line in raw.splitlines() if line.startswith('METRIC ')]
                    test['status']='PASS';result['tests'].append(test)
                    detail=''
                    if test['metrics']:
                        m=test['metrics'][0];detail=f' GPU p50/p95 {m["gpu_us_p50"]:.1f}/{m["gpu_us_p95"]:.1f} us; CPU record {m["cpu_record_us_p50"]:.1f} us'
                    print(f'PASS {case} {test["wall_seconds"]:.2f}s'+detail,flush=True)
                result['status']='PASS'
            finally:lock.unlink()
    except Exception as error:
        result['error']=str(error);print('FAIL '+str(error),flush=True)
    finally:
        result['wall_seconds']=time.perf_counter()-start
        result['build_actions']=workflow.actions if workflow else []
        result['reused_targets']=workflow.reused if workflow else 0
        (out/'result.json').write_text(json.dumps(result,indent=2))
        print(f'{result["status"]} {args.level} {result["wall_seconds"]:.2f}s; built {len(result["build_actions"])}; evidence {out.relative_to(ROOT)}')
    return 0 if result['status'] in ['PASS','SKIP'] else 1

if __name__=='__main__':sys.exit(main())
