"""Read-only local-console/active-display and ETW preflight. No elevation."""
import ctypes as C,json,subprocess,sys,urllib.request,hashlib
from ctypes import wintypes as W
from pathlib import Path
class Luid(C.Structure):_fields_=[('low',W.DWORD),('high',W.LONG)]
class Rat(C.Structure):_fields_=[('num',W.UINT),('den',W.UINT)]
class Source(C.Structure):_fields_=[('adapter',Luid),('id',W.UINT),('mode',W.UINT),('status',W.UINT)]
class Target(C.Structure):_fields_=[('adapter',Luid),('id',W.UINT),('mode',W.UINT),('technology',W.UINT),('rotation',W.UINT),('scaling',W.UINT),('refresh',Rat),('scan',W.UINT),('available',W.BOOL),('status',W.UINT)]
class DisplayPath(C.Structure):_fields_=[('source',Source),('target',Target),('flags',W.UINT)]
class Mode(C.Structure):_fields_=[('data',C.c_byte*64)]
class Header(C.Structure):_fields_=[('type',W.UINT),('size',W.UINT),('adapter',Luid),('id',W.UINT)]
class TargetName(C.Structure):_fields_=[('header',Header),('flags',W.UINT),('tech',W.UINT),('manufacturer',W.WORD),('product',W.WORD),('connector',W.UINT),('friendly',W.WCHAR*64),('path',W.WCHAR*128)]
class SourceName(C.Structure):_fields_=[('header',Header),('name',W.WCHAR*32)]
def probe(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);u=C.windll.user32;k=C.windll.kernel32
    session=W.DWORD();k.ProcessIdToSessionId(k.GetCurrentProcessId(),C.byref(session))
    result={'process_session':session.value,'active_console_session':k.WTSGetActiveConsoleSessionId(),'remote_session':bool(u.GetSystemMetrics(0x1000)),'primary_pixels':[u.GetSystemMetrics(0),u.GetSystemMetrics(1)],'screens':[]}
    np,nm=W.UINT(),W.UINT();err=u.GetDisplayConfigBufferSizes(2,C.byref(np),C.byref(nm))
    if err==0:
        paths=(DisplayPath*np.value)();modes=(Mode*nm.value)();err=u.QueryDisplayConfig(2,C.byref(np),paths,C.byref(nm),modes,None)
        if err==0:
            for p in paths[:np.value]:
                t=TargetName();t.header=Header(2,C.sizeof(t),p.target.adapter,p.target.id)
                s=SourceName();s.header=Header(1,C.sizeof(s),p.source.adapter,p.source.id)
                te=u.DisplayConfigGetDeviceInfo(C.byref(t));se=u.DisplayConfigGetDeviceInfo(C.byref(s))
                result['screens'].append({'name':t.friendly,'monitor_path':t.path,'source':s.name,'source_id':p.source.id,'adapter_luid':[p.source.adapter.low,p.source.adapter.high],'target_id':p.target.id,'technology':p.target.technology,'target_available':bool(p.target.available),'active':bool(p.flags&1),'refresh_num':p.target.refresh.num,'refresh_den':p.target.refresh.den,'edid_valid':bool(t.flags&4),'name_errors':[te,se]})
    result['display_config_error']=err
    result['physical_local_verified']=bool(not err and not result['remote_session'] and session.value==result['active_console_session'] and result['screens'] and all(s['active'] and s['target_available'] and s['technology'] in (0,4,5,6,10,11,12,13,16,0x80000000) and s['edid_valid'] and s['name_errors']==[0,0] for s in result['screens']))
    for name,cmd in [('session',['query','session']),('token',['whoami','/all'])]:
        p=subprocess.run(cmd,capture_output=True,timeout=10);(out/(name+'.log')).write_bytes(p.stdout+p.stderr)
    (out/'display.json').write_text(json.dumps(result,indent=2))
    return result
if __name__=='__main__':
    out=Path(sys.argv[1] if len(sys.argv)>1 else 'evidence/g6-p7/preflight')
    if (out/'preflight.json').exists():
        print('Recorded preflight preserved; select a new output directory for a fresh probe.');sys.exit(0)
    r=probe(out)
    exe=out/'PresentMon-2.6.0-x64.exe'
    if not exe.exists():
        try:
            with urllib.request.urlopen('https://github.com/GameTechDev/PresentMon/releases/download/v2.6.0/PresentMon-2.6.0-x64.exe',timeout=45) as f:exe.write_bytes(f.read())
        except Exception as e:(out/'download-error.log').write_text(repr(e))
    if exe.exists():
        for name,args in [('help',['--help']),('permission',['--timed','1','--terminate_after_timed','--no_console_stats','--output_file',str((out/'permission.csv').resolve())])]:
            p=subprocess.run([str(exe.resolve()),*args],capture_output=True,timeout=15);(out/(name+'.log')).write_bytes(p.stdout+p.stderr)
            r[name+'_exit']=p.returncode
        r['presentmon_sha256']=hashlib.sha256(exe.read_bytes()).hexdigest()
    (out/'preflight.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))
