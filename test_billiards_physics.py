from pathlib import Path
import datetime,hashlib,json,re,subprocess
r=Path(__file__).resolve().parent;out=r/'billiards-test-results'/('physics-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True)
p=subprocess.run([str(r/'zig-out/bin/pool_tests.exe')],cwd=r,capture_output=True,text=True,timeout=600)
raw=p.stdout+p.stderr;(out/'run.log').write_text(raw);print(raw,flush=True)
assert p.returncode==0,p.returncode
assert 'PASS pool analytical suite' in raw
match=re.search(r'accepted_ticks=(\d+) rejected_ticks=(\d+) processed_objects=(\d+)',raw);assert match
ticks,rejected,objects=map(int,match.groups());assert objects==16*ticks and ticks>=10000 and rejected==2
result=dict(status='PASS',accepted_ticks=ticks,expected_rejections=rejected,actual_published_objects=objects,checks=[line for line in raw.splitlines() if line.startswith('PASS ')],executable_sha256=hashlib.sha256((r/'zig-out/bin/pool_tests.exe').read_bytes()).hexdigest(),shader_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in r.glob('*.dxil')},debug_gbv='enabled on isolated analytical and rejection cases; long trajectories uninstrumented',raw_sha256=hashlib.sha256((out/'run.log').read_bytes()).hexdigest())
(out/'verification.json').write_text(json.dumps(result,indent=2));print(out)
