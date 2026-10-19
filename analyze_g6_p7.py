"""Application frame metrics. No display-rate estimate without an external trace."""
import math
def quantiles(values):
    x=sorted(values)
    return {'samples':len(x),**{name:x[max(0,math.ceil(p*len(x))-1)] if x else None for name,p in [('p50',.5),('p95',.95),('p99',.99)]}}
def summarize(records):
    frames=[r for r in records if r['type']=='FRAME'];sim=[r for r in frames if r['simulated']]
    submissions=[r for r in records if r['type']=='SUBMITTED'];presents=[r for r in records if r['type']=='PRESENT_RETURN']
    result={'submitted':len(submissions),'present_returns':len(presents),'completed_frames':len(frames),'simulated_ticks':len(sim),
            'displayed_fps':None,'display_latency_ms':quantiles([]),'displayed_images':None,'dropped_images':None,'repeated_refreshes':None,
            'GPU-02':'UNVERIFIED','external_display_trace':False,'photon_latency':'UNVERIFIED: optical instrument required',
            'max_contacts':max((r['contacts'] for r in sim),default=0),'contact_ticks':sum(r['contacts']>0 for r in sim),
            'contact_observations':sum(r['contacts'] for r in sim),'max_island':max((r['largest'] for r in sim),default=0),
            'errors':sum(r['errors'] for r in frames),'paused_render_frames':sum(not r['simulated'] for r in frames)}
    for key in ['physics_ms','render_ms','cpu_record_ms','cpu_submit_ms','cpu_frame_ms','present_ms','acceptance_wait_ms','generation_age']:
        source=sim if key=='physics_ms' else frames
        result[key]=quantiles([r[key] for r in source])
    for key in ['committed','usage','allocations','releases']:
        result[key]={'min':min((r[key] for r in frames),default=0),'max':max((r[key] for r in frames),default=0)}
    inputs=[r for r in records if r['type']=='AUTOMATED_CUE_INPUT'];acks=[r for r in records if r['type']=='IMPULSE_COMMITTED']
    result['input_messages']=len(inputs);result['committed_commands']=len(acks)
    result['message_to_ack_qpc']=[a['qpc']-i['qpc'] for i,a in zip(inputs,acks)]
    return result

def verify(records,removal=False):
    types=[r['type'] for r in records];frames=[r for r in records if r['type']=='FRAME']
    assert frames,'no actual GPU frame completions'
    assert not any(r['errors'] or r['rejected'] for r in frames),'physics/render rejection'
    assert sum(t=='AUTOMATED_CUE_INPUT' for t in types)==sum(t=='IMPULSE_COMMITTED' for t in types)==1,'command acknowledgement'
    assert types.count('PAUSE')==types.count('RESUME')==1 and any(not r['simulated'] for r in frames),'pause/resume'
    assert max(r['contacts'] for r in frames)>0,'collision workload never reached contacts'
    byframe={r['frame']:r for r in frames};submitted={r['frame']:r for r in records if r['type']=='SUBMITTED'}
    presents={r['frame']:r for r in records if r['type']=='PRESENT_RETURN'}
    assert len(submitted)==types.count('SUBMITTED') and len(presents)==types.count('PRESENT_RETURN'),'duplicate images'
    for r in frames:
        s,p=submitted[r['frame']],presents[r['frame']]
        assert s['generation']==p['generation']==r['generation'],'generation changed after draw submission'
        assert s['submit_qpc']<=p['present_begin_qpc']<=p['present_end_qpc']<=r['qpc'],'QPC order'
        assert r['present_result']==0 and r['present_id']>0 and r['swap_chain']!=0,'Present API failure'
        assert r['snapshot_start_qpc']==0 or r['snapshot_start_qpc']<=r['submit_qpc'],'invalid snapshot clock'
    assert len({(r['swap_chain'],r['present_id']) for r in presents.values()})==len(presents),'ambiguous Present IDs'
    for a in (r for r in records if r['type']=='IMPULSE_COMMITTED'):
        assert a['frame'] in byframe and a['generation']==byframe[a['frame']]['generation'],'acknowledged different tick'
    if removal:
        assert types.count('CONTROLLED_REMOVE_REQUEST')==types.count('EXPECTED_DEVICE_REMOVAL_STOP')==types.count('CONTROLLED_REMOVAL_TEARDOWN_PASS')==1,'removal/teardown incomplete'
        request=next(r for r in records if r['type']=='CONTROLLED_REMOVE_REQUEST')
        assert not any(r['qpc']>request['qpc'] and r['type'] in ('SUBMITTED','PRESENT_RETURN') for r in records),'submission after removal'
    else:
        assert 'CLEAN_EXIT' in types and len(submitted)==len(presents)==len(frames)==298,'ordinary shutdown lost work'
    return True
