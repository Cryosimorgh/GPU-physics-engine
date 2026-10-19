"""Independent exact-arithmetic and scope checks; no GPU simulation replica."""
from pathlib import Path
from decimal import Decimal
import struct,unittest
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
    def test_pool_only_source_contract(self):
        # These are self-contained structural checks. Archived before/after
        # shader equality and GPU results are checked by the handoff verifier.
        hlsl=(R/'physics.hlsl').read_text()
        rail=hlsl[hlsl.index('double poolRailGap('):hlsl.index('float force(')]
        for expression in ('double x=double(val(a,0)),y=double(val(a,1)),r=double(val(a,8))',
                           'x-double(bounds.x)-r','double(bounds.z)-r-x',
                           'y-double(bounds.y)-r','double(bounds.w)-r-y'):
            self.assertIn(expression,rail)
        append=hlsl[hlsl.index('void append('):hlsl.index(']void ph_round(')]
        self.assertIn('double poolGap=wall?poolRailGap(a,w):double(gap)',append)
        self.assertIn('target=float(poolTarget(a,b,double(nx),double(ny),poolGap))',append)
        walls=hlsl[hlsl.index(']void ph_walls('):hlsl.index(']void ph_admit_round(')]
        self.assertIn('admissionGap=poolRailGap(i,w)',walls)
        self.assertIn('phase()!=8&&admissionGap<=0',walls)
        geometry=hlsl[hlsl.index('void geometry('):hlsl.index('void checkContact(')]
        self.assertIn('gap=w==0?x-double(bounds.x)-ra:',geometry)
        self.assertIn('target=poolTarget(a,b,nx,ny,gap)',geometry)
if __name__=='__main__':unittest.main()
