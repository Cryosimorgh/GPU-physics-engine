GPU Physics Bench - Windows x64

Extract the entire ZIP to a writable folder and double-click Launch.bat.
No Zig, Python, RTK, DXC, Visual Studio or repository is needed to RUN.
Keep GPUPhysicsBench.exe and every .dxil file together.
Requires Windows 10/11 x64, a D3D12 GPU with double-precision shader support,
and enough current DXGI memory budget. The supplied release targets baseline
x86-64 CPU instructions. This is an unsigned experimental application.

CONTROLS (also available in the window menus)
Space: pause/resume. N: pause and advance exactly one fixed simulation tick.
R: deterministic scene reset. 1/2/3: 10K/100K/1M physical balls.
P: cycle sparse (9), mixed (10), clustered (11) collision profiles.
Scene menu: choose profile or 1/2/3 frames in flight.
Home: world overview. Z: first table closeup. Wheel: zoom. Left drag: pan.
+/-: tick pacing 0.125x to 4x; the global physical dt stays 1/128 second.
H: dashboard. F9: recording on/off. F10: save/flush results.
View menu: VSync toggle. Escape/window close: drain and exit.
Interactive execution has no 10,000-tick timeout. The checked 32-bit GPU
generation/index limits still require a reset before numeric exhaustion.
Scene changes create a fully admitted replacement while retaining the old
scene, then drain/retire old resources. This temporarily needs BOTH scenes'
memory. Rejection keeps the old scene. A scene switch currently resets the
camera and starts the chosen scene unpaused at normal pacing.

RESULTS
Recording starts enabled. A unique session directory is created in results/
beside the EXE (or under --output-dir). CSV and JSON contain matching frame
and interaction records; JSON is finalized on clean exit. F10 requests a
background flush plus a valid summary.json snapshot while running. hardware.json
records the adapter, driver, initial configuration and memory. The worker uses
a 2048-record bounded queue; dropped records and I/O errors are reported.
Do not unplug the output disk or kill the process if you need finalized JSON.
Recording off stops frame telemetry, but control events are still recorded.
CPU frame time includes actual frame-path CPU blocking; GPU timings are
separate. p50/p95/p99 are GPU-physics durations from bounded completed-frame
windows, not physical display latency. Summary distributions cover at most
the latest 4096 recorded frames. Dashboard windows target 1s and 10s, capped
by that same bounded history. Expensive cleanup/output happens on exit.
Do not run concurrent GPU benchmarks for controlled measurements.

SCENE / PHYSICS LIMITS
This is 2D disk physics rendered with shaded sphere impostors. Each independent
closed table contains 16 balls. 1M balls means many independent tables, NOT one
million-body connected island. Radius, deterministic seed, forces and fixed dt
are inherited unchanged from G4. All selected balls are physically simulated.
Overview renders at most 50,000 visual instances; closeup selects all instances
with screen clipping. The HUD shows actual physical count, submitted rendered
instances and their ratio. Rendered instances are not necessarily visible pixels.
Original validation, rollback and ordered state publication remain in place.
Strict immutable source snapshots are not newly guaranteed by this application;
the default direct-queue path serializes state writes and rendering. Debug-layer
and GPU-validation runs are separate from release benchmarking.
No 60 Hz promise is made for 1M balls or clustered workloads.

DISPLAY
DISPLAY FPS: UNVERIFIED is intentional until valid local Windows display events
are collected. Render FPS and Present calls/s are NOT displayed FPS. This does
not prevent using the app at a physical local display. G4 GPU-02 remains open;
G5 is not started. OS presentation estimates are not true photon latency.

Optional local PresentMon workflow:
Sign in on the actual physical console. Use a supported PresentMon console
release, with tracing permissions (Performance Log Users membership followed
by sign-out/in, or an appropriately elevated capture). Consult that installed
version's --help. Current documented options include --process_name
GPUPhysicsBench.exe --qpc_time --write_display_metadata --output_file capture.csv
--timed 30 --terminate_after_timed. Retain dropped frames and display tracking;
do not pass --exclude_dropped or --no_track_display. Repeat captures and retain
raw ETL with a supported Windows tracing profile for causal analysis. Application
CSV includes frame/generation/epoch, simulation-attempt-start and Present QPCs.
Those values alone do NOT prove a unique image-to-display mapping or GPU-02.
See https://github.com/GameTechDev/PresentMon/blob/main/README-ConsoleApplication.md

AUTOMATED / SOURCE BUILD
GPUPhysicsBench.exe --n 100000 --profile 10 --depth 2 --steps 200 --automated
The explicit --steps bound is for automation only; omitted/0 runs until exit.
--debug enables dedicated D3D12 debug-layer/GBV testing, not normal benchmarking.
--output-dir "D:\My Results" selects an existing or creatable output base.
Source developers need Zig 0.15.2, Python 3 and a Windows SDK including DXC.
python build_physics.py
python build_viewer.py
python package_windows.py --no-build
The Python build scripts detect SDK headers and DXC; RTK is not required.
Source: https://github.com/Cryosimorgh/GPU-physics-engine
