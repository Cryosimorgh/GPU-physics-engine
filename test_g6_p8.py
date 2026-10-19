import unittest
from analyze_g6_p8 import summarize,distribution
class Contracts(unittest.TestCase):
    def test_no_run_cannot_qualify(self):self.assertEqual(summarize([],{'status':'PASS'},0)['status'],'FAIL')
    def test_cleanup_cannot_substitute_for_duration(self):self.assertEqual(summarize([{'type':'START','n':8192}],{'status':'PASS'},0)['accepted_ticks'],0)
    def test_missing_quantiles(self):self.assertIsNone(distribution([])['p99'])
    def test_rank(self):self.assertEqual(distribution(range(100))['p99'],98)
    def test_rejected_state_rollback_is_not_lost_without_end_probe(self):
        row=dict(type='TICK',accepted=False,valid=False,elapsed_s=1,oracle_ok=True,energy_ok=True,rollback_verified=True,memory=dict(committed=1,allocations=1,releases=0,usage=1,budget=100))
        r=summarize([row],{'status':'FAIL'},1);self.assertTrue(r['unexpected_rollback_verified']);self.assertTrue(r['rollback_verified']);self.assertEqual(r['status'],'FAIL')
    def test_batch_fails_exit_status(self):
        from pathlib import Path
        self.assertIn("return 0 if results['status']=='PASS' else 1",Path('run_g6_p8.py').read_text())
    def test_scoped_to_cli(self):
        from pathlib import Path
        s=Path('sustained_physics.zig').read_text();self.assertIn('c.ph_verify(p,cfg,tick+1',s);self.assertIn('seconds>30',s);self.assertIn('if(!valid)return error.QualificationFailure',s);self.assertIn('c.ph_inject(p,1)',s)
if __name__=='__main__':unittest.main()
