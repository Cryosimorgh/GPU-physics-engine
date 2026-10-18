"""CPU preflight for profiler extraction and retention; executed by one sweep."""
import unittest
from profile_global import linear_fit, shared_bytes, cache_balance, skipped_measurements


class GlobalProfileTests(unittest.TestCase):
    def test_skipped_scans_count_only_forced_rebuilds(self):
        for limit in (1,7,8,9,4095,4096):
            for completed in (0,1,min(7,limit),limit):
                expected=sum(i%8==0 or i==limit for i in range(1,completed+1))
                self.assertEqual(skipped_measurements(completed,limit,True),expected)
                self.assertEqual(skipped_measurements(completed,limit,False),0)
        self.assertEqual(skipped_measurements(4026,4096,True),503)
        with self.assertRaises(ValueError):skipped_measurements(9,8,True)

    def test_iteration_fit_keeps_fixed_and_incremental_cost_separate(self):
        fit = linear_fit([(1,45),(128,3855),(512,15375),(1024,30735)])
        self.assertAlmostEqual(fit['us_per_iteration'],30)
        self.assertAlmostEqual(fit['intercept_us'],15)

    def test_compiler_shared_memory_parser_checks_scalar_and_array_storage(self):
        text = '\n'.join(['@a = addrspace(3) global [7168 x i32] undef',
                          '@b = addrspace(3) global [128 x double] undef',
                          '@c = addrspace(3) global [128 x double] undef',
                          '@d = addrspace(3) global i32 undef',
                          '@e = addrspace(3) global i32 undef'])
        self.assertEqual(shared_bytes(text),30728)
        self.assertLessEqual(shared_bytes(text),32768)
        self.assertEqual(shared_bytes('@v = addrspace(3) global [512 x <3 x double>] undef'),12288)

    def test_unknown_shared_declaration_is_not_silently_accepted(self):
        with self.assertRaises(ValueError):shared_bytes('no shared declarations')

    def test_external_dxil_shared_declarations_have_no_initializer(self):
        self.assertEqual(shared_bytes('@a = external addrspace(3) global [7168 x i32], align 4'),28672)

    def test_cache_selection_requires_all_fixtures_and_performance_balance(self):
        fixtures = [('chain',n) for n in (16,64,256,1024)]+[(topology,n) for topology in ('branching','dense','oblique') for n in (64,256)]
        rows = [dict(topology=topology,n=n,solver=solver,converged=2,samples=2,gpu_p50_us=t)
                for topology,n in fixtures for solver,t in [('Adaptive',100),('CachedP4',80)]]
        self.assertTrue(cache_balance(rows)['retain'])
        rows[1]['converged']=1
        self.assertFalse(cache_balance(rows)['retain'])


if __name__=='__main__':unittest.main()
