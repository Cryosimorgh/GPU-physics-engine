"""Focused portable provenance checks; no GPU or window required."""
import hashlib,json,tempfile,unittest
from pathlib import Path
from build_billiards import verify_build

class BuildProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.bin=self.root/'zig-out/bin';self.bin.mkdir(parents=True)
        for p,data in [(self.root/'source.c',b'source'),(self.root/'shader.dxil',b'shader'),(self.bin/'shader.dxil',b'shader'),(self.bin/'GPUPhysicsBilliards.exe',b'exe')]:p.write_bytes(data)
        sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        self.manifest=dict(verified_build=1,source_sha256={'source.c':sha(self.root/'source.c')},shader_sha256={'shader.dxil':sha(self.root/'shader.dxil')},executable_sha256=sha(self.bin/'GPUPhysicsBilliards.exe'))
        self.path=self.bin/'BILLIARDS_BUILD.json';self.save()
    def save(self):self.path.write_text(json.dumps(self.manifest))
    def test_current_verified_build(self):self.assertEqual(verify_build(self.root),self.manifest)
    def test_unknown_provenance(self):
        self.path.unlink()
        with self.assertRaisesRegex(RuntimeError,'Missing verified'):verify_build(self.root)
    def test_unverified_record(self):
        self.manifest['verified_build']=0;self.save()
        with self.assertRaisesRegex(RuntimeError,'Unknown'):verify_build(self.root)
    def test_source_change(self):
        (self.root/'source.c').write_bytes(b'changed')
        with self.assertRaisesRegex(RuntimeError,'Stale billiards source'):verify_build(self.root)
    def test_corrupted_executable(self):
        (self.bin/'GPUPhysicsBilliards.exe').write_bytes(b'corrupt')
        with self.assertRaisesRegex(RuntimeError,'executable'):verify_build(self.root)
    def test_changed_shader(self):
        (self.root/'shader.dxil').write_bytes(b'changed')
        with self.assertRaisesRegex(RuntimeError,'shader'):verify_build(self.root)
    def test_corrupted_runtime_shader(self):
        (self.bin/'shader.dxil').write_bytes(b'corrupt')
        with self.assertRaisesRegex(RuntimeError,'shader'):verify_build(self.root)
    def test_unknown_extra_shader(self):
        (self.root/'unknown.dxil').write_bytes(b'unknown')
        with self.assertRaisesRegex(RuntimeError,'inventory'):verify_build(self.root)

if __name__=='__main__':unittest.main()
