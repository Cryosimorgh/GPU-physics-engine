"""Paired, randomized scientific regression timings against immutable 75e1b73."""
from pathlib import Path
import csv,datetime,hashlib,io,json,math,random,shutil,statistics,subprocess,zipfile
r=Path(__file__).resolve().parent
out=r/'billiards-test-results'/('performance-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True)
baseline=out/'before-75e1b73';baseline.mkdir()
archive=subprocess.check_output(['git','archive','--format=zip','75e1b73'],cwd=r)
with zipfile.ZipFile(io.BytesIO(archive)) as z:z.extractall(baseline)
for shader in baseline.glob('*.dxil'):shutil.copy2(shader,baseline/'zig-out/bin'/shader.name)
randomizer=random.Random(20261017)
rows=[];runs=[]
def percentile(values,p):return sorted(values)[math.ceil(p*len(values))-1]
for n in [10000,100000,1000000]:
 for repeat in range(7):
  order=['before','after'];randomizer.shuffle(order)
  for revision in order:
   directory=baseline if revision=='before' else r
   file=out/f'{n}-{repeat}-{revision}.json';log=file.with_suffix('.log')
   command=[str(directory/'zig-out/bin/viewer.exe'),'--n',str(n),'--profile','10','--mode','0','--steps','200','--warmup','20','--quiet','--out',str(file)]
   with log.open('w') as f:subprocess.run(command,cwd=directory,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=300)
   result=json.loads(file.read_text());assert result['status']=='PASS' and result['independent_full_coverage'] and result['cleanup_memory_reconciled'];assert len(result['samples'])==200
   gpu=[x['physics_us']/1000 for x in result['samples']]
   run=dict(n=n,repeat=repeat,revision=revision,profile=10,measured_ticks=200,warmup=20,p50_ms=percentile(gpu,.5),p95_ms=percentile(gpu,.95),p99_ms=percentile(gpu,.99),cpu_submit_ms=statistics.median(x['cpu_submit_us']/1000 for x in result['samples']),allocation_ms=result['allocation_us']/1000,peak_committed=result['peak_committed'],initial_state_sha256=result['initial_state_sha256'],command=command,raw_sha256=hashlib.sha256(file.read_bytes()).hexdigest());runs.append(run)
   for x in result['samples']:rows.append(dict(n=n,repeat=repeat,revision=revision,sequence=x['sequence'],physics_ms=x['physics_us']/1000,cpu_record_ms=x['cpu_record_us']/1000,cpu_submit_ms=x['cpu_submit_us']/1000,completion_ms=x['completion_us']/1000))
   print(n,repeat,revision,'p95',round(run['p95_ms'],3),flush=True)
comparison=[]
for n in [10000,100000,1000000]:
 subset=[x for x in runs if x['n']==n];ratios=[]
 for rep in range(7):
  a=next(x for x in subset if x['repeat']==rep and x['revision']=='after');b=next(x for x in subset if x['repeat']==rep and x['revision']=='before');assert a['initial_state_sha256']==b['initial_state_sha256'];ratios.append(math.log(a['p95_ms']/b['p95_ms']))
 bootstrap=sorted(math.exp(statistics.mean(randomizer.choices(ratios,k=7))) for _ in range(10000));low=bootstrap[249];high=bootstrap[9749];estimate=math.exp(statistics.mean(ratios));status='REGRESSION' if low>1.05 else 'NO_REGRESSION_OVER_5_PERCENT' if high<=1.05 else 'INCONCLUSIVE'
 comparison.append(dict(n=n,paired_p95_ratio=estimate,bootstrap_95_percent_interval=[low,high],status=status,before_median_p95_ms=statistics.median(x['p95_ms'] for x in subset if x['revision']=='before'),after_median_p95_ms=statistics.median(x['p95_ms'] for x in subset if x['revision']=='after')))
with (out/'samples.csv').open('w',newline='') as f:
 writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
result=dict(scope='Matched scientific profile 10, simulate-only; no gameplay equivalence claim',baseline_revision='75e1b73',random_seed=20261017,repetitions_per_revision=7,measured_ticks_per_process=200,comparisons=comparison,runs=runs,cache_counters='UNAVAILABLE',display_fps='UNVERIFIED',shader_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in r.glob('*.dxil')})
(out/'results.json').write_text(json.dumps(result,indent=2));print(json.dumps(comparison,indent=2));print(out)
