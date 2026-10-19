"""Read-only evidence verification, no GPU work, window, or rebuilding."""
import csv,hashlib,json,subprocess
from pathlib import Path
from analyze_g6_p7 import verify,summarize,quantiles
R=Path(__file__).resolve().parent;E=R/'evidence/g6-p7'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    from build_billiards import verify_build
    build=verify_build();session=json.loads((E/'session.json').read_text());original=json.loads((E/'original.json').read_text())
    assert session['binary_sha256']==build['executable_sha256']
    assert session['source_sha256']==build['source_sha256'] and session['shader_sha256']==build['shader_sha256']
    assert session['GPU-02']=='UNVERIFIED' and session['displayed_fps'] is None and session['display_latency_valid_samples']==0 and session['raw_ETL'] is None
    old=Path(original['original']);assert all(digest(old/n)==h for n,h in original['hashes'].items())
    assert subprocess.check_output(['git','status','--porcelain'],cwd=old).decode()==original['status']
    assert all(digest(R/n)==h for n,h in original['hashes'].items() if n.endswith('.dxil'))
    assert digest(R/'projected_solver.hlsl')==original['hashes']['projected_solver.hlsl']
    pooled=[];modes={0:[],1:[]}
    for case in session['cases']:
        payload=json.loads(next((R/case['directory']).glob('session-*/samples.json')).read_text())
        assert verify(payload['records'],case['removal']) and not payload['dropped_telemetry_samples']
        assert all(case[k]==v for k,v in summarize(payload['records']).items())
        if not case['removal']:modes[case['mode']]+=payload['records']
    for mode,records in modes.items():
        frames=[r for r in records if r['type']=='FRAME'];sim=[r for r in frames if r['simulated']];row={'mode':mode,'frames':len(frames),'ticks':len(sim)}
        for key in ['physics_ms','render_ms','cpu_record_ms','cpu_submit_ms','cpu_frame_ms','present_ms','acceptance_wait_ms','generation_age']:
            row[key]=quantiles([r[key] for r in (sim if key=='physics_ms' else frames)])
        row['message_to_ack_ms']=quantiles([c['message_to_physics_ack_ms'][0] for c in session['cases'] if c['mode']==mode and not c['removal']])
        row['GPU-02']='UNVERIFIED';row['displayed_fps']=None;pooled.append(row)
    (E/'pooled.json').write_text(json.dumps(pooled,indent=2))
    with (E/'pooled.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['mode','frames','ticks','metric','samples','p50','p95','p99'])
        for row in pooled:
            for key,value in row.items():
                if isinstance(value,dict):w.writerow([row['mode'],row['frames'],row['ticks'],key,*[value[x] for x in ['samples','p50','p95','p99']]])
    result={'status':'PASS','cases':len(session['cases']),'preserved_original_tracked_files':len(original['hashes']),
        'unchanged_DXIL':len(build['shader_sha256']),'shader_source_unchanged':True,'compiled_source_matches':True,'GPU-02':'UNVERIFIED'}
    (E/'verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result));print(json.dumps(pooled,indent=2))
if __name__=='__main__':main()
