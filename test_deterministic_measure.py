"""Measurement-mode contracts only; production physics is not reimplemented."""
import hashlib
from pathlib import Path
import unittest
from dev_test import ROOT
from measure_repeatability import ordering_signatures

class MeasurementContracts(unittest.TestCase):
    def test_retained_solver_math_is_byte_preserved(self):
        self.assertEqual(hashlib.sha256((ROOT/'projected_solver.hlsl').read_bytes()).hexdigest(),
                         '10c5ee6541c7799119a9578b304c51f8d3de3938e2221613894bc7fae75d5c24')

    def test_measurement_is_disabled_and_bounded_by_default(self):
        s=(ROOT/'measurement-schedule.hlsl').read_text()
        self.assertIn('#define G5_DETERMINISTIC_MEASURE 0',s)
        self.assertIn('G5_MEASURE_MAX_BODIES=1024',s)
        self.assertIn('G5_MEASURE_MAX_CONTACTS=2048',s)
        self.assertIn('if(roots!=1){fail(64);return;}',s)

    def test_canonicalization_moves_double_impulses_with_records(self):
        s=(ROOT/'measurement-schedule.hlsl').read_text()
        self.assertIn('c.Store2(CT(LAMBDA_N,j),ln)',s)
        self.assertIn('c.Store2(CT(LAMBDA_T,j),lt)',s)
        self.assertIn('c.Load4(o+64)',s)

    def test_insertion_predecessor_load_is_inside_nonzero_index_loop(self):
        s=(ROOT/'measurement-schedule.hlsl').read_text()
        self.assertIn('while(j>0){\n   if(!g5KeyLess',s)
        self.assertNotIn('while(j>0&&',s)

    def test_timestamp_query_capacity_and_production_default(self):
        s=(ROOT/'physics.c').read_text()
        self.assertIn('#define G5_MEASURE_TIMESTAMPS 0',s)
        self.assertIn('#define G5_TIMESTAMP_COUNT 48',s)
        self.assertIn('#define G5_TIMESTAMP_COUNT 40',s)
        self.assertIn('s_stamp(p->d,47)',s)
        self.assertIn('D3D12_QUERY_HEAP_TYPE_TIMESTAMP,64',(ROOT/'runtime.c').read_text())

if __name__=='__main__':unittest.main()
