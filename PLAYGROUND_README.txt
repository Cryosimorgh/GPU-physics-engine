GPU Physics Playground - Windows x64

Extract the entire ZIP into a writable folder. Run Launch.bat.
No development tools, repository, Codex, or remote desktop are needed to run.
Windows 10/11 x64, D3D12 double-precision shader support and enough current DXGI
memory budget are required. The release uses baseline x86-64 CPU instructions.
Dear ImGui is statically linked; D3D12, DXGI, D3DCompiler_47 and UCRT are Windows
system components. Segoe UI is used if present, otherwise the embedded UI font.

PLAY
The default is a continuously shared arena with 100 moving physical balls.
This is real 2D disk physics rendered as shaded spheres, not 3D rigid bodies.
Left-click a ball to select. Drag to aim an impulse; release to queue it for
the next global physics tick. The arrow and numeric dv show the shot strength.
Right-drag pans; wheel zooms; F focuses the selected ball; Home shows the arena.
Space pauses/resumes. Period advances one global tick while paused. R resets
the same seed. Escape deselects, then closes. H toggles a clean view.
Adjust impulse strength in the right panel. Each shot is capped at dv 1.5;
mass is 1, so impulse and dv have the same numeric value. One pending shot is
allowed. Additional shots before it is submitted are explicitly logged as
rejected; selecting another ball does not retarget an already queued shot.
Paused shots wait for Period or Resume. Reset cancels pending scene input.

TOP BAR
Scene: Playground, or separately preserved Scientific Benchmarks.
Population: 100 / 1,000 previews, 10K / 100K / 1M real physical balls.
Physics: pause, step, reset and pacing. Pacing never changes dt = 1/128.
Recording: start/stop (F9), flush/save (F10), actual backbuffer screenshot (F12).
Settings: focus, overview, clean view, VSync and 1/2/3 frames in flight.
The statistics and graph panels collapse using their title arrows. The memory
section expands for budget/usage/peak and failure counts. Scroll a panel if
the window is too small. Larger populations initially show a close region;
Home fits the full arena. Zoom and focus allow inspection of actual collisions.

SCENE CONTRACT
Playground v1, seed 18228. Radius 1/16, mass 1, inverse inertia 512.
Rows/columns scale with N. Initial pitch is 3/16; paired horizontal separation
is 17/128, strictly greater than diameter 1/8. There are no initial overlaps.
All bodies share one arena: width = ceil(sqrt(N))*3/16 + 1/2;
height = ceil(N/ceil(sqrt(N)))*3/16 + 1/2. Occupancy tends to 34.9% at large N.
Initial speed is below 0.492 units/s. No artificial animation or perpetual
driving force is used. Body contacts are inelastic and frictionless; wall
restitution is 0.75. Motion can dissipate: strike balls again to add energy.
The original contact projection, discovery, solve, validate and publication
passes remain in use. No independent per-body tick rates or new solver exist.
Impulses are versioned, bounded GPU commands, applied to provisional state in
prepare. Stale handle/generation/epoch/tick commands reject without publication.

SCIENTIFIC BENCHMARKS
The sparse/mixed/clustered presets remain the original independent 16-ball
table scenes, including their seed, constants, geometry and forces. They are
not the new arena. They require at least the 10K preset. Their initializer and
solver source are preserved. Interactive results are not controlled benchmark
results; do not compare scene families as physically equivalent workloads.

COUNTS AND LIMITS
All selected N bodies are genuinely simulated; no visual duplication is used.
Overview may sample at most 50K submitted visual instances. Close views submit
all instances and the GPU clips off-screen geometry. The UI separates simulated
balls from submitted rendered instances and the visual fraction. Submitted
instances are not the number of visible pixels or unoccluded balls.
The original bounded large-island fallback and nonconvergence reporting remain.
Playground reserves 12*N contacts and 16*N candidate pairs; these are checked
reservations, not a universal bound on possible contact topology. Oversized or
nonconvergent workloads fail explicitly with the last published state retained.
Scene changes admit the replacement while retaining the old scene, then drain
and retire old resources. This needs old + new memory temporarily. Allocation
rejection leaves the active scene intact. No 60 Hz promise is made at 1M.
Strict immutable snapshot isolation is not newly claimed; the existing G4
ordered, validated GPU publication model remains in place. G5 is not started.

RECORDING
Results are written to unique results/session-* folders beside the EXE.
CSV and JSON include frame IDs, scene epoch, tick generation, QPC timestamps,
configuration, real workload counts, timings and interaction/impulse events.
Committed impulse events retain the actual handle, generation, serial and dv.
hardware.json and scene-*.json record hardware and deterministic initial hashes.
F10 requests an asynchronous flush and summary.json. Raw samples.json finalizes
on clean exit; samples.csv streams while running. Do not kill the process if
you need finalized JSON. Recording off suppresses frame records, not events.
The writer uses a bounded 2048-record queue and reports dropped telemetry/I/O
failures. Rolling statistics use bounded 1s/10s windows capped at 4096 frames.
The graph retains 240 observations. Font upload/bootstrap is outside the tick
loop; normal statistics add no synchronous GPU readback or wait beyond existing
G4 frame completion. Picking reuses asynchronous completed-frame diagnostics.
GUI resource admission reserves 16 MiB, bounds UI vertices/indices, and charges
live font/vertex/index resources using actual D3D12 allocation sizes. DXGI peak
is observed usage, not a claim of complete physical-memory transaction tracing.

DISPLAY
Simulation ticks/s, rendered frames/s and Present calls/s are distinct from
physical display FPS. Display FPS remains UNVERIFIED without valid local OS
display events. This never blocks playing or recording. Optional PresentMon
captures should run on the physical console with authorized tracing permission;
keep QPC and display metadata, dropped-frame records and raw ETL. Engine QPCs
alone do not close GPU-02. OS presentation estimates are not photon latency.
Frozen G4 is not automatically approved by this application.

AUTOMATION / BUILD
GPUPhysicsPlayground.exe --n 1000000 --steps 32 --automated --quiet
Omit --steps (or use 0) to run until exit. --profile 12 is Playground;
--profile 9/10/11 selects Scientific Benchmarks at 10K or greater.
--debug enables dedicated D3D12 debug/GBV correctness testing, not benchmarking.
--output-dir "D:\My Results" chooses a writable results base.
Source build: Python 3, Zig 0.15.2, Windows SDK with D3D12 headers and DXC.
python build_playground.py --tests
python package_playground.py
No RTK or Visual Studio is required by the build scripts. SDK paths are detected.

ImGui v1.90.9 (MIT): LICENSE-ImGui.txt. Repository and exact source branch:
https://github.com/Cryosimorgh/GPU-physics-engine/tree/g4-playable-playground
