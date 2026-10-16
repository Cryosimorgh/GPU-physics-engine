# GPU Physics Bench

Portable Windows x64 application built on the standalone G4 Zig/C/HLSL/D3D12 implementation.

Download [GPUPhysicsBench-Windows-x64.zip](dist/GPUPhysicsBench-Windows-x64.zip), extract everything into a writable folder, and run **Launch.bat**. Running the application requires no development tools. The release targets baseline x86-64 CPU instructions; it requires Windows 10/11, D3D12 shader double precision, and sufficient current DXGI memory budget.

The window menus expose 10K/100K/1M populations, sparse/mixed/clustered profiles, pause, single step, deterministic reset, pacing, VSync, camera controls, recording, and 1/2/3 frames in flight. Space pauses; N steps; R resets; 1/2/3 choose population; P cycles profiles; Home shows overview; Z zooms to a table; wheel zooms; drag pans; H toggles the dashboard; F9 records; F10 saves. Interactive runs continue until exit. `--steps` explicitly bounds automated runs.

Results go into uniquely named folders under `results/` beside the executable. CSV and JSON record matching frames and interaction events; a background worker performs benchmark I/O through a bounded queue and reports dropped samples. JSON finalizes on clean exit; F10 also writes a live `summary.json`. See [complete usage and limitations](PORTABLE_README.txt).

These are **independent 16-ball tables**, with fixed global `dt=1/128`. Increasing population adds tables. Overview samples at most 50,000 rendered instances while all selected balls remain simulated; the dashboard reports both counts. This does not demonstrate a million-body connected island or guarantee 60 Hz at 1M. Strict immutable source snapshots are not newly claimed; the existing G4 ordered state publication/rollback model remains in use.

**Displayed FPS remains UNVERIFIED.** Render FPS, simulation ticks/s, and Present calls/s are distinct engine metrics. Optional physical-console PresentMon instructions are included. G4 GPU-02 remains open; this application does not approve G4 or start G5.

## Build from source

Developers need Zig 0.15.2, Python 3, and a Windows SDK containing D3D12 headers, UCRT, and DXC. The build scripts discover the installed SDK; RTK is not required.

```powershell
python build_physics.py
python build_viewer.py
python package_windows.py --no-build
```

The application executable is `zig-out/bin/GPUPhysicsBench.exe`. Shaders are resolved beside the executable, independently of the caller's working directory. `build_viewer.py --reference-cli` rebuilds the bounded original G4 verification CLI; `--lifecycle` builds the evolving generation/compaction regression. Original physics/shader/scene semantics are preserved from the initial G4 snapshot.

## Test

```powershell
python build_viewer.py --host-only --reference-cli
python build_viewer.py --host-only --lifecycle
zig test tests.zig -O ReleaseSafe -target x86_64-windows-gnu -mcpu=baseline
python test_portable.py
```

The serial device suite tests all populations/profiles with the existing independent physics oracle, GBV at each frame depth, native allocation/fence regressions, evolving generational lifecycle, real Win32 controls, deterministic reset hashes, active-state preservation on failed admission, CSV/JSON agreement, and an unbounded interactive run beyond 10,000 actual ticks. It extracts the ZIP separately into a path with spaces, launches from a foreign working directory, and removes development tools from the child process's PATH. Results are retained under ignored `local-test-results/`.

The prior validated G4 repository and frozen evidence remain preserved locally. The GitHub engine repository excludes those historical raw reports/traces.
