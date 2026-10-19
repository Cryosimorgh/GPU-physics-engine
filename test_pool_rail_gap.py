"""Independent exact-arithmetic and scope checks; no GPU simulation replica."""
from pathlib import Path
from decimal import Decimal
import json,struct,unittest
R=Path(__file__).resolve().parent
def f32(x):return struct.unpack('<f',struct.pack('<f',x))[0]
def exact(x):return Decimal.from_float(x)
class RailGap(unittest.TestCase):
    def test_original_witness(self):
        width=f32(2.54);r=f32(.028575);x=f32(2.5110435485839844)
        before=f32(f32(width-r)-x);after=width-r-x
        self.assertEqual(after,float(exact(width)-exact(r)-exact(x)))
        self.assertEqual(before,.0003814697265625)
        self.assertEqual(after,.00038141384720802307)
        self.assertEqual((before-after)*128,7.152557373046875e-6)
        self.assertEqual(f32(-after*128),-0.04882097244262695)
        self.assertEqual(f32(-after*128)+after*128,0)
    def test_all_rails_cancellation(self):
        for extent in [f32(2.54),f32(1.27)]:
            for r in [f32(.028575),.03125]:
                for high in [False,True]:
                    center=f32(extent-r) if high else r
                    bits=struct.unpack('<I',struct.pack('<f',center))[0]
                    for offset in [-2,-1,0,1,2]:
                        x=struct.unpack('<f',struct.pack('<I',bits+offset))[0]
                        got=extent-r-x if high else x-0.-r
                        oracle=exact(extent)-exact(r)-exact(x) if high else exact(x)-exact(r)
                        self.assertEqual(got,float(oracle))
                        self.assertEqual((got>0)-(got<0),(oracle>0)-(oracle<0))
    def test_independent_validator_and_solver_unchanged(self):
        before=(R/'evidence/g6-p8b/baseline-physics.hlsl').read_text()
        after=(R/'physics.hlsl').read_text()
        # All functions following append/admission, including coloring, solver,
        # geometry(), KKT checks, publication and rollback remain byte-identical.
        marker='[numthreads(256,1,1)]void ph_admit_round'
        self.assertEqual(before[before.index(marker):],after[after.index(marker):])
        start=' if(!wall){';end='\n  else {'
        # Isolate append's ball-ball branch, including its existing conversions.
        def ball(t):
            t=t[t.index('void append('):];return t[t.index('if(!wall)'):t.index('else {float4 bounds')]
        self.assertEqual(ball(before),ball(after))
    def test_recorded_baseline(self):
        p=json.loads((R/'evidence/g6-p8b/control-provenance.json').read_text())
        self.assertEqual((p['exit'],p['failure_tick'],p['error_flags']),(1,4072,32))
        self.assertTrue(p['rollback_verified'])
if __name__=='__main__':unittest.main()
