"""Serialized P10 qualification entry point. Does not start GUI or package builds."""
from pathlib import Path
import json,subprocess,sys,time,hashlib,os
R=Path(__file__).resolve().parent;E=R/'evidence/p10'
def main():
    E.mkdir(parents=True,exist_ok=True)
    result={'status':'FAIL','scope':'P10 bounded native3D foundation; not production release','tests':[]}
    files=['physics3.c','physics3.h','physics3.hlsl','physics3-schema.json','build_physics3.py','test_physics3.py','run_p10.py']
    hashes=lambda:{n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in files}
    result['input_hashes']=hashes();lock=E/'running.lock'
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(fd,str(os.getpid()).encode());os.close(fd)
    try:
        for name,args in [('build',['build_physics3.py']),('native',['test_physics3.py','--smoke']),('stress',['test_physics3.py','--stress','10000','100000','1000000']),('python-regressions',['-m','unittest','test_dev_workflow','test_pool_rail_gap','test_g6_p9','-q'])]:
            cmd=[sys.executable,*args];start=time.perf_counter()
            with (E/(name+'.log')).open('w') as f:
                f.write(json.dumps(cmd)+'\n');f.flush();p=subprocess.run(cmd,cwd=R,stdout=f,stderr=subprocess.STDOUT,timeout=180)
            item={'name':name,'command':cmd,'exit':p.returncode,'seconds':time.perf_counter()-start};result['tests'].append(item)
            print(('PASS ' if not p.returncode else 'FAIL ')+name,flush=True)
            if p.returncode:raise RuntimeError(name+': '+(E/(name+'.log')).read_text()[-2500:])
        assert result['input_hashes']==hashes(),'Inputs changed during execution'
        result['status']='PASS'
    except Exception as error:result['error']=str(error);print(result['error'],flush=True)
    finally:
        lock.unlink();(E/'run.json').write_text(json.dumps(result,indent=2))
    return result['status']!='PASS'
if __name__=='__main__':raise SystemExit(main())
