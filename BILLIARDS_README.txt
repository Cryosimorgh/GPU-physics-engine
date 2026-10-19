GPU Physics Billiards - Windows x64

Extract everything into a writable folder. Run Launch.bat or
GPUPhysicsBilliards.exe. Windows 10/11 x64, D3D12 shader double precision and
sufficient current DXGI memory budget are required. No development tools are
required to play. Dear ImGui is statically linked; its MIT license is included.
The CPU target is baseline x86-64. Shaders must remain beside the executable.

PLAYABLE BILLIARDS (DEFAULT)
One 2.54 m x 1.27 m cushion table, exactly 16 balls of radius 0.028575 m and
mass 0.17 kg. One white cue ball; 15 numbered object balls. Cue starts on the
head spot. The triangular eight-ball pattern has its apex on the foot spot,
8 in the center and a solid/stripe at opposite rear corners. A 0.5 mm rack
clearance prevents invalid initial penetration. Every ball starts at rest.
Nothing moves until an explicit cue strike. There is no external driving force.

Left-click the white cue ball, drag to aim, release to strike. The arrow shows
direction and delta velocity in m/s. Adjust power with the strength slider.
Each command is capped at delta-v 1.5 m/s (maximum impulse 0.255 N s).
Shots while any ball is moving/spinning are blocked on the GPU. Settings offers
an explicit sandbox override. Colored balls cannot be directly struck.

Right-drag pans; wheel zooms; F focuses the selected cue ball; Home fits table.
Space pauses/resumes; Period advances one global tick; R resets the rack.
Escape deselects then closes. H hides UI. Panels collapse with title arrows.
The fixed global timestep is 1/128 s; pacing never changes physics dt.
In the billiards mode, 1/2/3 switches explicitly to synthetic stress populations.

PHYSICS QUALIFICATION
New approaching impacts use pre-impact normal restitution, 0.93 between balls
and 0.8 at cushions. Persistent resting contacts do not repeatedly bounce.
Tangential Coulomb impulses use material coefficients 0.02 (balls) / 0.15 (rails).
Cloth sliding friction exchanges linear velocity and horizontal rolling state
using solid-sphere inertia 2/5 m R^2. Rolling resistance then removes motion at
constant bounded deceleration. Yaw spin has passive Coulomb-style resistance.
The coefficients are chosen model parameters, not measurements of a specific
commercial table. See BILLIARDS_PHYSICS_CORRECTION.md for equations and tests.

This is a qualified planar approximation. It has no ball lift, jump/masse cue
control, detailed compliant cushion deformation, pocket sinking, scoring or
eight-ball rules. Horizontal rolling state and planar yaw are represented, but
this is not a full 3D rigid-body engine. Ball positions are published only after
validation. A separate bounded, energy-neutral position stabilization pass fixes
floating-point drift; it never substitutes for restitution or injects velocity.
Severe penetration, nonconvergence or capacity errors reject publication.

The playable entity set stays fixed at 16. Reset replaces the drained scene
owner; incremental ball creation/deletion is not a gameplay operation. Existing
G1/G4 structural lifecycle remains separately tested on scientific fixtures.

SCIENTIFIC STRESS TESTS
Scene exposes the preserved sparse/mixed/clustered 16-ball-table fixtures and
the former continuous synthetic arena. Population offers 10K/100K/1M, plus the
arena previews. These retain their old deterministic seeds, drives and contact
model. They are synthetic workloads, not realistic games of pool. Gameplay
results and scientific timing comparisons must remain separate. No universal
60 Hz or million-body connected-island performance claim is made.

RECORDING
F9 starts/stops recording; F10 saves/flushes; F12 captures the actual backbuffer.
Unique results/session-* directories contain CSV, JSON, hardware/scene metadata
and timing summaries. Shot, pause, camera, reset, ball-impact and rail-impact
events are recorded. JSON finalizes on clean exit. I/O uses a bounded background
queue and reports dropped samples. No normal physics stage needs a CPU readback.
Full physics stage timings include the actual existing pipeline and the new
pool-only stabilization. Live FPS is engine render rate, not physical display FPS.

gameplay.mp4 and screenshots are actual executable captures. The video's
15 fps encoding cadence is not a display measurement; capture timestamps are
included with examples. The footage includes a break, a later rail shot and
stopping/reset. Interactive/capture timings are not controlled benchmarks.

SAFETY / LIMITS
The existing checked admission, staged GPU calculation, validation, rollback
and fence retirement remain. Playable mode reserves 256 pairs / 256 contacts;
16 objects have at most 120 unordered body pairs and 64 body/rail constraints.
This bound does not apply to large stress workloads. No contact is truncated.
The existing bounded large-island fallback remains; no G5 work was added.
Strict immutable source snapshots are not newly claimed beyond the qualified
ordered G4 publication model. Formal GPU-02 / physical displayed FPS remains
UNVERIFIED. No G4 or G5 approval is implied by the playable app.

BUILD / AUTOMATION
Python 3, Zig 0.15.2 and Windows SDK with DXC are needed to build, not to play.
python build_billiards.py --tests
python test_billiards_physics.py
python test_billiards_gameplay.py
python package_billiards.py
python test_billiards_package.py
Pillow and ffmpeg are used only for development gameplay-capture automation.
GPUPhysicsBilliards.exe --steps 32 --automated --quiet bounds an actual GPU run.
--debug enables dedicated D3D12 debug/GBV testing. --output-dir chooses a
writable results base. Omit --steps for continuous interactive play.

Source branch: billiards-physics-correction
https://github.com/Cryosimorgh/GPU-physics-engine
