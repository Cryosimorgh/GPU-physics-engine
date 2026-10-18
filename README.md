# Standalone GPU physics engine

**Technical architecture and living gate record:** [docs/ENGINE_ARCHITECTURE.md](docs/ENGINE_ARCHITECTURE.md). Update it at each G0–G6 breakpoint or material architecture decision. Historical and local experimental results are labeled separately from released code.


Zig / C / HLSL / Direct3D 12 standalone experiment. Engine snapshot from local G4 commit `ce81b2c`; compiled engine bytes match the measured implementation at `e324fd3`. Reports, benchmark results, raw traces, and historical reference repositories are intentionally excluded from this repository.

## Run

Requires Windows x64, a compatible D3D12 GPU with shader double precision, and sufficient current DXGI memory budget. Run from the repository root so the executable can find the included DXIL shaders:

```powershell
.\zig-out\bin\viewer.exe --n 10000 --profile 10 --interactive --out interactive-10k.json
```

Home: overview; Z: close view; mouse wheel: zoom; left drag: pan; Space: pause; Escape: exit. Profiles: 9 sparse, 10 mixed, 11 clustered. `--depth 1|2|3`, `--vsync 0|1`. Interactive runs are bounded to 10,000 ticks.

This is 2D disk physics drawn as sphere impostors. Every 16 balls occupy an independent closed table; increasing population increases the number of tables. It does not demonstrate a million-body connected collision island. Overview rendering samples at most 50,000 instances while all entities remain simulated. The one-million mixed workload was not qualified for 60 Hz; physical displayed FPS and display latency remain unverified.

## Build

Requires Zig 0.15.2, Python 3, RTK, and Windows SDK 10.0.26100.0. The existing scripts use that SDK installation path and compile for the local CPU.

```powershell
New-Item -ItemType Directory -Force zig-out/bin | Out-Null
rtk proxy python build_physics.py
rtk proxy python build_viewer.py
rtk proxy python build_viewer.py --host-only --lifecycle
rtk proxy zig build test
```

The shaders, generated layout contracts, storage, spatial index, integrated solver, renderer, scene checker, native test code, and existing compiled executables are included. Build scripts generate layout headers from the checked-in schemas. Historical gate evidence remains in the preserved local standalone experiment and is not uploaded here.
