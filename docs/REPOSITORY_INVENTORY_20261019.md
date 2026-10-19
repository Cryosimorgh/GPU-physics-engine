# Repository inventory — 2026-10-19

Repository: https://github.com/Cryosimorgh/GPU-physics-engine
Default branch: `main`
Snapshot: after integration PR [#1](https://github.com/Cryosimorgh/GPU-physics-engine/pull/1), merge commit `fc6300c3d83e8cdf2201b0a2d475b62eb87d34b9`.
Method: GitHub API recursive tree and branch comparison, source/config inspection, previous archived Windows handoff evidence. **Not** a local Windows rebuild, GPU execution, binary vulnerability audit, or static analysis pass.

## Files and stack

The recursive source tree has **359 entries: 338 blobs/files and 21 directories**, approximately **28,672,095 bytes** summed from reported blob sizes (not Git pack size). Major extensions:

| Type | Count |
|---|---:|
| Compiled HLSL/DXIL `.dxil` | 85 |
| Python `.py` | 50 |
| JSON `.json` | 54 |
| C/C++ sources `.c` / `.cpp` | 9 / 7 |
| C headers `.h` | 28 |
| Include fragments `.inc` | 10 |
| HLSL `.hlsl` | 15 |
| Zig `.zig` | 17 |
| Tracked Windows binaries `.exe` | 12 |
| PNG / MP4 / ZIP | 19 / 2 / 2 |
| CSV / patch | 8 / 3 |

The supported development target is **Windows x64 / Direct3D 12**, using **Zig 0.15.2, C, HLSL, Python**, Windows SDK/DXC, and bundled Dear ImGui source for the portable playground. Shader double precision is required on tested paths. No Linux/Vulkan/Metal backend is present or qualified.

## Modules and current contracts

| Area | Key files | Status |
|---|---|---|
| Entry points and public contracts | `api.h`, `runtime.h`, `physics.h`, `main.zig`, `build.zig` | Native Windows standalone implementation; public/stable engine API is not formally qualified |
| GPU storage/lifetime | `storage.zig`, `storage.hlsl`, `layout.*`, `transaction.zig` | G0 planning and G1 scoped historical results |
| GPU spatial hash and contacts | `spatial.c`, `spatial.hlsl`, `spatial-layout.h`, `physics.c` | G2 scoped results; contact and island formation integrated |
| GPU contact solver | `projected_solver.hlsl`, `physics.hlsl`, `physics.c`, `physics-math.hlsl` | G3 scoped; **G5 deferred/not qualified** for difficult large connected islands |
| Requalified playable billiards | `pool.hlsl`, `pool-layout.h`, `play_ui.cpp`, `playground_view.inc`, `viewer.c` | Local analytic/headless evidence; G4 conditional; GPU-02 physical scanout unverified |
| G6 immutable accepted state | `state-publication.h/.inc`, `publication-runtime.inc`, `publication-tests.inc` | G6-P1 bounded local PASS |
| G6 resource ownership | `work-ownership.h/.inc`, `resource-claims.inc`, `ownership-tests.inc` | G6-P2 bounded local PASS, owner-thread serialized; not a general scheduler |
| G6 real GPU renderer consumer | `render-consumer.inc`, `render-consumer-tests.inc`, `render_consumer_main.zig`, `viewer.c` | G6-P3 bounded **offscreen** local PASS; CPU acceptance wait ~1.13 ms median |
| Generated schemas and pipelines | `*-schema.json`, `generate*.py`, `build*.py`, tracked `*.dxil` | Contracts are generated and outputs checked in; repeatability needs Windows tooling and artifact/hash checks |
| Tests, benchmarks and packaging | `dev_test.py`, `test_*.py`, `run_g6_p1.py`, `run_g6_p2.py`, `run_g6_p3.py`, `package*.py` | Multiple local scripts; no repository CI workflow found |

## Git and integration

At audit start: **10 branches**: `main`, playable requalification, billiards correction, G4 interactive/playground, G5 contact snapshot and Anderson experiments, G6-P1/P2/P3. The cumulative G6-P3 branch includes P1 and P2 (linear ancestry) plus playable work; merging it is not three separate independent merges.

Before this audit the GitHub pull-request API returned **zero historical PRs**, open or closed. **PR #1** was created, conflict-reconciled, and merged into `main`. Integration used a two-parent merge combining the G6-P3 tested source and `main`'s docs-only history; the only new file-content resolutions compared with the G6-P3 tested tree were the full authoritative architecture record and a **comment-only** `PH_WORK_EXTRA` limit correction (three → five). The playable branch retains separate history and needs an explicit history-preserving sync, not a forced ref overwrite.

The separate G5 experimental branches are retained as evidence, **not** approved production optimizations. No experiment was automatically promoted by this merge. README and AGENTS development instructions came from the more detailed playable branch; the full living `docs/ENGINE_ARCHITECTURE.md` from `main` was preserved, with a new integration decision.

## Risk / discrepancy register

1. **No Windows CI:** Recursive tree contains no `.github/workflows` or other GitHub Actions workflow. The integration has **no GitHub checks/workflow runs**; prior Windows headless passes are evidence for the development branch, not a post-merge retest.
2. **No GitHub releases:** Releases endpoint returned an empty array. `README.md` refers to `dist/GPUPhysicsBilliards-Windows-x64-20261018-requalified.zip`, but that exact file is **not in the tracked main tree**. Older benchmark/playground `dist/` ZIPs and 12 prebuilt Windows executables are committed; distinguish archival artifacts from tested current release payloads.
3. **Tracked generated/binary artifacts:** 85 DXIL files, 12 EXEs, two historical ZIPs, 19 PNGs and two MP4s increase repository size and may be stale relative to sources. Introduce an explicit artifact policy and reproducible build/manifest checks; do not delete historical evidence without an approved retention plan.
4. **G5 solver convergence:** Large connected 1,024-body chain requires ~4,024 sequential sweeps and ~140 ms solver execution under the recorded deterministic test; Anderson trial lost convergence in eight formerly passing fixture/policy configurations. **Deferred, not passed**. Do not restart incidental micro-optimization sweeps.
5. **G6 P3 host synchronization:** CPU accepted-generation wait measured **1,131.8 μs p50** in the headless offscreen P3 case, which may limit CPU/GPU overlap; defer or consume last accepted generation if safe.
6. **Device and display claims:** No physical device removal/recovery has been tested, and GPU-02 displayed FPS/real scanout remains unverified. Offscreen `DrawInstanced` is not a displayed-frame qualification. General user-defined GPU workloads and multi-device/multi-producer scheduling are not qualified.
7. **Architecture/version evidence:** The long `ENGINE_ARCHITECTURE.md` is the persistent gate record. The G6 and G5 handoffs have local Windows test evidence, but exact integration-head full tests have **not** been executed in this inventory. GPU 1,000,000 *storage/synthetic scattered scenes* must not be described as 1,000,000 fully coupled physics interactions.
8. **Timing accounting:** Earlier P2 `break` fixture has an unexplained ~95 μs execution-mode shift; exclude from speedup or acceptance claims until reconciled.

## Recommended next actions (scoped)

**Immediate:** Validate the current integration head on Windows with `python dev_test.py` and `python run_g6_p3.py`; verify all tracked shader hashes/build outputs before declaring the merged development baseline independently tested. Keep G5 deferred/G6 unqualified in reports.

**Next engineering task:** G6-P4 should remove the unnecessary CPU accepted-state blocking wait using only safe already-accepted generations/queue fences and without creating an unrelated scheduler.

**Repository operations:** Add a small Windows headless GitHub Actions smoke-test workflow after confirming toolchain/SDK installation and time budget; fix the README release filename/status; decide a generated-artifact policy; recheck G4 real display/device-loss boundaries only when those claims are needed.

**Qualification discipline:** P1, P2, and P3 are local *preparation* passes. Neither integrating their source nor reconciling Git history turns them into a formal G6 engine-foundation pass.
