"""CPU-only orchestration/rollback tests. FakeGPU is NOT a physics qualification."""
import unittest
from dataclasses import asdict
import numpy as np

from sunder_world import (Body, Handle, NativeLease, NativeResult, World,
                          WorldConfig, WorldError, compare_replays, replay_record)


class FakeGPU:
    def __init__(self, cfg):
        self.cfg = cfg
        self.n = cfg.capacity
        self.adapter = "TEST DOUBLE: NO GPU"
        self.accepted = None
        self.pending = None
        self.rejected_once = False
        self.leases = {}
        self.serial = 0
        self.closed = False

    def seed(self, a):
        self.accepted = a.copy()

    def resume_clock(self, tick):
        self.native_tick = tick

    def stage(self, a):
        assert self.pending is None
        self.pending = a.copy()

    def discard(self):
        self.pending = None
        return True

    def tick(self):
        r = NativeResult()
        r.committed = self.n * 256
        r.phases_us[7] = 4.
        if self.rejected_once:
            self.rejected_once = False
            r.error = 16
            r.published = 0
            return True, r
        out = (self.pending if self.pending is not None else self.accepted).copy()
        dynamic = out[19] > 0
        out[:3, dynamic] += out[3:6, dynamic] * np.float32(self.cfg.dt)
        self.accepted = out
        self.pending = None
        r.published = self.n
        return True, r

    def read(self):
        return self.accepted.copy()

    def acquire(self):
        self.serial += 1
        lease = NativeLease(1, self.serial, self.serial, self.serial % 3, self.serial)
        self.leases[self.serial] = lease
        return lease

    def release(self, lease):
        assert lease.serial in self.leases
        del self.leases[lease.serial]

    def close(self):
        assert not self.leases
        self.closed = True


