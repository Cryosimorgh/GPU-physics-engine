"""Static executable/shader provenance inspection. No GPU execution."""
import hashlib
import json
from pathlib import Path
import struct

from dev_test import ROOT, compiler, sdk

def sha(data):
    return hashlib.sha256(data).hexdigest()

def pe(path):
    data = path.read_bytes()
    at = struct.unpack_from('<I', data, 60)[0]
    count, timestamp = struct.unpack_from('<HI', data, at+6)
    optional = struct.unpack_from('<H', data, at+20)[0]
    sections = {}
    for i in range(count):
        offset = at+24+optional+40*i
        name = data[offset:offset+8].rstrip(b'\0').decode()
        size, raw = struct.unpack_from('<II', data, offset+16)
        sections[name] = dict(sha256=sha(data[raw:raw+size]), bytes=size)
    return dict(sha256=sha(data), bytes=len(data), timestamp=timestamp, sections=sections)

if __name__ == '__main__':
    out = ROOT/'dev-test-results/solver-cost-inspection'
    a = pe(ROOT/'zig-out/bin/physics.exe')
    b = pe(out/'fresh-control/physics.exe')
    result = dict(recovery_executable=a, fresh_executable=b,
        changed_sections=[n for n in a['sections'] if a['sections'][n]!=b['sections'].get(n)],
        tools={str(p):sha(Path(p).read_bytes()) for p in [compiler(),sdk()[1],sdk()[1].parent/'dxcompiler.dll',sdk()[1].parent/'dxil.dll']},
        archived_provenance_limit='Archive has no original physics.exe, compiler/linker invocation, Zig/linker/library hashes or build-cache manifest. Historical hash cause cannot be proven from that archive.',
        link_flags='Current Zig 0.15.2 invokes lld-link -DEBUG -PDBALTPATH:physics.pdb -BREPRO. Full command and libraries are in fresh-control-link.log.',
        baseline_gpu_sweep_repeated=False)
    (out/'executable-provenance.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k not in ['recovery_executable','fresh_executable','tools']},indent=2))
