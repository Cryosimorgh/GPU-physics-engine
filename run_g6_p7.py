"""One bounded, serialized real-window P7 session. Never estimates display FPS.
Build once: python build_billiards.py
Run once: python run_g6_p7.py
"""
import csv,hashlib,json,subprocess,sys,time
from pathlib import Path
from build_billiards import verify_build
from display_probe import probe
from analyze_g6_p7 import summarize,verify
R=Path(__file__).resolve().parent;E=R/'evidence/g6-p7'
def main():
    E.mkdir(parents=True,exist_ok=True)
    if (E/'session.json').exists():raise RuntimeError('Session already exists; preserve evidence, choose a new revision for repeat testing')
    manifest=verify_build();before=probe(E/'session-preflight')
    if not before['physical_local_verified']:raise RuntimeError('Verified physical local display required; no viewer started')
    start=time.monotonic();result={'GPU-02':'UNVERIFIED','G5':'DEFERRED','G6':'NOT QUALIFIED','cases':[],
        'display_blocker':json.loads((E/'preflight/preflight.json').read_text()),'binary_sha256':manifest['executable_sha256'],
        'source_sha256':manifest['source_sha256'],'shader_sha256':manifest['shader_sha256'],
        'displayed_fps':None,'display_latency_valid_samples':0,'raw_ETL':None,
        'controlled_API_removal':True,'physical_hardware_recovery_tested':False}
    try:
        # ABBA repeat in one session, followed by one controlled removal per mode.
        for idx,(mode,removal) in enumerate([(0,False),(1,False),(1,False),(0,False),(0,True),(1,True)]):
            case=E/f'case-{idx}-mode-{mode}';case.mkdir();test={'mode':mode,'removal':removal,'directory':str(case.relative_to(R)),'status':'FAIL'}
            result['cases'].append(test)
            cmd=[str(R/'zig-out/bin/GPUPhysicsBilliards.exe'),'--automated','--quiet','--output-dir',str(case),'--n','16','--profile','13','--depth','2','--vsync','1','--nonblocking',str(mode),'--steps','320','--self-test','41' if removal else '40']
            test['command']=cmd;now=time.monotonic()
            with (case/'process.log').open('wb') as log:
                try:p=subprocess.run(cmd,cwd=R,stdout=log,stderr=subprocess.STDOUT,timeout=15);test['exit_code']=p.returncode
                except subprocess.TimeoutExpired:raise RuntimeError(f'{case.name}: bounded viewer timeout')
            test['wall_s']=time.monotonic()-now;assert test['exit_code']==0,case.name+': process failure'
            sessions=list(case.glob('session-*'));assert len(sessions)==1;session=sessions[0]
            data=json.loads((session/'samples.json').read_text());assert data['dropped_telemetry_samples']==0
            verify(data['records'],removal);test.update(summarize(data['records']));test['qpc_frequency']=data['qpc_frequency']
            test['message_to_physics_ack_ms']= [q*1000/data['qpc_frequency'] for q in test['message_to_ack_qpc']]
            test['status']='PASS'
            # Overall session is deliberately bounded, not a benchmark campaign.
            if time.monotonic()-start>65:raise RuntimeError('Session time budget exceeded')
        after=probe(E/'session-postflight');assert before['screens']==after['screens'],'display path changed'
        result['application_status']='PASS';result['display_status']='UNVERIFIED: PresentMon exit 6, ETW access denied; no displayed-frame/latency evidence'
    except Exception as e:result['application_status']='FAIL';result['error']=repr(e)
    finally:
        result['wall_s']=time.monotonic()-start;(E/'session.json').write_text(json.dumps(result,indent=2))
        columns=['mode','removal','status','completed_frames','simulated_ticks','contact_ticks','max_contacts','max_island','wall_s','displayed_fps']
        with (E/'comparison.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');w.writeheader();w.writerows(result['cases'])
    print('mode removal result frames ticks contactTicks maxContacts GPU-p50-ms CPUwait-p50-ms age-p95')
    for c in result['cases']:print(c['mode'],c['removal'],c['status'],c.get('completed_frames'),c.get('simulated_ticks'),c.get('contact_ticks'),c.get('max_contacts'),c.get('physics_ms',{}).get('p50'),c.get('acceptance_wait_ms',{}).get('p50'),c.get('generation_age',{}).get('p95'))
    print(result.get('application_status'),'; GPU-02 UNVERIFIED; no display FPS reported; evidence',E)
    return 0 if result.get('application_status')=='PASS' else 1
if __name__=='__main__':sys.exit(main())
