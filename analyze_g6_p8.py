"""Offline reduction of full, bounded sustained-test records."""
import math
def distribution(x):
    x=sorted(x);return {'samples':len(x),'min':min(x) if x else None,'max':max(x) if x else None,**{n:x[max(0,math.ceil(p*len(x))-1)] if x else None for n,p in [('p50',.5),('p95',.95),('p99',.99)]}}
def stages(t):
    return dict(prepare=t[1],discovery=sum(t[2+3*r]-(t[1] if r==0 else t[1+3*r]) for r in range(9)),contacts=sum(t[30+r]-t[2+3*r] for r in range(9)),graph=sum(t[3+3*r]-t[30+r] for r in range(8)),solver=sum(t[4+3*r]-t[3+3*r] for r in range(8)),validation=t[28]-t[27],publication=t[39]-t[28])
def summarize(rows,cleanup,exit_code):
    ticks=[r for r in rows if r['type']=='TICK'];start=next((r for r in rows if r['type']=='START'),{});end=next((r for r in rows if r['type']=='END'),None)
    accepted=[r for r in ticks if r['accepted']];contact=[r for r in accepted if r['contacts']>0];elapsed=ticks[-1]['elapsed_s'] if ticks else 0
    probes=[r for r in rows if r['type']=='ROLLBACK_PROBE']
    failures=[r for r in ticks if not r['accepted']]
    reliable=exit_code==0 and cleanup.get('status')=='PASS' and end is not None and elapsed>=29.99 and ticks and all(r['valid'] for r in ticks) and bool(contact) and len(probes)==1 and probes[0]['rollback_verified']
    out={'status':'PASS' if reliable else 'FAIL','cleanup':cleanup,'exit_code':exit_code,'n':start.get('n'),'fixture':start.get('fixture'),'flags':start.get('flags'),
         'wall_session_s':elapsed,'simulation_s':end['simulation_s'] if end else len(accepted)/128,'accepted_ticks':len(accepted),'rejected_ticks':sum(not r['accepted'] for r in ticks),'expected_rejection_probes':len(probes),'rollback_verified':bool(probes and probes[0]['rollback_verified']),
         'accepted_ticks_per_s':len(accepted)/elapsed if elapsed else None,'contact_ticks':len(contact),'contact_tick_fraction':len(contact)/len(accepted) if accepted else 0,
         'contact_observations':sum(r['contacts'] for r in accepted),'max_contacts':max((r['contacts'] for r in accepted),default=0),'max_islands':max((r['islands'] for r in accepted),default=0),'largest_island':max((r['largest'] for r in accepted),default=0),
         'max_active':max((r['active'] for r in accepted),default=0),'max_solved_bodies':max((r['solved_bodies'] for r in accepted),default=0),'kkt_scope':'GPU mandatory KKT every tick; existing pool analytical regressions' if start.get('fixture')==13 else 'GPU mandatory checks plus independent CPU full-contact oracle every tick',
         'independent_failures':sum(not r['oracle_ok'] for r in ticks),'energy_failures':sum(not r['energy_ok'] for r in ticks),'invalid_state_ticks':sum(not r['valid'] for r in ticks),'shots':end.get('shots') if end else None}
    for key in ['cpu_record_us','cpu_submit_us','blocking_us','api_us','verification_us','wall_tick_us','iterations','max_iterations','energy']:
        out[key]=distribution([r[key] for r in accepted])
    out['gpu_tick_us']=distribution([r['gpu_us'][39] for r in accepted]);out['contact_gpu_tick_us']=distribution([r['gpu_us'][39] for r in contact])
    out['stage_us']={k:distribution([stages(r['gpu_us'])[k] for r in accepted]) for k in ['prepare','discovery','contacts','graph','solver','validation','publication']}
    out['memory']={k:distribution([r['memory'][k] for r in ticks]) for k in ['committed','allocations','releases','usage','budget']}
    out['windows']=[dict(start_s=w,end_s=w+5,ticks=len(rr),gpu_tick_us=distribution([r['gpu_us'][39] for r in rr]),committed=distribution([r['memory']['committed'] for r in rr]),allocations=distribution([r['memory']['allocations'] for r in rr])) for w in range(0,30,5) if (rr:=[r for r in accepted if w<=r['elapsed_s']<w+5])]
    out['post_session_rollback_probe_verified']=bool(probes and all(r['rollback_verified'] for r in probes))
    out['unexpected_rollback_verified']=all(r.get('rollback_verified') is True for r in failures) if failures else None
    out['rollback_verified']=out['post_session_rollback_probe_verified'] or out['unexpected_rollback_verified'] is True
    return out
