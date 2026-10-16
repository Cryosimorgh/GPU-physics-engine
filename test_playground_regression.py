"""Original scientific oracle and evolving generational lifecycle; no UI timing claims."""
from pathlib import Path
import datetime,json,subprocess
r=Path(__file__).resolve().parent
out=r/'playground-test-results'/('scientific-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
out.mkdir(parents=True)
results=[]
for n in [10000,100000,1000000]:
 for profile in [9,10,11]:
  path=out/f'{n}-{profile}.json'
  with path.with_suffix('.log').open('w') as f:
   subprocess.run([str(r/'zig-out/bin/viewer.exe'),'--n',str(n),'--profile',str(profile),'--steps','24','--quiet','--out',str(path)],cwd=r,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=300)
  j=json.loads(path.read_text())
  assert j['status']=='PASS' and j['independent_full_coverage'] and j['cleanup_memory_reconciled'] and j['actual_simulation_ticks']==24
  results.append(dict(n=n,profile=profile,status='PASS',actual_ticks=24,independent_full_coverage=True,cleanup_memory_reconciled=True))
  print(n,profile,'PASS',flush=True)
life=out/'lifecycle';life.mkdir()
with (life/'run.log').open('w') as f:subprocess.run([str(r/'zig-out/bin/g4_lifecycle.exe'),str(life)],cwd=r,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=180)
j=json.loads((life/'result.json').read_text());assert j['status']=='PASS' and j['validation_errors']==0 and j['evolving_ticks']==40
(out/'results.json').write_text(json.dumps(dict(scientific=results,lifecycle=j),indent=2))
print('PASS 9 independent scientific oracle cases and evolving lifecycle:',out)
