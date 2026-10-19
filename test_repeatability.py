"""Signature sensitivity checks; no physics implementation or GPU execution."""
import unittest
from measure_repeatability import ordering_signatures, stats, conditional

class SignatureTests(unittest.TestCase):
    def example(self,root=None,groups=None,contacts=None):
        return ordering_signatures(contacts or [(0,1,100),(2,3,200),(1,2,300)],
            root or [0,1,2],groups or [[0,1],[2]],[0,1,2,3],[[0]*4]*4)

    def test_mutable_array_order_does_not_change_contact_set(self):
        a=self.example();b=self.example(root=[2,1,0])
        self.assertEqual(a['contact_set'],b['contact_set']);self.assertNotEqual(a['root_order'],b['root_order'])

    def test_within_color_order_is_not_different_arithmetic(self):
        a=self.example();b=self.example(groups=[[1,0],[2]])
        self.assertEqual(a['arithmetic_schedule'],b['arithmetic_schedule'])
        self.assertNotEqual(a['exact_dispatch_schedule'],b['exact_dispatch_schedule'])

    def test_color_pass_sequence_is_semantically_distinct(self):
        a=self.example();b=self.example(groups=[[2],[0,1]])
        self.assertNotEqual(a['arithmetic_schedule'],b['arithmetic_schedule'])

    def test_contact_record_placement_is_part_of_exact_dispatch(self):
        a=self.example()
        b=self.example(contacts=[(1,2,300),(2,3,200),(0,1,100)],root=[2,1,0],groups=[[2,1],[0]])
        self.assertEqual(a['arithmetic_schedule'],b['arithmetic_schedule'])
        self.assertEqual(a['colored_stream'],b['colored_stream'])
        self.assertNotEqual(a['exact_dispatch_schedule'],b['exact_dispatch_schedule'])

    def test_missing_or_conflicting_colored_contacts_are_rejected(self):
        with self.assertRaises(ValueError):self.example(groups=[[0,2],[1]])
        with self.assertRaises(ValueError):self.example(groups=[[0,1]])

    def test_geometry_bits_are_part_of_input_signature(self):
        self.assertNotEqual(self.example()['contact_set'],self.example(contacts=[(0,1,101),(2,3,200),(1,2,300)])['contact_set'])

    def test_no_repeat_does_not_report_zero_uncertainty(self):
        result=conditional([{'key':'a','value':1},{'key':'b','value':2}],lambda r:r['key'],'value')
        self.assertIsNone(result['pooled_within_group_cv_pct'])
        self.assertEqual(stats([1,2,3])['range_pct'],100)

if __name__=='__main__':unittest.main()
