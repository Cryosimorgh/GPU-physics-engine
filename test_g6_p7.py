import unittest
from analyze_g6_p7 import summarize,quantiles,verify
class EvidenceTests(unittest.TestCase):
    def test_present_counts_never_become_display_counts(self):
        r=summarize([{'type':'SUBMITTED'},{'type':'PRESENT_RETURN'}]*120)
        self.assertEqual(r['present_returns'],120);self.assertIsNone(r['displayed_fps']);self.assertIsNone(r['displayed_images']);self.assertIsNone(r['dropped_images']);self.assertEqual(r['GPU-02'],'UNVERIFIED')
    def test_empty_latency_has_no_samples(self):self.assertEqual(quantiles([]),dict(samples=0,p50=None,p95=None,p99=None))
    def test_quantiles(self):self.assertEqual(quantiles(range(100))['p95'],94)
    def test_no_gpu_completion_rejected(self):
        with self.assertRaisesRegex(AssertionError,'no actual GPU'):verify([{'type':'PRESENT_RETURN'}])
    def test_source_guardrails(self):
        from pathlib import Path
        v=Path('viewer.c').read_text();b=Path('bench_interactive.inc').read_text();r=Path('render-consumer.inc').read_text()
        self.assertIn('vimage_event(v,f,"SUBMITTED")',v);self.assertIn('vimage_event(v,f,"PRESENT_RETURN")',v)
        self.assertIn('r.age=f->snapshot_age',b);self.assertIn('publication_clock[clock].generation==f->generation',r)
        self.assertIn('s->render[0]==0',v)
if __name__=='__main__':unittest.main()
