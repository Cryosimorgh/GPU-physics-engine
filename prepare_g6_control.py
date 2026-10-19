"""Prepare the unchanged source control without editing this working tree."""
from pathlib import Path
import shutil,json,subprocess,zipfile,io,importlib.util
from dev_test import ROOT,digest
BASELINE='a147f6bf265bc82060107358cd41157e38d371c2'
def prepare():
 out=ROOT/'evidence/g6-p1';out.mkdir(parents=True,exist_ok=True)
 dest=out/'control';record=out/'control-build.json'
 if record.exists():
  saved=json.loads(record.read_text())
  if saved.get('baseline_revision',BASELINE)!=BASELINE:raise RuntimeError('Control baseline revision differs')
  if all((dest/n).is_file() and digest(dest/n)==h for n,h in saved['hashes'].items()):
   saved['baseline_revision']=BASELINE;record.write_text(json.dumps(saved,indent=2));return dest
 # Git archive provides sources only; pre-existing DXIL is never adopted.
 stage=ROOT/'.dev-test-cache/g6-control-source';stage.mkdir(parents=True,exist_ok=True)
 raw=subprocess.run(['git','archive','--format=zip',BASELINE],cwd=ROOT,capture_output=True,check=True).stdout
 with zipfile.ZipFile(io.BytesIO(raw)) as archive:
  for entry in archive.infolist():
   name=Path(entry.filename)
   if len(name.parts)!=1 or name.suffix not in {'.c','.h','.inc','.hlsl','.zig','.py','.json'}:continue
   (stage/name).write_bytes(archive.read(entry))
 spec=importlib.util.spec_from_file_location('g6_control_workflow',stage/'dev_test.py')
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 workflow=module.Workflow(out);dest.mkdir(exist_ok=True)
 for target in ['physics','pool_tests']:
  exe=workflow.gpu(target);shutil.copy2(exe,dest/exe.name)
 for p in (stage/'zig-out/bin').glob('*.dxil'):shutil.copy2(p,dest/p.name)
 record.write_text(json.dumps({'baseline_revision':BASELINE,'actions':workflow.actions,'reused':workflow.reused,'hashes':{p.name:digest(p) for p in dest.iterdir()}},indent=2))
 return dest
if __name__=='__main__':print('Verified unchanged control:',prepare())
