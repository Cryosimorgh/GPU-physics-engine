"""CPU-only preflight tests for the bounded sweep, no GPU process launches."""
from pathlib import Path
import tempfile
import struct
import unittest
from sweep_g5 import fixture, bodies, percentile, summarize, read_solver_trace, OMEGA_MAX, performance_balance


class SweepTests(unittest.TestCase):
    def trace_fixture(self, directory, policy=2, iterations=366, restart=None, contraction=.5):
        path = Path(directory)/'trace.json'
        count, capacity = 63, 512
        meta = bytearray(256)
        struct.pack_into('<I', meta, 8, count)
        arena = bytearray(80*capacity)
        def record(slot, it, event=0):
            struct.pack_into('<4I6d3If', arena, 80*(count+slot),
                             0x47355452, 1, 0, it, .001, .001, .002, contraction,
                             1., OMEGA_MAX, event, policy, 0, .9)
        for slot in range((iterations-1)//64):
            record(slot, (slot+1)*64)
        record(64, iterations, 16)
        if restart is True or (restart is None and policy == 3 and iterations > 512):
            record(65, 512, 8)
        Path(str(path)+'-meta-1.bin').write_bytes(meta)
        Path(str(path)+'-contacts-1.bin').write_bytes(arena)
        payload = dict(islands=1, solver_dispatches=1, total_iterations=iterations,
                       status='PASS', contact_capacity=capacity)
        return path, payload

    def test_improving_windows_preserve_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path, payload = self.trace_fixture(directory, 4, 1195, restart=False, contraction=.5)
            self.assertFalse(any(r['event'] == 8 for r in read_solver_trace(payload, path)))

    def test_poor_windows_require_bounded_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path, payload = self.trace_fixture(directory, 4, 4036, restart=True, contraction=.973)
            self.assertEqual(sum(r['event'] == 8 for r in read_solver_trace(payload, path)), 1)
            path, payload = self.trace_fixture(directory, 4, 4036, restart=False, contraction=.973)
            with self.assertRaisesRegex(ValueError, 'budgeted restart'):
                read_solver_trace(payload, path)

    def test_unnecessary_restart_is_rejected_by_trace_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            path, payload = self.trace_fixture(directory, 4, 1195, restart=True, contraction=.5)
            with self.assertRaisesRegex(ValueError, 'unexpected restart'):
                read_solver_trace(payload, path)

    def test_balance_rejects_slowdowns_and_failed_cases(self):
        def rows(candidate_time, converged=2):
            return [dict(topology='dense', n=64, solver=solver, converged=count,
                         samples=2, gpu_p50_us=gpu, cpu_p50_us=10)
                    for solver, gpu, count in [('Policy3', 100, 2), ('Adaptive', candidate_time, converged)]]
        self.assertTrue(performance_balance(rows(80))['retain'])
        self.assertFalse(performance_balance(rows(120))['retain'])
        self.assertFalse(performance_balance(rows(10, 1))['retain'])

    def test_complete_residual_history_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path, payload = self.trace_fixture(directory, 3, 4024)
            records = read_solver_trace(payload, path)
            self.assertEqual(sum(r['event'] == 8 for r in records), 1)
            self.assertEqual(records[-1]['iteration'], 4024)

    def test_gpu_float32_relaxation_bound_is_not_decimal_rounded(self):
        self.assertGreater(OMEGA_MAX, 1.995)
        with tempfile.TemporaryDirectory() as directory:
            path, payload = self.trace_fixture(directory)
            self.assertEqual(read_solver_trace(payload, path)[-1]['omega_after'], OMEGA_MAX)

    def test_restart_accepts_exact_double_literal_encoding(self):
        with tempfile.TemporaryDirectory() as directory:
            path, payload = self.trace_fixture(directory, 3, 4024)
            arena_path = Path(str(path)+'-contacts-1.bin')
            arena = bytearray(arena_path.read_bytes())
            struct.pack_into('<d', arena, 80*(63+65)+56, 1.995)
            arena_path.write_bytes(arena)
            restart = next(r for r in read_solver_trace(payload, path) if r['event'] == 8)
            self.assertEqual(restart['omega_after'], 1.995)

    def test_missing_residual_window_is_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path, payload = self.trace_fixture(directory)
            arena_path = Path(str(path)+'-contacts-1.bin')
            data = bytearray(arena_path.read_bytes())
            struct.pack_into('<I', data, 80*(63+2), 0)
            arena_path.write_bytes(data)
            with self.assertRaisesRegex(ValueError, 'missing residual windows'):
                read_solver_trace(payload, path)

    def test_trace_reserve_is_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            path, payload = self.trace_fixture(directory)
            payload['contact_capacity'] = 128
            with self.assertRaisesRegex(ValueError, 'diagnostic arena reserve'):
                read_solver_trace(payload, path)

    def test_all_fixtures_are_connected_nonoverlapping_and_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            for topology in ('chain', 'branching', 'dense', 'oblique'):
                for n in ([16, 64, 256, 1024] if topology == 'chain' else [64, 256]):
                    path = Path(directory)/'fixture.bin'
                    description, pairs = fixture(topology, n, path)
                    data = path.read_bytes()
                    fixture(topology, n, path)
                    self.assertEqual(data, path.read_bytes())
                    self.assertEqual(len(bodies(data)), n)
                    self.assertEqual(description['initial_overlaps'], 0)
                    expected = n-1 if topology in ('chain', 'branching') else 2*n-2*int(n**.5)
                    self.assertEqual(len(pairs), expected)
                    self.assertEqual([b[15] for b in bodies(data)], list(range(n)))

    def test_new_topologies_reject_unsupported_sizes(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                fixture('dense', 1024, Path(directory)/'fixture.bin')

    def test_rejection_timeout_error_are_separate(self):
        runs = [dict(topology='chain', n=64, solver=solver, status=status)
                for solver in ('PGS', 'SOR1.995')
                for status in ('CONVERGED', 'REJECTED', 'TIMEOUT', 'ERROR', 'ADMISSION_REJECTED', 'BLOCKED_AFTER_TIMEOUT')]
        summary, regressions = summarize(runs)
        for row in summary:
            for key in ('converged', 'rejected', 'timeouts', 'errors', 'admission_rejected', 'blocked'):
                self.assertEqual(row[key], 1)
        self.assertEqual(regressions[0]['kind'], 'CORRECTNESS_OR_EXECUTION')

    def test_short_sample_p95_is_maximum(self):
        self.assertEqual(percentile([200, 100], .95), 200)
        self.assertIsNone(percentile([], .95))

    def test_unchanged_control_and_rejected_attempt_are_not_timing_regressions(self):
        def run(n, solver, status, gpu):
            return dict(topology='chain', n=n, solver=solver, status=status,
                        gpu_stage_us={'total':gpu}, cpu_submit_us=10)
        runs = [run(16, 'PGS', 'CONVERGED', 10), run(16, 'SOR1.995', 'CONVERGED', 11),
                run(64, 'PGS', 'REJECTED', 10), run(64, 'SOR1.995', 'CONVERGED', 11)]
        self.assertEqual(summarize(runs)[1], [])

    def test_matched_accepted_slowdown_is_reported(self):
        runs = [dict(topology='branching', n=64, solver=solver, status='CONVERGED',
                     gpu_stage_us={'total':gpu}, cpu_submit_us=10)
                for solver, gpu in [('PGS', 10), ('SOR1.995', 50)]]
        self.assertEqual(summarize(runs)[1][0]['kind'], 'OBSERVED_PERFORMANCE')

    def test_three_way_comparison_detects_adaptive_failure(self):
        runs = [dict(topology='chain', n=1024, solver=solver, status=status)
                for solver, status in [('PGS', 'REJECTED'), ('SOR1.995', 'CONVERGED'), ('Adaptive', 'ERROR')]]
        summary, regressions = summarize(runs)
        self.assertEqual([r['solver'] for r in summary], ['PGS', 'SOR1.995', 'Adaptive'])
        self.assertEqual(regressions[0]['configuration']['solver'], 'Adaptive')

    def test_fixed_sor_convergence_is_required_even_when_pgs_rejects(self):
        runs = [dict(topology='chain', n=256, solver=solver, status=status)
                for solver, status in [('PGS', 'REJECTED'), ('SOR1.995', 'CONVERGED'), ('Adaptive', 'REJECTED')]]
        regression = summarize(runs)[1][0]
        self.assertEqual(regression['kind'], 'CONVERGENCE')
        self.assertEqual(regression['solver'], 'Adaptive')
        self.assertEqual(regression['reference'], 'SOR1.995')


if __name__ == '__main__':
    unittest.main()
