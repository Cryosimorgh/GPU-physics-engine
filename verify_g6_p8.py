"""Offline evidence reconciliation; --refresh fixes summaries, never reruns GPU tests."""
import csv,hashlib,json,subprocess,sys
from pathlib import Path
from analyze_g6_p8 import summarize,distribution
R=Path(__file__).resolve().parent;E=R/'evidence/g6-p8'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    manifest=json.loads((E/'build-manifest.json').read_text());original=json.loads((E/'original.json').read_text());results=json.loads((E/'results.json').read_text())
    for n,h in manifest['source_sha256'].items():assert sha(R/n)==h,n
    for n,h in manifest['shader_sha256'].items():assert sha(R/n)==h,n
    for n,h in manifest['binary_sha256'].items():assert sha(R/'zig-out/bin'/n)==h,n
    O=Path(original['original']);assert all(sha(O/n)==h for n,h in original['hashes'].items())
    assert subprocess.check_output(['git','status','--porcelain'],cwd=O).decode()==original['status']
    for n in ['physics.c','projected_solver.hlsl','physics.hlsl','pool.hlsl']:
        assert sha(R/n)==original['hashes'][n]
    for n,h in original['hashes'].items():
        if n.endswith('.dxil'):assert sha(R/n)==h
    corrected=[]
    for old in results['scenarios']:
        name=old['name'];path=E/(name+'.json');rows=[json.loads(x) for x in (E/(name+'.json.jsonl')).read_text().splitlines()]
        cleanup=json.loads(path.read_text());new=summarize(rows,cleanup,old['exit_code']);new.update({k:old[k] for k in ['name','command','process_wall_s']})
        ticks=[r for r in rows if r['type']=='TICK'];assert all(r['gpu_us'][39]>0 for r in ticks)
        assert all(r['memory']['committed']==ticks[0]['memory']['committed'] and r['memory']['allocations']==ticks[0]['memory']['allocations'] for r in ticks)
        assert cleanup['cleanup_ok'] and cleanup['retired_bytes']==0 and cleanup['memory']['committed']==cleanup['memory']['context_committed']
        if new['status']=='PASS':
            assert all(r['valid'] and r['oracle_ok'] and r['energy_ok'] and r['independent']['objects']==new['n'] and r['independent']['residual_ratio']<=1 for r in ticks)
            assert new['wall_session_s']>=30 and new['contact_tick_fraction']>.99
        else:
            assert ticks[-1]['error_flags']==32 and not ticks[-1]['accepted'] and ticks[-1]['rollback_verified']
            assert len([r for r in ticks if not r['valid']])==1
        new['latency_stability']='UNVERIFIED: finite observed range only; contact growth and outliers, no hard deadline qualification'
        new['deadline_misses_gpu_128Hz']=sum(r['gpu_us'][39]>7812.5 for r in ticks)
        new['runtime_gpu_allocations_constant']=True;new['runtime_commitment_constant']=True
        new['completed_simulation_duration_s']=new['accepted_ticks']/128
        corrected.append(new)
    if '--refresh' in sys.argv:
        saved=E/'results.recorded-batch.json'
        if not saved.exists():saved.write_bytes((E/'results.json').read_bytes())
        results['scenarios']=corrected;results['analysis_corrections']=['Unexpected rejection rollback now counted separately from post-session injected probes','Pool CSV independent KKT residual is blank, not placeholder zero','Future batch exits nonzero when any scenario fails; recorded original batch returned zero but individual failing process exit 1 is retained']
        (E/'results.json').write_text(json.dumps(results,indent=2))
        small=E/'small-pool.csv';savedcsv=E/'small-pool.recorded-batch.csv'
        if not savedcsv.exists():savedcsv.write_bytes(small.read_bytes())
        with small.open(newline='') as f:rr=list(csv.DictReader(f));fields=list(rr[0])
        for row in rr:row['kkt_ratio']=''
        with small.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rr)
        with (E/'comparison.csv').open('w',newline='') as f:
            w=csv.writer(f);w.writerow(['name','status','n','wall_s','simulation_s','accepted','unexpected_rejected','contact_ticks','max_contacts','max_islands','largest_island','accepted_tps','gpu_p50_ms','gpu_p95_ms','gpu_p99_ms','gpu_max_ms','CPU_submit_p50_us','committed_bytes','allocations','rollback','cleanup'])
            for s in corrected:w.writerow([s['name'],s['status'],s['n'],s['wall_session_s'],s['simulation_s'],s['accepted_ticks'],s['rejected_ticks'],s['contact_ticks'],s['max_contacts'],s['max_islands'],s['largest_island'],s['accepted_ticks_per_s'],*[s['gpu_tick_us'][k]/1000 for k in ['p50','p95','p99','max']],s['cpu_submit_us']['p50'],s['memory']['committed']['max'],s['memory']['allocations']['max'],s['rollback_verified'],s['cleanup']['cleanup_ok']])
    else:assert results['scenarios']==corrected,'summary differs: run --refresh offline'
    result={'status':'PASS','scenario_statuses':{s['name']:s['status'] for s in corrected},'raw_ticks':sum(s['accepted_ticks']+s['rejected_ticks'] for s in corrected),'compiled_source_hashes':len(manifest['source_sha256']),'DXIL_hashes':len(manifest['shader_sha256']),'preserved_original_files':len(original['hashes']),'all_cleanup_verified':True,'no_physics_changes':True,'G5':'DEFERRED','G6':'NOT QUALIFIED','GPU-02':'UNVERIFIED'}
    (E/'offline-verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
