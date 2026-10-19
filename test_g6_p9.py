import unittest
from run_g6_p9 import compare,extended
class Qualification(unittest.TestCase):
    def test_no_execution_never_passes(self):self.assertEqual(extended([],{'status':'PASS'},0)['status'],'FAIL')
    def test_empty_prefix_is_not_determinism(self):self.assertFalse(compare([],[])['bitwise_equal'])
    def test_shorter_completed_repeat_only_claims_shared_prefix(self):
        a=[dict(type='TICK',state_hash=str(i)) for i in range(3)]
        d=compare(a,a[:2]);self.assertEqual(d['common_ticks'],2);self.assertTrue(d['bitwise_equal'])
    def test_changed_state_is_reported(self):
        def r(h):return dict(type='TICK',state_hash=h,tick=0,contacts=1,islands=1,largest=2,iterations=1,energy=1,independent={})
        d=compare([r('a')],[r('b')]);self.assertFalse(d['bitwise_equal']);self.assertEqual(d['first_difference'],0)
    def test_gpu_timing_includes_publication(self):
        from pathlib import Path
        c=Path('physics.c').read_text();self.assertLess(c.index('state_record_copy(p,(unsigned)p->pending_slot)'),c.index('s_stamp(p->d,39)'))
if __name__=='__main__':unittest.main()
