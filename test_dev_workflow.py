"""Small CPU-only tests for selection, invalidation and failure propagation."""
from pathlib import Path
import json,sys,tempfile,unittest,os
import subprocess
from unittest.mock import patch
import dev_test as d

class WorkflowTests(unittest.TestCase):
    def test_selection(self):
        self.assertEqual(d.select_cases(['render.hlsl','README.md','zig-out/bin/pool_tests.exe']),[])
        self.assertEqual(d.select_cases(['tests.zig']),['cpu'])
        self.assertEqual(d.select_cases(['physics_main.zig']),['cli','device'])
        self.assertEqual(d.select_cases(['main.zig','spatial_main.zig']),['storage','spatial'])
        self.assertEqual(d.select_cases(['projected_solver.hlsl']),['collisions','energy','overhead','commands'])
        self.assertEqual(d.select_cases(['physics.c']),d.SMOKE+['commands'])

    def test_transitive_invalidation_and_output_tampering(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(d,'ROOT',Path(directory)),patch.object(d,'compiler',return_value=sys.executable),patch.object(d,'sdk',return_value=(Path(sys.executable).parent,Path(sys.executable))):
            root=Path(directory);(root/'unit.c').write_text('#include "middle.h"');(root/'middle.h').write_text('#include "leaf.h"');(root/'leaf.h').write_text('v1');(root/'out').mkdir()
            w=d.Workflow(root/'out');command=[sys.executable,'-c','from pathlib import Path; Path("target").write_text("compiled")']
            w.build('target',['unit.c'],['target'],command);self.assertEqual(len(w.actions),1)
            w.build('target',['unit.c'],['target'],command);self.assertEqual(len(w.actions),1)
            (root/'unrelated.h').write_text('unrelated');w.build('target',['unit.c'],['target'],command);self.assertEqual(len(w.actions),1)
            (root/'leaf.h').write_text('v2');w.build('target',['unit.c'],['target'],command);self.assertEqual(len(w.actions),2)
            (root/'target').write_text('corrupted');w.build('target',['unit.c'],['target'],command);self.assertEqual(len(w.actions),3)
            self.assertEqual(d.dependencies(['unit.c']),['leaf.h','middle.h','unit.c'])

    def test_failure_keeps_log_and_does_not_stamp_success(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(d,'ROOT',Path(directory)),patch.object(d,'compiler',return_value=sys.executable),patch.object(d,'sdk',return_value=(Path(sys.executable).parent,Path(sys.executable))):
            root=Path(directory);(root/'input.c').write_text('');(root/'out').mkdir();w=d.Workflow(root/'out')
            with self.assertRaises(RuntimeError):w.build('bad',['input.c'],['missing'],[sys.executable,'-c','print("diagnostic"); raise SystemExit(7)'])
            self.assertNotIn('bad',w.state);self.assertIn('diagnostic',(root/'out/build-bad.log').read_text())

    def test_generator_preserves_local_edits(self):
        original_run=subprocess.run
        def run(args,**kwargs):
            if args[0]=='git':return subprocess.CompletedProcess(args,1,b'',b'')
            return original_run(args,**kwargs)
        with tempfile.TemporaryDirectory() as directory,patch.object(d,'ROOT',Path(directory)),patch.object(d,'compiler',return_value=sys.executable),patch.object(d,'sdk',return_value=(Path(sys.executable).parent,Path(sys.executable))),patch.object(d,'GENERATORS',{'generate_fake.py':('schema.json',['generated.h'])}),patch.object(d.subprocess,'run',side_effect=run):
            root=Path(directory);(root/'out').mkdir();(root/'schema.json').write_text('{}');(root/'generated.h').write_text('local edit')
            (root/'generate_fake.py').write_text('from pathlib import Path\n(Path(__file__).parent/"generated.h").write_text("expected")')
            w=d.Workflow(root/'out')
            with self.assertRaisesRegex(RuntimeError,'Preserving edited'):w.generate()
            self.assertEqual((root/'generated.h').read_text(),'local edit')

class ShaderCacheTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.enterContext(patch.object(d,'ROOT',self.root))
        self.tool=self.root/'compiler.bin';self.tool.write_bytes(b'tool-v1')
        self.enterContext(patch.object(d,'compiler',return_value=str(self.tool)))
        self.enterContext(patch.object(d,'sdk',return_value=(self.root,self.tool)))
        (self.root/'logs').mkdir();(self.root/'shader.hlsl').write_text('#include "outer.hlsl"')
        (self.root/'outer.hlsl').write_text('#include "inner.hlsl"');(self.root/'inner.hlsl').write_text('v1')
        self.command=[sys.executable,'-c','from pathlib import Path; Path("shader.dxil").write_text("compiled")']
        self.w=d.Workflow(self.root/'logs')

    def build(self,workflow=None,command=None):
        (workflow or self.w).build('shader',['shader.hlsl'],['shader.dxil'],command or self.command)

    def test_newer_stale_dxil_without_provenance_is_compiled(self):
        binary=self.root/'shader.dxil';binary.write_text('stale')
        future=(self.root/'shader.hlsl').stat().st_mtime_ns+10_000_000_000
        os.utime(binary,ns=(future,future));self.build()
        self.assertEqual(len(self.w.actions),1);self.assertEqual(binary.read_text(),'compiled')
        self.assertEqual(self.w.state['shader']['verified_build'],1)

    def test_legacy_timestamp_adoption_record_is_not_provenance(self):
        binary=self.root/'shader.dxil';binary.write_text('stale')
        self.w.state['shader']=dict(key=self.w.key(['shader.hlsl'],self.command),outputs={'shader.dxil':d.digest(binary)})
        self.w.save();fresh=d.Workflow(self.root/'logs');self.build(fresh)
        self.assertEqual(len(fresh.actions),1);self.assertEqual(binary.read_text(),'compiled')

    def test_changed_transitive_hlsl_include_recompiles_despite_same_timestamp(self):
        self.build();header=self.root/'inner.hlsl';st=header.stat()
        header.write_text('v2');os.utime(header,ns=(st.st_atime_ns,st.st_mtime_ns));self.build()
        self.assertEqual(len(self.w.actions),2)

    def test_unchanged_verified_cache_reused_across_invocations(self):
        self.build();fresh=d.Workflow(self.root/'logs');self.build(fresh)
        self.assertEqual(fresh.actions,[]);self.assertEqual(fresh.reused,1)

    def test_corrupted_output_recompiled_despite_same_size_and_timestamp(self):
        self.build();binary=self.root/'shader.dxil';st=binary.stat()
        binary.write_text('corrupt!');os.utime(binary,ns=(st.st_atime_ns,st.st_mtime_ns));self.build()
        self.assertEqual(len(self.w.actions),2);self.assertEqual(binary.read_text(),'compiled')

    def test_changed_tool_bytes_recompile_despite_same_size_and_timestamp(self):
        self.build();st=self.tool.stat();self.tool.write_bytes(b'tool-v2')
        os.utime(self.tool,ns=(st.st_atime_ns,st.st_mtime_ns))
        fresh=d.Workflow(self.root/'logs');self.build(fresh);self.assertEqual(len(fresh.actions),1)

    def test_changed_options_recompile(self):
        self.build();self.build(command=self.command+['--different-options'])
        self.assertEqual(len(self.w.actions),2)

if __name__=='__main__':unittest.main()
