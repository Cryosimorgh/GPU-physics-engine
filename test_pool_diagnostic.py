import json,re,unittest
from pathlib import Path
from analyze_pool_fault import analyze
from run_g6_p8a import decode
class DiagnosticContract(unittest.TestCase):
    def test_layout_does_not_grow_or_alias(self):
        p=json.loads(Path('pool-schema.json').read_text());self.assertEqual(p['extension_bytes'],768);self.assertEqual(p['failure_diagnostic_offset'],p['position_y_offset']+64);self.assertEqual(p['failure_diagnostic_offset']+p['failure_diagnostic_bytes'],p['guard_offset'])
    def test_default_disabled_first_writer_latch(self):
        s=Path('pool-failure-diagnostic.hlsl').read_text();self.assertIn('#define G6_POOL_FAILURE_DIAGNOSTICS 0',s);self.assertIn('m.InterlockedCompareExchange(at,0,code,previous)',s);self.assertIn('if(previous!=0)return',s)
    def test_normal_shaders_are_byte_identical(self):
        E=Path('evidence/g6-p8a');self.assertEqual(json.loads((E/'control-provenance.json').read_text())['shader_sha256'],json.loads((E/'diagnostic-build.json').read_text())['normal_shaders'])
    def test_every_physics_flag32_site_is_traced(self):
        s=Path('physics.hlsl').read_text();self.assertEqual(len(re.findall(r'fail\(32\)',s)),6)
        self.assertEqual(set(map(int,re.findall(r'poolFault\((\d+),',s))),set(range(1,10)))
        self.assertNotIn('POOL_FAILURE_DIAGNOSTIC_OFFSET',s[s.index('void ph_clear'):s.index('void ph_prepare')])
    def test_two_repeated_numeric_witnesses(self):
        E=Path('evidence/g6-p8a');a=analyze(E/'diagnostic-0.json');b=analyze(E/'diagnostic-1.json');self.assertEqual(a,b);self.assertEqual(a['normal_residual_stored_equation'],0);self.assertGreater(a['ratio'],9)
    def test_no_math_correction(self):
        old=json.loads(Path('evidence/g6-p8a/original-workspace.json').read_text())
        import hashlib
        for n in ['projected_solver.hlsl','physics-math.hlsl','pool.hlsl','physics.c']:
            self.assertEqual(hashlib.sha256(Path(n).read_bytes()).hexdigest(),old['hashes'][n])
if __name__=='__main__':unittest.main()
