"""Offline aggregation only. Never submits GPU work."""
from pathlib import Path
import csv,hashlib,json,statistics,subprocess,struct
R=Path(__file__).resolve().parent;E=R/'evidence/g6-p8b'
def read(p):return json.loads(p.read_text())
def stream(p):
    with p.open() as f:
        for line in f:yield json.loads(line)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def ticks(p):return [r for r in stream(p) if r['type']=='TICK']
def quant(values):
    s=sorted(values);return {f'p{p}':s[min(len(s)-1,int((len(s)-1)*p/100))] for p in (50,95,99)}
def main():
    original=read(E/'control-provenance.json');runs=read(E/'results.json');finish=read(E/'completion.json');suite=read(E/'broader-g6/results.json')
    assert runs['target_status']==finish['status']==suite['status']=='PASS'
    baseline=ticks(E/'control.json.jsonl');archived=ticks(R/'evidence/g6-p8a/control.json.jsonl')
    assert len(baseline)==len(archived)==4073 and all(a['state_hash']==b['state_hash'] for a,b in zip(baseline,archived))
    shaders=runs['provenance']['shaders'];changed=[n for n,h in shaders.items() if original['shader_sha256'][n]!=h]
    assert sorted(changed)==['ph_append.dxil','ph_walls.dxil']
    rails=[json.loads(line[5:]) for line in (E/'rail-numerical.log').read_text().splitlines() if line.startswith('RAIL ')]
    assert len(rails)==24 and all(r['normal_residual']<=r['threshold'] for r in rails)
    witness=next(r for r in rails if r['wall']==1 and r['kind']==4)
    # Zig's f32 text is shortest round-trip; widen its actual binary32 value.
    witness['target32_exact']=struct.unpack('<f',struct.pack('<f',witness['target32']))[0]
    result={'gate':'G6-P8b','status':'TARGETED CORRECTION PASS','G5':'DEFERRED','G6':'BLOCKED / NOT QUALIFIED','GPU-02':'UNVERIFIED','baseline':original,'baseline_all_4073_hashes_match_P8a':True,'changed_default_shaders':changed,'rails':rails,'numerical':{'before_gap32':0.0003814697265625,'geometry_gap64':0.00038141384720802307,'before_target32':-0.048828125,'before_residual':7.152557373046875e-6,'before_threshold':7.271219886650902e-7,'after_focused_GPU':witness,'scope':'After residual is independently measured in a focused rail fixture with the same stored position/radius/gap. Sustained trajectories change after the corrected target; no claim that they retain the rejected tick input.'},'sessions':[],'tests':runs['tests']+finish['tests'],'broader_suite':{'status':suite['status'],'processes':len(suite['tests']),'failures':suite['failures'],'physical_hardware_loss_tested':False},'remaining_blockers':['G5 remains DEFERRED; no solver qualification in this task','G4 GPU-02 / G6-P7 displayed-frame evidence remains UNVERIFIED','Formal G6 qualification was not executed or granted; P6 API/fault tests do not prove physical hardware-loss recovery'],'architecture_contract_changed':False,'architecture_record_preserved':True,'limitations':['Pool sustained KKT uses mandatory GPU validation, not an independent full-scene CPU contact oracle each tick','30 seconds means wall-clock sessions, including verification and logging; fixed dt remains 1/128','No performance improvement claim from divergent before/after trajectories; timing is descriptive only'],'harness_repairs':['Initial rail test used a debug device per case and timed out after 14 passes; reused one existing context for the 24 numerical cases','Copied bounded G6 script initially lacked the repository import path; failed before GPU execution, then resumed only that suite','Final runners gained overwrite protection and nonzero failure exit; exact executed scripts are preserved separately']}
    streams=[]
    for i in range(3):
        path=E/f'sustained-{i}.json';all_rows=list(stream(Path(str(path)+'.jsonl')));ts=[x for x in all_rows if x['type']=='TICK'];end=next(x for x in all_rows if x['type']=='END');probe=next(x for x in all_rows if x['type']=='ROLLBACK_PROBE');cleanup=read(path)
        assert len(ts)>4072 and end['wall_s']>=30 and all(x['valid'] and x['accepted'] and x['energy_ok'] and x['error_flags']==0 for x in ts)
        assert probe['rollback_verified'] and probe['published']==0 and cleanup['cleanup_ok'] and cleanup['validation_errors']==0 and cleanup['retired_bytes']==0
        mem={k:{'min':min(x['memory'][k] for x in ts),'max':max(x['memory'][k] for x in ts)} for k in ['committed','allocations','releases','usage','budget']}
        assert mem['committed']['min']==mem['committed']['max']==1638400 and mem['allocations']['min']==mem['allocations']['max']==25
        streams.append(ts)
        divergence=next((k for k,(a,b) in enumerate(zip(baseline,ts)) if a['state_hash']!=b['state_hash']),None)
        result['sessions'].append({'repeat':i,'accepted_ticks':len(ts),'rejected_ticks':0,'expected_rejection_probes':1,'shots':end['shots'],'first_nine_shot_ticks':[x['tick'] for x in ts if x['shot']][:9],'wall_s':end['wall_s'],'simulation_s':end['simulation_s'],'accepted_ticks_per_wall_s':len(ts)/end['wall_s'],'gpu_us':quant([x['gpu_us'][39] for x in ts]),'cpu_record_us':quant([x['cpu_record_us'] for x in ts]),'cpu_submit_us':quant([x['cpu_submit_us'] for x in ts]),'contacts_sum':sum(x['contacts'] for x in ts),'contact_ticks':sum(x['contacts']>0 for x in ts),'max_contacts':max(x['contacts'] for x in ts),'largest_island':max(x['largest'] for x in ts),'rest_ticks':sum(x['energy']==0 for x in ts),'last_hash':end['state_hash'],'tick_4072':ts[4072],'first_expected_divergence_from_old_geometry':divergence,'memory':mem,'rollback_probe':probe,'cleanup':cleanup})
    common=min(map(len,streams));assert all(len({s[i]['state_hash'] for s in streams})==1 for i in range(common))
    result['determinism']={'common_ticks':common,'all_state_hashes_equal':True,'hash_scope':'Entire allocated SoA, padding and source guard, plus retained rolling state; verified live per tick. Different wall-clock final tick counts are expected.'}
    old=R.parent/'g6-pool-diagnostic-work';saved=read(E/'original-hashes.json')
    assert all(digest(old/n)==h for n,h in saved.items())
    assert subprocess.check_output(['git','status','--porcelain'],cwd=old)==(E/'original-status.txt').read_bytes()
    result['original_workspace_preserved']=True
    result['provenance']={'branch':subprocess.check_output(['git','branch','--show-current'],cwd=R).decode().strip(),'integration_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=R).decode().strip(),'main_base':'7ec03c3','baseline_reference_commit':'2db61f6','reference_zip':'G6-P8a-Pool-Validation-20261019.zip','reference_zip_sha256':digest(R.parent/'G6-P8a-Pool-Validation-20261019.zip'),'reference_note':'Requested (2) filename was not found locally. Existing verified P8a ZIP and the identical reproduced 4073-tick trace were used.','architecture_sha256':digest(R/'docs/ENGINE_ARCHITECTURE.md')}
    assert (R/'docs/ENGINE_ARCHITECTURE.md').read_bytes()==subprocess.check_output(['git','show','origin/main:docs/ENGINE_ARCHITECTURE.md'],cwd=R)
    (E/'gate-G6-P8b.json').write_text(json.dumps(result,indent=2))
    with (E/'sessions.csv').open('w',newline='') as f:
        cols=['repeat','accepted_ticks','rejected_ticks','shots','wall_s','accepted_ticks_per_wall_s','contact_ticks','max_contacts','largest_island','rest_ticks','last_hash'];writer=csv.DictWriter(f,fieldnames=cols);writer.writeheader();writer.writerows({k:s[k] for k in cols} for s in result['sessions'])
    print(json.dumps({'status':result['status'],'ticks':[s['accepted_ticks'] for s in result['sessions']],'determinism':common,'changed_shaders':changed,'broader_processes':len(suite['tests']),'original_preserved':True}))
if __name__=='__main__':main()
