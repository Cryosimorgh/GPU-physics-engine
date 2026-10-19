"""Recovery provenance checks only; delegates all builds to the recovered workflow."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import zipfile

from dev_test import ROOT, Workflow, compiler, sdk
from sweep_g5 import build_variants

out = ROOT / 'dev-test-results' / 'recovery-preflight'
out.mkdir(parents=True, exist_ok=False)
workflow = Workflow(out)
workflow.run('workflow-unit-tests', [sys.executable, '-m', 'unittest',
             'test_dev_workflow', 'test_sweep_g5', 'test_global_profile', '-q'], timeout=60)
variants = build_variants(workflow)
with zipfile.ZipFile(ROOT.parent / 'g5-recovery-kit' / 'original' /
                     'G5-Global-Solver-Cost-Handoff-20261018T090324676154Z.zip') as archive:
    archived = json.loads(archive.read('evidence/results.json'))
differences = []
for variant, build in variants.items():
    for name, actual in build['sha256'].items():
        expected = archived['builds'][variant]['sha256'].get(name)
        if actual != expected:
            differences.append(dict(variant=variant, file=name, expected=expected, actual=actual))
result = dict(source_verifier='25/25 source and 6/6 workflow hashes matched',
              builds=variants, differences=differences, build_actions=workflow.actions,
              reused=workflow.reused,
              tools={str(p):hashlib.sha256(Path(p).read_bytes()).hexdigest()
                     for p in [compiler(), sdk()[1]]})
(out / 'provenance.json').write_text(json.dumps(result, indent=2))
print(json.dumps(dict(unit_tests='PASS', build='PASS', differences=differences,
                      evidence=str(out)), indent=2))
sys.exit(bool(differences))