class WorldTests(unittest.TestCase):
    def world(self, capacity=4):
        return World(WorldConfig(capacity=capacity, contact_capacity=32),
                     backend_factory=FakeGPU)

    def test_empty_and_spawn_to_capacity(self):
        with self.world(4) as w:
            with w.acquire() as snap:
                self.assertEqual(len(list(snap.entries())), 0)
            handles = [w.create_body(Body((i * 2., 0., 0.))) for i in range(4)]
            with self.assertRaises(WorldError) as cm:
                w.create_body(Body((20., 0., 0.)))
            self.assertEqual(cm.exception.code, "CAPACITY")
            self.assertEqual(w.step().status, "ACCEPTED")
            with w.acquire() as snap:
                self.assertEqual(len(list(snap.entries())), 4)
                self.assertEqual(snap.body(handles[0])["position"], (0., 0., 0.))

    def test_stale_handles_and_snapshot_immutability(self):
        with self.world() as w:
            old = w.create_body(Body((0., 0., 0.), (1., 0., 0.)))
            self.assertEqual(w.step().status, "ACCEPTED")
            snap = w.acquire()
            self.assertEqual(snap.body(old)["position"][0], 1 / 128)
            self.assertEqual(w.step().status, "ACCEPTED")
            self.assertEqual(snap.body(old)["position"][0], 1 / 128)
            snap.close()
            w.remove_body(old)
            new = w.create_body(Body((5., 0., 0.)))
            self.assertEqual(old.slot, new.slot)
            self.assertNotEqual(old.generation, new.generation)
            self.assertEqual(w.step().status, "ACCEPTED")
            with w.acquire() as new_snap:
                with self.assertRaises(WorldError):
                    new_snap.body(old)
                self.assertEqual(new_snap.body(new)["position"][0], 5.)

    def test_edit_while_accepted_snapshot_is_leased(self):
        with self.world(2) as w:
            h = w.create_body(Body((1., 0., 0.)))
            self.assertEqual(w.step().status, "ACCEPTED")
            held = w.acquire()
            self.assertEqual(held.body(h)["position"], (1., 0., 0.))
            # Cached accepted readback permits candidate edits without
            # reading a native slot that the snapshot consumer has leased.
            w.apply_impulse(h, (1., 0., 0.))
            self.assertEqual(w.step().status, "ACCEPTED")
            self.assertEqual(held.body(h)["position"], (1., 0., 0.))
            held.close()
            with w.acquire() as current:
                self.assertGreater(current.body(h)["position"][0], 1.)

    def test_rejected_structural_tick_keeps_accepted_state(self):
        with self.world() as w:
            h = w.create_body(Body((0., 0., 0.)))
            w.step()
            w._backend.rejected_once = True
            w.remove_body(h)
            provisional = w.create_body(Body((2., 0., 0.)))
            failed = w.step()
            self.assertEqual((failed.status, failed.error_bits), ("REJECTED", 16))
            with w.acquire() as snap:
                self.assertEqual(len(list(snap.entries())), 1)
                self.assertEqual(snap.body(h)["position"], (0., 0., 0.))
                with self.assertRaises(WorldError):
                    snap.body(provisional)
            with self.assertRaises(WorldError):
                w.update_body(provisional, mass=4)
            # A discarded reservation may never reappear as a valid future ID.
            w.remove_body(h)
            fresh = w.create_body(Body((3., 0., 0.)))
            self.assertNotEqual(fresh.generation, provisional.generation)
            self.assertEqual(w.step().status, "ACCEPTED")

    def test_invalid_update_atomic(self):
        with self.world() as w:
            h = w.create_body(Body((2., 0., 0.)))
            w.step()
            old_epoch = w.epoch
            with self.assertRaises(WorldError):
                w.update_body(h, radius=2.)
            self.assertEqual(w.step().status, "ACCEPTED")
            self.assertEqual(w.epoch, old_epoch)
            with w.acquire() as snap:
                self.assertEqual(snap.body(h)["position"][0], 2.)

    def test_forces_impulses_and_async(self):
        with self.world() as w:
            h = w.create_body(Body((1., 0., 0.)))
            w.apply_force(h, (2., 0., 0.))
            w.apply_impulse(h, (1., 0., 0.))
            f = w.step_async()
            self.assertEqual(f.result().status, "ACCEPTED")
            self.assertEqual(w.poll().status, "ACCEPTED")
            with w.acquire() as snap:
                self.assertGreater(snap.body(h)["velocity"][0], 0)
            w.clear_force(h)
            self.assertEqual(w.step().status, "ACCEPTED")

    def test_growth_retains_handles_and_replays(self):
        with self.world(2) as w:
            h = w.create_body(Body((0., 0., 0.), (1., 0., 0.)))
            self.assertEqual(w.step().status, "ACCEPTED")
            w.grow(4)
            h2 = w.create_body(Body((10., 0., 0.)))
            self.assertEqual(w.step().status, "ACCEPTED")
            with w.acquire() as snap:
                self.assertEqual(snap.body(h2)["position"][0], 10)
                self.assertEqual(snap.body(h)["position"][0], 2 / 128)
            record = w.record()
        runs = (replay_record(record, FakeGPU), replay_record(record, FakeGPU))
        self.assertTrue(compare_replays(*runs)["equal"])
        run2 = list(runs[1])
        run2[1][1][0][1]["position"] = (999, 0, 0)
        self.assertFalse(compare_replays(runs[0], run2)["equal"])

    def test_cross_world_handles_are_rejected(self):
        with self.world(2) as first, self.world(2) as second:
            one = first.create_body(Body((0., 0., 0.)))
            two = second.create_body(Body((1., 0., 0.)))
            self.assertEqual((one.slot, one.generation), (two.slot, two.generation))
            self.assertNotEqual(one.world_id, two.world_id)
            with self.assertRaises(WorldError) as context:
                second.remove_body(one)
            self.assertEqual(context.exception.code, "STALE_HANDLE")
            second.step()
            with second.acquire() as snap:
                with self.assertRaises(WorldError):
                    snap.body(one)
                self.assertEqual(snap.body(two)["position"], (1., 0., 0.))

    def test_lease_prevents_destroy(self):
        w = self.world()
        snap = w.acquire()
        with self.assertRaises(WorldError) as cm:
            w.close()
        self.assertEqual(cm.exception.code, "BACKPRESSURE")
        snap.close()
        w.close()

    def test_reject_bad_parameters(self):
        for invalid in ({"capacity": 0}, {"units": "pixels"},
                        {"dt": 0}, {"lower": (0, 0, 0), "upper": (0, 0, 1)}):
            with self.assertRaises(WorldError):
                WorldConfig(**invalid)
        with self.world() as w:
            with self.assertRaises(WorldError):
                w.create_body(Body((0, 0, 0), mass=-2))
            with self.assertRaises(WorldError):
                w.create_body(Body((0, 0, 0), velocity=(float("nan"), 0, 0)))
            self.assertEqual(w.step().status, "ACCEPTED")
            self.assertEqual(w.epoch, 0)


if __name__ == "__main__":
    unittest.main()
