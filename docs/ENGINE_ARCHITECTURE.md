# GPU Physics Engine — Technical Architecture and Development Record

**Project:** [Cryosimorgh/GPU-physics-engine](https://github.com/Cryosimorgh/GPU-physics-engine)  
**Record date:** 2026-10-18  
**Document type:** Living engineering record  
**Style:** Clear technical English, based on ASD-STE100 principles without strict controlled-language limits  
**Status:** Experimental GPU physics engine. G5 and production release are **not qualified**.

> **Update rule:** Update this document in the same change that closes, rejects, or reopens a development breakpoint. Keep prior results and their limitations. Do not turn a local experiment into a released feature by changing its status here.

## 1. Purpose and scope

The project tests a **GPU-first physics architecture** for many moving entities and contacts. It uses native Zig and C on Windows, Direct3D 12 for GPU execution, and HLSL compute shaders for simulation. The current physics model is mainly **two-dimensional disks**. The playable billiards mode adds a limited model of rolling and spin. It is not a general three-dimensional rigid-body engine.

The central design aim is to keep the simulation state and most calculations on the GPU. The CPU configures work, submits commands, processes bounded results, and controls resource lifetime. It should not move every entity to system memory after each tick.

This repository is an **independent experiment**. It does not depend on Unity or GGG. Integration with another application is a later design decision, not a completed feature.

### Evidence boundaries

There are two different development baselines:

- [`main`](https://github.com/Cryosimorgh/GPU-physics-engine/tree/main) stores the original G4 engine snapshot. It does **not** contain the later G5 sweep code or all subsequent optimization experiments.
- [`billiards-playable-requalification-20261018`](https://github.com/Cryosimorgh/GPU-physics-engine/tree/billiards-playable-requalification-20261018) stores the later playable billiards, headless test workflow, and revised shaders. Its test and README claims apply to that branch.

G5 results in this record come from **user-supplied local handoff results**, not from a G5 release on `main`. The latest uploaded `results.json` describes a quick, two-sample, cold, one-tick sweep. It explicitly marks `qualification: false`.

Use these labels throughout the document:

| Label | Meaning |
|---|---|
| **Implemented** | Code exists in a named repository revision. |
| **Measured** | Recorded execution data supports the stated workload and hardware. |
| **Conditionally accepted** | The scoped tests pass, but at least one exit condition is open. |
| **Experimental** | A local or branch-specific change needs broader evidence. |
| **Planned** | A design target. No implementation claim. |

## 2. System layout

```text
Inputs / scene / structural commands
             |
             v
      CPU command control
      - resource admission
      - command lists and fences
      - fixed global tick number
             |
             v
       GPU simulation passes
   1. Prepare provisional state
   2. Build spatial search data
   3. Find candidate body contacts
   4. Add wall and contact constraints
   5. Build connected contact islands
   6. Color and solve constraints
   7. Check physics and memory guards
   8. Publish accepted state generation
             |
             +----> GPU rendering of a completed generation
             |
             +----> Bounded diagnostic and timing readback
```

The order is important. Broad-phase search must precede contact solving. Contact graph data must be complete before the solver uses it. A result must pass validation before clients treat it as accepted state.

**Architectural gap:** The G4 `ph_publish` shader writes accepted per-body results back to the original `source` buffer. It is guarded by validation, but it is **not yet a strict full-generation buffer swap**. The intended rule is that `S(t)` remains read-only for the entire tick, and only a validated `S(t+1)` becomes visible. This requirement remains open until source bindings, publication, in-flight ownership, and failure behavior prove it. Do not call strict immutable snapshot isolation complete.

## 3. GPU backend and execution control

**Code:** `api.h`, `runtime.c`, `runtime.h`, `physics.c`, `viewer_runtime.c`.

The backend creates a D3D12 device, queues, resources, command allocators, command lists, query heaps, and fences. HLSL shaders compile into DXIL. The host uses explicit resource states, GPU command ordering, and fence completion to control reuse and destruction.

Key choices:

- **Native Zig/C host:** Avoids a large managed-engine layer in this experiment. It also makes CPU command overhead easier to measure.
- **HLSL compute passes:** Keep spatial search, integration, constraint work, and result checks on the GPU.
- **Explicit synchronization:** Use GPU barriers for dependent passes and fences for resource lifetime. A fence signals completion; it does not prove a physics result is valid.
- **Indirect GPU work:** Generate dispatch counts and decide whether optional work is needed without copying each count to the CPU.
- **Timestamp queries:** Measure GPU work separately from CPU submission, waiting, rendering, and presentation.

**Distinct engineering value:** The work scheduler, memory ownership, and simulation are tested together. The useful result is measured end-to-end behavior, not a fast isolated kernel.

**Not implemented as a general service:** A complete autonomous GPU resource monitor, multi-client allocator, or general dependency scheduler. Current code has memory budget checks and a specialized fixed-pass pipeline. A general job graph remains planned.

## 4. Entity identity and GPU storage — G1

**Code:** `entity.zig`, `transaction.zig`, `storage.zig`, `storage.hlsl`, `layout.zig`, `layout.hlsl`.

Entities use **stable slot IDs with generation counters**. A dense index can change when live entities are compacted, while a stale handle must not become valid again after slot reuse. Separate maps connect slot IDs and dense storage.

The project compared three data layouts:

| Layout | Trade-off | Observed decision |
|---|---|---|
| Array of structures (AoS) | Simple per-entity access; extra data can enter a cache line. | Not selected for the measured pipeline. |
| Structure of arrays (SoA) | Passes can read only the fields they need. | **Selected** for the tested workload. |
| Array of structures of arrays (AoSoA32) | Groups fields into fixed-size tiles. | Tested; not selected as the default. |

The selected SoA layout stores entity fields in GPU buffers. Active entities can be compacted into a dense work list. A structural epoch invalidates cached active lists when the entity set or active policy changes.

Resource growth allocates new capacity, migrates live state, verifies maps, and retires old allocations only when owners finish. The earlier G1 evidence reports live processing at 10 million entities and growth to approximately 20 million **allocated slots**. The latter is a capacity test, not a 20-million-entity performance result.

**Measured historical G1 result:** Around **3.30 ms** for the selected 10-million-entity storage workload with 10% active entities. This is a storage pipeline result, **not full physics**.

**Innovation / value:** Generation-safe ECS identity, GPU-resident compaction, and verified lifetime-safe capacity changes work in one native pipeline. The individual methods are known techniques; the integration and evidence are the project contribution.

## 5. Memory limits, resource budgets, and failure control — G0/G1

**Code:** `runtime.c`, `storage.zig`, `physics.c`.

Before large allocations, the host computes buffer sizes with checked integer arithmetic. It compares required memory with a current DXGI budget and any user limit. The allocator records committed bytes, peak use, allocation counts, and retired resources.

The resource tests cover allocation failure, invalid dimensions, guard regions, delayed fences, structural changes, and cleanup. A failed allocation must not damage existing accepted state. Resource retirement must not release a buffer while the GPU or graphics queue still owns it.

**G0** established legal capacity and dispatch plans. For example, a historical 10-million-body plan used about **10.75 GB** under its assumptions. A legal memory plan is **not** proof of execution speed or a promise that all 10-million-body workloads fit every GPU.

**Open work:** A complete GPU resource broker with priorities and fair admission for independent simulation clients. Today, the system mainly applies budget limits and explicit ownership to its own workload.

## 6. Spatial indexing and contact discovery — G2

**Code:** `spatial.c`, `spatial.hlsl`, `spatial-schema.json`.

Testing compared a GPU spatial hash with a radix-based path. The selected hash uses an open-addressed lookup structure and a staged count, prefix, and scatter flow. The GPU uses it to find body pairs that may touch. Candidate pairs are not accepted contacts until the narrow phase checks them.

A broad-phase pipeline must avoid two errors:

1. **Missed contacts:** A pair reaches or crosses the contact boundary but is absent from the candidate set.
2. **False correctness claims:** A candidate count is reported as an actual resolved-contact count.

The GPU maintains counts, capacity guards, and checks of body-to-slot mapping. High-density tests validate contact coverage independently.

**Measured historical G2 result:** The hash path processed the specified 10-million-body workload with about **35 million verified contacts** in about **24.04 ms**. The compared radix path took about **37.67 ms** under that test. These results cover candidate/contact construction, **not resolution**.

**Innovation / value:** The broad phase was chosen by direct workload measurements. GPU-side contact counters and verification connect speed results to the work actually performed.

## 7. Contact graph and island construction — G3/G4

**Code:** `physics.c`, `physics.hlsl`, `execution-layout.h`.

Every body contact adds a constraint edge. The graph passes join bodies that depend on one another. A connected component forms a **collision island**. The solver may process independent islands at the same time.

The pipeline builds parent/root information, counts island members and constraints, scans offsets, and scatters data into contiguous ranges. Contact coloring separates constraints that must not write the same body concurrently.

This prevents a common GPU error: two threads update the velocity of the same body without an ordered resolution policy. It also exposes a cost: one very large island offers less simple parallel work than thousands of small independent islands.

The G4 billiards stress fixture has many **separate 16-ball tables**. It tests high population and many small contact islands. It does **not** show that a million mutually connected bodies can be solved efficiently.

**Open work:** Multi-workgroup solving for large islands, plus coordination costs, shared/global memory trade-offs, and bounded convergence under general contact graphs.

## 8. Projected contact solver — G3/G5

**Code:** `projected_solver.hlsl`, `physics.hlsl`, `physics-math.hlsl`.

The solver uses projected impulses. Normal impulses must not pull two bodies together. Friction impulses remain inside their configured bounds. The iteration loop measures a constraint residual and stops only when the result satisfies its tolerance, or when it reaches a work limit.

The solver stores accepted per-body state in 32-bit floating-point fields. Some sensitive intermediate calculations use 64-bit floating point. This helps avoid cancellation near strict convergence limits. The implementation checks momentum, energy, constraint residuals, and published-state consistency with independent tests where applicable.

A single-workgroup path can use local memory for a small island. Larger islands may use global GPU memory and need many synchronization steps. This is the main reason a large, tightly coupled graph can be much slower than the same number of independent entities.

### G5 convergence study: PGS and SOR

A local experiment added **projected successive over-relaxation (SOR)** with factor **1.995** for qualifying large islands. It improved difficult compressive chains. It did not improve all graphs.

| One connected island | PGS outcome / GPU time | SOR 1.995 outcome / GPU time |
|---|---:|---:|
| Chain, 64 bodies | Rejected / 19.58 ms | Accepted / 16.41 ms |
| Chain, 256 bodies | Rejected / 37.33 ms | Accepted / 31.63 ms |
| Chain, 1,024 bodies | Rejected / 187.60 ms | Accepted / 148.63 ms |
| Branching, 64 bodies | Accepted / 2.76 ms | Accepted / 14.21 ms |
| Dense, 64 bodies | Accepted / 1.98 ms | Accepted / 24.48 ms |
| Oblique/friction, 64 bodies | Accepted / 4.69 ms | Accepted / 9.88 ms |

These are the medians of **two cold, independent one-tick samples per configuration**, from the 2026-10-18 uploaded quick sweep. A rejected time measures an **attempt**, not a successful physics tick. This is not a sustained benchmark or an approved G5 performance target.

The results identify a clear trade-off: **fixed high relaxation rescues chains but often wastes thousands of iterations on other graphs**. For example, the 64-body dense fixture needs 107 PGS iterations and 3,232 SOR iterations. No one global factor has been qualified for all tested contact patterns.

### G5 adaptive relaxation trial — rejected (2026-10-18)

A new local headless sweep compared **PGS**, **fixed SOR 1.995**, and one **adaptive residual-based** policy. It used ten deterministic cold compressive fixtures and two independent one-tick samples per solver and fixture (**60 runs**). The CSV matches all 30 JSON summary entries. Every accepted run passed the recorded independent invariants, and rejected attempts reported verified rollback.

| One connected island | PGS GPU p50 | Fixed SOR GPU p50 | Adaptive GPU p50 | Adaptive outcome |
|---|---:|---:|---:|---|
| Chain, 64 bodies | Rejected / 19.67 ms | Accepted / 15.55 ms | **Accepted / 2.39 ms** | 366 iterations |
| Chain, 256 bodies | Rejected / 39.39 ms | Accepted / 33.34 ms | **Rejected / 35.19 ms** | Reached 4,096 iterations |
| Chain, 1,024 bodies | Rejected / 188.93 ms | Accepted / 150.51 ms | **Rejected / 175.11 ms** | Reached 4,096 iterations |
| Branching, 256 bodies | Accepted / 15.26 ms | Accepted / 28.60 ms | Accepted / 15.63 ms | Near PGS cost |
| Dense, 64 bodies | Accepted / 1.94 ms | Accepted / 28.23 ms | Accepted / 1.85 ms | Near PGS cost |
| Oblique/friction, 256 bodies | Accepted / 34.95 ms | Accepted / 34.68 ms | Accepted / 33.92 ms | Near PGS cost |

The adaptive policy converged in **16 of 20** attempts; fixed SOR converged in **20 of 20**, and PGS in **14 of 20**. It reduced the 64-body chain solver work substantially, but it lost required convergence for the larger chains. Reported rejected GPU times are failed **attempt costs**, not simulation throughput.

**Decision: REJECT ADAPTIVE.** The submitted local results state that the pre-change source policy and production shader binaries were restored. The previous fixed-SOR policy remains the local working baseline; the restoration was **not followed by a separate GPU rerun**. No code or binary change was introduced by this documentation update.

**Evidence:** User-uploaded `results(2).json` and `results(2).csv`; quick run, 2026-10-18; 2 samples per case, 4,096-iteration limit, no GBV or sustained workload claim. These evidence files are **local**, not GitHub CI. Recorded sweep SHA-256: `81de61132ef41cd1937d6c4f591e4cb528732b8d6`.

**Next action:** Use a **headless residual-trajectory diagnostic** on chain sizes 64, 256, and 1,024 to find why adaptive relaxation stalls. Evaluate one safeguarded fallback or restart rule, with a strict work budget and both fixed baselines unchanged. Run a single consolidated sweep. Do not launch the viewer, capture screenshots, or start multi-workgroup solver development yet.

### G5 bounded-restart candidate — conditional correctness pass (2026-10-18)

Production remains policy 1: the existing PGS/fixed-SOR behavior (not a qualified G5 result). Policy 2 is
the rejected residual-adaptive experiment. Policy 3 adds one bounded restart
and is retained as an **opt-in correctness candidate**, not a G5 qualification
or a production performance improvement.

The experiment reports retaining the SoA storage, spatial/contact pipeline,
contact graph, global tick, immutable free-state inputs (not strict immutable
source-buffer publication), projected normal/tangent constraints, rounded-state KKT
tolerances, validation, work limits, and rollback are preserved. The change is
local to the existing GPU island solver; it creates no scheduler or CPU solve.

### Diagnosis

GPU traces record every 64-iteration residual window and relaxation change.
The 64-body chain settles near omega 1.929 and converges without a reduction.
For 256 bodies, a window contraction ratio of 2.633 at iteration 384 halves
the excess relaxation from approximately 1.995 to 1.4975. For 1024 bodies,
reductions occur at iterations 320 and 3200 (ratios 1.486 and 13.967).
The controller mistakes nonmonotonic SOR residual transients for sustained
instability. It then restores relaxation too slowly: the final factors are
1.9328125 and 1.9638911, respectively. Both exhaust 4096 iterations.
Independent contact/impulse/oracle checks and exact rollback pass; this is a
relaxation-control failure, not evidence of incorrect contact equations.

### Bounded fallback and measured decision

Policy 3 spends at most one eighth of the island's existing iteration/work
budget on adaptation. If it has not converged, it clears only that island's
impulses, restores its immutable free velocities, and runs fixed SOR 1.995 for
the remaining budget. There is at most one restart, no new allocation or
mid-solve readback, no size/topology/fixture rule, and no tolerance or limit
increase. A remaining-budget failure still rejects and rolls back normally;
this is not a universal convergence guarantee.

One serialized quick batch: two cold one-tick trials per configuration, plus
six instrumented chain trials. The diagnostic automatically reproduced the
old-policy failures before allowing candidate execution. All 20 candidate
and 20 fixed-SOR benchmark trials converged; PGS converged in 14 and rejected
six at 64/256/1024 bodies. The reviewed JSON contains 60 timing runs and 6
additional diagnostic runs; all 30 summary medians agree with their raw samples.
All 54 accepted benchmark runs report accepted-state invariant checks, and all
6 rejected runs report verified rollback. Actual island/contact coverage, KKT, impulse
reconstruction, accepted-state invariants and rejected-state rollback passed.
There were no timeouts or final audit errors. Thirteen sweep unit tests pass.

| Chain bodies | Fixed SOR GPU p50/p95, ms | Candidate GPU p50/p95, ms | Candidate iterations |
|---:|---:|---:|---:|
| 64 | 15.69 / 15.72 | 2.52 / 2.57 | 367 |
| 256 | 33.76 / 33.89 | 39.78 / 39.85 | 4036 |
| 1024 | 148.51 / 149.50 | 173.56 / 177.48 | 4026 |

The fallback recovers every previously converging configuration, but discards
useful adaptive/PGS progress on slower successful networks. At 256 bodies,
branching costs 34.39 ms versus PGS 15.86 ms, and oblique/frictional costs
52.64 ms versus PGS 31.14 ms. Keep production unchanged. The next target is
a residual-informed restart trigger that avoids these unnecessary restarts;
the 1024-body global-memory island solve remains the dominant cost.

### Decision breakpoint: remove unnecessary restarts (policy 4)

Retain policy 4 as an opt-in successor to policy 3. At the same one-eighth-budget
checkpoint (iteration 512 with the unchanged 4096 limit), restart only when
the minimum absolute projected residual in the last complete 64-iteration
window is at least 0.8 times the preceding window minimum. This reuses the
controller's existing poor-contraction threshold. Improving windows preserve
their impulses and velocities; there is no later forced restart or increased
budget. Restarted islands use the same single clean fixed-SOR fallback.
The rule has no topology, size or fixture lookup. All KKT, projection, friction,
energy/momentum and rollback checks remain unchanged.

Saved policy-2 traces showed checkpoint ratios 1.3123 and 0.9731 for the failing
256/1024 chains. In the new batch, candidate ratios were 0.9956/0.9639 for those
chains (restart), 0.5391 for branching-256 and 0.3903 for oblique-256 (preserve).
All ten instrumented candidate histories satisfy the restart decision audit.

One automated `python sweep_g5.py quick --trace-restarts` invocation ran 17
unit tests, built once using verified dependency caches, then serialized 80
uninstrumented timing trials and ten candidate trace checks. Every candidate,
policy-3 and fixed-SOR timing trial converged (20 each); PGS converged in 14
and rejected six. All ten candidate trace cases converged. Full contact/island
coverage, unchanged invariants and rejection rollback passed; no timeouts or
audit errors occurred. No passing case was rerun manually.

The predeclared retention rule requires both equal-fixture geometric mean
and sum of GPU p50 times to be no worse than policy 3, with no lost convergence.
The measured ratios were 0.8690 and 0.8650; summed CPU submission medians were
0.9876 of policy 3. Branching-256 improves from 33.63 to 15.57 ms and
oblique-256 from 56.85 to 30.66 ms. Candidate chain-256/1024 still require
4036/4027 iterations, with GPU p50/p95 39.78/39.92 and 171.52/171.97 ms.
Small individual timing increases remain visible in the raw comparison; two
samples are exploratory, not a tail-latency or significance claim.

The remaining dominant cost is the 1024-body one-workgroup/global-memory solve:
170.30 ms of its 171.52 ms complete tick. The restart still discards 512
iterations on hard chains. Production stays policy 1; no broader G5 approval
is implied. **Evidence:** User-uploaded `results(4).json` and `ENGINE_ARCHITECTURE(2).md` (2026-10-18), saved locally in the Codex workspace under `dev-test-results/g5-sweep-20261018T080015570617Z/`. The companion CSV and residual-traces CSV are referenced in the handoff but **not available on GitHub** or independently inspected here. The raw JSON contains full trace events, test statuses, CPU/GPU timings, source/build hashes, and measured candidate results. No GPU runs were executed during this document update.

**Gate and provenance note:** These results represent a local opt-in solver experiment. They do not establish that the policy-4 HLSL implementation has been committed to the linked GitHub branch. They are not a sustained-simulation qualification, and the 80 two-sample timing runs cannot establish stable p95 latency. G5 remains **NOT QUALIFIED**.

### Reproduction and evidence

Run `python sweep_g5.py quick --diagnose-adaptive`. All builds finish before
GPU cases execute sequentially under the existing workflow lock. Traced
diagnostic runs are separate from uninstrumented timing trials. The test-only
trace uses checked, bounded unused contact-record space; missing windows or
insufficient room fail the diagnostic without truncating simulation work.

Full results, CPU submission times, source/binary hashes and raw exports
were saved **locally** under `dev-test-results/g5-sweep-20261018T074517651930Z/`.
The user supplied `results(3).json` and `ENGINE_ARCHITECTURE(1).md` for this
review. The separate CSV and residual trace exports were referenced by the
handoff but were **not uploaded or committed to GitHub**. Therefore those
exports have not been independently inspected in this documentation update.

The batch required a trace-decoder repair for the GPU's distinct float32 and
float64 encodings of the 1.995 literal. `--resume` verified compiled artifacts,
reused 42 completed GPU cases, and ran only the 24 unexecuted cases, without
rebuilding. Original summaries retain those decoder failures; final trace
repairs used saved exports only. Timing controls therefore precede the resumed
candidate trials. Two samples make p95 merely the maximum, not a tail-latency
claim. No GUI, packaging, sustained campaign or broader gate approval occurred.
**Scope:** This evidence concerns local uncommitted solver experiments, not
code shipped on `main` or the playable GitHub branch. The source and compiled
binary hashes are reported in local JSON but binaries are not available here
for independent execution. Neither G5 nor the candidate is production-qualified.

### G5 global-memory solver profiling and body-cache experiment — REJECT (2026-10-18)

**Tested change:** A bounded group-shared body-state cache for at most 1,024 connected bodies, in `projected_solver.hlsl`. It keeps current work velocities and sleep state in shared memory, uses the existing global-memory path above that limit, and leaves other solver policies available for the sweep. The compiler reported 30,728 bytes of group-shared memory for this variant. The cache was tested behind `G5_BODY_CACHE`; the delivered default remains **0** and production relaxation policy remains **1**.

**Verification:** One serialized headless `python sweep_g5.py quick --profile-global` run produced 100 uninstrumented timing trials (ten deterministic fixtures × five solver configurations × two cold attempts) and 22 separate profiling/policy/boundary probes. The package includes 22 passing unit tests and archived per-run results. All **20 cached policy-4 trials converged** with passing invariant checks; across the 100 timing trials there were **94 accepted** and six expected PGS rejections with verified rollback. All 50 JSON summary medians match the recorded samples. A 1,025-body boundary probe used the global fallback and rejected/rolled back as expected.

| Connected island | Policy-4 global p50 | Cached policy-4 p50 | Change |
|---|---:|---:|---|
| Chain, 16 bodies | 3.53 ms | 4.30 ms | **21.7% slower** |
| Chain, 64 bodies | 3.09 ms | 3.77 ms | **21.9% slower** |
| Chain, 256 bodies | 37.16 ms | 37.68 ms | 1.4% slower |
| Chain, 1,024 bodies | 170.13 ms | **152.69 ms** | **10.3% faster** |
| Branching, 256 bodies | 19.30 ms | 18.89 ms | 2.1% faster |
| Oblique/friction, 256 bodies | 31.88 ms | 32.58 ms | 2.2% slower |

The 1,024-body **solver stage** changed from 167.47 ms to 150.47 ms; iterations changed from 4,026 to 4,025. The cache improves the heavy chain but harms the equal-fixture geometric-mean GPU p50 by **4.25%** (ratio 1.04253), despite reducing the sum of fixture medians by **4.82%** (ratio 0.95176). It therefore **fails the predeclared two-part retention rule**. Two samples per fixture are not enough to claim a statistical or p95 gain.

**Cost analysis and boundaries:** Rejected, rollback-verified PGS diagnostic probes yielded a complete-solver fit of **45.79 microseconds per iteration** and a **1.687 ms** fixed/intercept term. A synthetic barrier/reduction probe measured 0.674/0.811 ms for 128/512 virtual iterations; it is not an accepted physics solve or an additive synchronization share. Counted real runs recorded about **45,800 device barriers** and **36,240 group barriers**. Instrumented source-level body accesses imply about **1.100 GB of logical global working-velocity access** before caching, but compiler-elided loads, cache hits, real DRAM traffic, and stall time are not known. A bracketed empty-work queue interval of 0.837 ms contains multiple effects and is not pure dispatch overhead. Nvidia Nsight GPU performance counters were **not accessible** owing to permissions; no hardware-memory, FP64 utilization, or actual stall-cause attribution is established.

**Decision:** **REJECT as a general default.** Preserve policy 1 and `G5_BODY_CACHE=0`. The changed shader and analysis scripts are provided only in the local handoff; this documentation update does not commit or activate shader changes. G5 remains **NOT QUALIFIED**.

**Evidence:** Supplied `G5-Global-Solver-Cost-Handoff-20261018T090324676154Z.zip`; included `evidence/results.json`, `evidence/results.csv`, `evidence/profile.csv`, per-run JSON/logs, compiler diagnostics, and source. The archived and tested `projected_solver.hlsl` files match byte-for-byte; its SHA-256 matches the result manifest. A setup-only DXIL parser error, recorded in `setup-failure.json`, was fixed before GPU execution; the resumed run reused compiled artifacts. None of these local evidence files are claimed to be GitHub CI. The ZIP's `docs/ENGINE_ARCHITECTURE.md` is a **short experiment excerpt**, not this complete living record.

**Next action:** Investigate the high cost per solver iteration, separating arithmetic, synchronization, and memory behavior as far as is possible with headless CLI and static DXIL analysis. If hardware counters remain unavailable, report **UNVERIFIED** rather than guessing. Test at most one narrowly justified correction against complete-tick baselines with the same automated quick sweep.

### G5 per-iteration optimization — baseline recovery blocked, evidence located (2026-10-18)

**Failure report:** The user-supplied `G5-baseline-recovery-blocker.zip` contains a `BLOCKED` status, a documentation-only patch and a short status manifest. Codex could not reconstruct the measured G5 solver baseline after cleaning its local workspace. Its restored checkout at `3a29fc0ec9ff9ac54c0680e9130405368700074c` has the earlier fixed-relaxation shader but lacks `sweep_g5.py`, `profile_global.py`, the measured policy-4 shader and raw evidence. The blocker reports **no** GPU sweep, production shader change or optimization measurement. Its cited documentation commit `49fd7980253d69c64db4918c5a0ca113fd47d622` belongs to the local patch; this entry does not assert that the local commit was published.

**Evidence recovery:** The exact original `G5-Global-Solver-Cost-Handoff-20261018T090324676154Z.zip` is still available in the conversation uploads. Its SHA-256 is `07dd2be67af66faf089bdc726feb1b0b4d7cdd59a7250a8fcf7d4acb327c0a18`, exactly the value required by the blocker. ZIP integrity passes. It contains `projected_solver.hlsl`, `sweep_g5.py`, `profile_global.py`, unit tests, deterministic fixture files and archived raw results, CSV, traces and build logs. The shader matches its archived tested copy and the source manifest at SHA-256 `f9b93e98d3fb78944ae6547530d77e94cf29013ca61313af41d3448194bb05f9`. Its compile-time defaults remain **policy 1** and **`G5_BODY_CACHE=0`**; historical policy-4 tests require an explicit `G5_RELAXATION_POLICY=4` compile setting.

**Dependency check:** A hash-matched `profile_islands.py` was found in the previous G5 convergence handoff and a hash-matched `dev_test.py` in the requalified billiards handoff. In total, **seven** workflow files and **21 of 25** measured engine source files were recovered with matching SHA-256 hashes. Four baseline source files (`asset_path.h`, `physics.h`, `playground-layout.h`, `playground.hlsl`) have **not** been recovered from the accessible uploaded archives. They must be verified against the isolated target checkout before claiming a fully reproduced source baseline. The test binaries and original GPU execution environment are not bundled.

**Artifact:** The newly prepared `G5-Baseline-Recovery-Kit-20261018.zip` contains the original intact archive, hash-matched dependencies, available source snapshots, a manifest and a read-only local verification script. The kit passed an offline SHA-256 and ZIP integrity check. It is a recovery **handoff**, not a tested rebuilt baseline or a code patch.

**Decision: BLOCKED pending isolated baseline reconstruction.** Do not substitute an earlier solver's measurements for the policy-4 baseline, install unverified files into the user's dirty working tree, or claim another per-iteration optimization. Once all source hashes and build settings match, run one serialized headless quick sweep with the original unchanged shader to establish the Windows D3D12 baseline. Then profile or implement one semantics-preserving per-iteration change. G5 remains **NOT QUALIFIED**; G0–G4 status is unchanged.

### G5 isolated baseline restoration — source/behavior PASS (2026-10-18)

**Recovery:** An isolated Windows checkout rebuilt the measured G5 command-line baseline from the recovery kit. The package `G5-Baseline-Restored-20261018.zip` includes the rebuilt source snapshot, `projected_solver.hlsl`, the G5 sweep, its fixture binaries, raw run JSON and per-run exports, CSV summary, compilation logs, verifier, and comparison report. The original project workspace was not altered as part of this recovery.

**Source and build checks:** The restored manifest reports **25 of 25 source files** and **6 of 6 workflow files** matching the archived SHA-256 hashes, including all four previously missing sources (`asset_path.h`, `physics.h`, `playground-layout.h`, `playground.hlsl`). The ZIP source hashes match the manifest. The restored shader matches the saved tested shader at SHA-256 `f9b93e98d3fb78944ae6547530d77e94cf29013ca61313af41d3448194bb05f9`. All shader-output hashes match the archived baseline, with G5 policy 4 compiled as `G5_RELAXATION_POLICY=4` and `G5_BODY_CACHE=0`. The ordinary production default remains policy 1 and cache-off.

**Behavior test:** Recorded Windows commands ran **33 headless workflow/unit tests** successfully; the sweep's focused 17 tests also passed (these may overlap and must not be added as independent tests). The serialized quick sweep recorded **80 single-tick GPU trials**, ten connected-island fixtures, four solver configurations, and two cold samples per case. All **20 policy-4**, **20 policy-3**, and **20 SOR** trials converged; PGS converged in **14 of 20**, with six expected rejections and independently checked rollback. All **74** accepted trials passed the supplied physical invariant checks. The sweep returned exit code 1 because expected PGS rejection cases are treated as failures by its aggregate exit policy; this is not a claim that the recovery itself failed. The CSV agrees with all 40 JSON summary rows and their 80 recorded p50 sample values.

| Policy-4 workload (one connected island) | Prior archive p50 | Restored Windows p50 | Result |
|---|---:|---:|---|
| Chain, 64 bodies | 3.09 ms | **2.47 ms** | Converged, 367 iterations |
| Chain, 256 bodies | 37.16 ms | 38.40 ms | Converged, 4,036 iterations |
| Chain, 1,024 bodies | 170.13 ms | **167.94 ms** | Converged, 4,026 iterations |
| Branching, 256 bodies | 19.30 ms | 18.24 ms | Converged, 1,195 iterations |
| Oblique/friction, 256 bodies | 31.88 ms | 37.41 ms | Converged, 1,082 iterations |

These are two cold independent ticks per case. Differences between two samples are not evidence of sustained speedups or latency quantiles; p95 equals the larger of two samples.

**Non-identity limitations:** The rebuilt `physics.exe` SHA-256 differs from the historical executable (`b68e82b173659046a93767444ebaa9a90d6d222d473e34375ecf187a0fa1836e` versus `fbc98450e31ffe5eb452a58ab3457aa1f22319d1b1d26d2de65dfcc7a7dd0451`). The archived historical executable bytes are unavailable; the cause is **UNVERIFIED**. The archived/new comparison records **156 numerical field differences** in per-run KKT values, iteration counts and energy/momentum roundoff, plus **23 contact-color count differences**; the maximum iteration difference is **444**. There are **zero structural/acceptance mismatches** in status, body/contact/island counts, invariant pass/fail and rollback. The evidence therefore supports **source-and-behavior restoration, not bitwise deterministic replay**. GPU debug-layer/GBV and sustained multi-tick qualification were not repeated.

**Decision: RECOVERY PASS; G5 STILL NOT QUALIFIED.** The missing-file blocker is closed for controlled research. Use the restored isolated checkout as the next matched before/after baseline; retain the exact source hashes, compile flags, shader hashes and fixtures. Do not compare isolated two-sample timings across different builds as if they were performance qualification. Do not commit experimental policy 4 to production based on this recovery alone.

**Next action:** Diagnose the executable hash mismatch through recorded compiler/linker/build inputs **without changing solver mathematics or doing another broad GPU run**. Establish the current executable as a stable local baseline, then investigate one measured cost per iteration and compare before/after in **one headless CLI sweep**. Preserve the original workspace and update this document at the next decision.

**Evidence:** User-supplied `G5-Baseline-Restored-20261018.zip`, including `recovery-manifest.json`, `evidence/preflight/provenance.json`, `evidence/sweep/results.json`, `results.csv`, `recovery-comparison.json`, Windows logs and exported GPU state. ZIP integrity and recorded summary data were checked off-line; the GPU run was recorded on Windows, not repeated in this review environment. Local handoff evidence is not GitHub CI evidence.

### G5 repeated-body-load removal in solver measurement — RETAIN (2026-10-18)

**What changed:** The original `measure()` fetched the bodies for the contact's tolerance test, then fetched them again through `relative()` for normal and tangential projected residuals. The contact state is not written between those reads. The new `measureRelative()` reuses the already loaded `Body a` and `Body b`, with the same explicit float32 rounding before FP64 relative-speed calculations. The `applyColor()` path is unchanged; it still reloads the bodies after a normal impulse before applying the tangential impulse. The change does not alter the contact graph, constraints, projection, solver iteration/work budget, synchronization barriers, KKT acceptance rules, or rollback.

The new compile-time selector is `G5_REUSE_MEASURE_BODIES` (0 = original, 1 = reuse). The **retained source defaults to 1**. The retained source SHA-256 is `39d7d5e606dfad1cbd71de04e1de68a3d7d008e35f235bfdc01df8814edc233f`; the separately tested candidate snapshot has SHA-256 `f060d6975f6d82bd92145767cfb8a6c518ed14eecc55ec712c56882749f488bb` because the default macro was switched after testing. The recorded final production-policy `ph_ready` and `ph_solve` shaders were rebuilt and their hashes matched the policy-1 candidate shader results exactly. The default relaxation policy remains **1**, and body caching remains **0**. No new GPU correctness tests were run after only changing that compile-time default.

**Static shader evidence:** For policy 4, `ph_solve.dxil` includes **225 → 191** static buffer-load instruction sites, **71 → 55** double-assembly sites and **157 → 153** FP64 arithmetic instruction sites; shader barrier sites remain **20**. These counts describe disassembled instruction sites, not physical memory transactions, cache misses or real stall time. Fresh unchanged controls for policy 0/1/3/4 reproduced historical archived `ph_solve.dxil` hashes, and all five policy configurations used the same fresh linked CLI host executable across the two arms.

**Matched Windows headless test:** One `python sweep_solver_cost.py quick` batch ran 33 existing unit tests, compiled the control and candidate variants, and executed **200 cold single-tick trials** (10 fixtures × 5 policies × 2 variants × 2 attempts). All trials completed without timeout. Independently recomputing all 50 JSON summary medians from the 200 recorded runs found no mismatches. Each arm produced **90 accepted and 10 expected rejected** trials; the rejection breakdown is six PGS and four original-adaptive-policy cases. All accepted trials reported invariant checks passed, and each rejection reported verified rollback. The contact/island counts, acceptance status, KKT bounds and work limits remained valid. This is recorded Windows execution evidence, **not** an independently rerun GPU test.

| Tested policy 4, one connected 1,024-body chain | Unchanged control | Body snapshot reuse |
|---|---:|---:|
| Complete GPU tick p50 | 167.33 ms | **162.99 ms** |
| Solver-stage p50 | 165.35 ms | **161.12 ms** |
| CPU recording/submission p50 | 2.928 ms | 2.846 ms |
| Solver iterations, two trials | 4,026 / 4,025 | 4,026 / 4,027 |
| Actual contacts / largest island | 1,023 / 1,024 | 1,023 / 1,024 |

**Decision rule:** Retain only if all correctness/rollback conditions pass and both the geometric mean and sum of complete-tick GPU p50 improve across (a) the ten policy-4 fixtures and (b) all 45 accepted-policy configurations. The audited policy-4 geometric-mean/sum ratios are **0.962547 / 0.964774**; the all-accepted-policy ratios are **0.983971 / 0.953917**. Both predeclared aggregate performance tests pass. **Decision: RETAIN** the narrow source change.

**Limits and observed regressions:** Some individual workloads regressed: branching-64 policy 4 went from **3.129** to **3.241 ms**, and dense-256 from **11.168** to **11.580 ms**. Solver coloring and iteration counts also vary slightly between runs. Two cold samples do not support a robust p95 or sustained-performance claim. The 1,024-body connected chain still spends roughly **161 ms** in its solver, with about **4,026** iterations. The division between FP64 arithmetic, barriers and actual memory stalls remains **UNVERIFIED**.

**Executable reproducibility:** A newly built unchanged CLI had SHA-256 `237c22371b75c76ffed9cc5c50b4f4fbbe201bd77e7539f49c0466b4d7edddbc`, versus the recovered local executable `b68e82b173659046a93767444ebaa9a90d6d222d473e34375ecf187a0fa1836e`. Local PE section hashes match for every section except `.buildid`, providing a concrete metadata explanation for that local rebuild difference. The much older archived executable fingerprint `fbc984...` cannot be explained without its original bytes, build logs and linker inputs.

**Evidence:** User-supplied `G5-Solver-Snapshot-Reuse-20261018.zip`: source and baseline HLSL, `change.patch`, static DXIL dumps, `evidence/matched-quick/results.json` and `results.csv`, 200 per-run exports, `retained-build.json`, 33-test log, linker/PE provenance and source architecture excerpt. ZIP CRC verification passed; recorded source hashes and summary medians were checked. The archive's source doc is an **experiment copy**; this section is integrated into the full living GitHub record instead. **No experimental solver code has been pushed to GitHub by this review. G5 is not qualified.**

### G5 skip overwritten preliminary residual — RETAIN LOCALLY (2026-10-18)

**Change:** During `ph_solve`, every eighth solver iteration and the final allowed iteration must reconstruct the per-body velocities from the free state and accumulated impulses. That path runs a mandatory projected-residual measurement and uses its result for the acceptance check. The prior hot loop also measured the residual **immediately before** these mandatory reconstructions, even though the subsequent measurement replaced both residual outputs. With `G5_SKIP_OVERWRITTEN_RESIDUAL=1`, the candidate omits only that redundant preliminary scan. The device/group barrier before reconstruction remains. Preliminary scans on all other iterations, and the post-reconstruction KKT measurement, are unchanged. There is no change to contact equations, FP64 expressions, impulse projection, color order, iteration/work limits, validation, rollback or adaptive/fallback policy rules.

At 4,026 iterations, the source-level logic skips 503 preliminary measurements and approximately 4,024 group-reduction barrier executions while keeping all required reconstruction checks. These are **source execution counts, not measured GPU barrier stalls or DRAM transactions**. The candidate does not reduce the required 4,026 iterations. Static DXIL instruction-site counts remain **191 buffer loads, 55 double assemblies, 153 FP64 arithmetic operations and 20 barriers** for policy 4; this optimization avoids executing part of the compiled code instead of removing static instructions.

**Matched headless evidence:** The single `python sweep_solver_cost.py quick --skip-overwritten-residual` Windows batch recorded **200 timing trials** (ten deterministic one-tick fixtures × five policies × two compile flags × two cold samples) plus six separate chain residual traces. Each matched arm contained **90 accepted solves** and **10 expected rejections** (six PGS and four earlier adaptive-policy attempts). The recorded independent accepted-state checks passed; rejected attempts verified rollback. Trace checks reproduced the expected 64-, 256- and 1,024-body chains without changing accepted/rejected decisions. All **50** JSON summary rows were independently recomputed from the trial data and matched the CSV, with no mismatches. **34** workflow/unit tests passed in the final recorded run. No graphical tests or Windows GPU execution occurred during this documentation review.

| Policy-4 connected island | Existing snapshot-reuse GPU p50 | Skip-overwritten-scan GPU p50 | Outcome |
|---|---:|---:|---|
| Chain, 64 bodies | 2.98 ms | **2.33 ms** | 367 iterations in both arms |
| Chain, 256 bodies | 37.74 ms | **33.46 ms** | 4,035 iterations in both arms |
| Chain, 1,024 bodies | 165.61 ms | **155.86 ms** | 4,026 iterations in both arms |
| Branching, 64 bodies | **3.49 ms** | 3.78 ms | **Regression** |
| Oblique/friction, 256 bodies | 34.37 ms | **31.69 ms** | Accepted in both arms |

The **1,024-body solver stage** changed from **163.33 to 153.93 ms**. The retained candidate met the predeclared quick-balance test: policy-4 geometric-mean and total-p50 ratios were **0.940693** and **0.932529**; the corresponding ratios across **45 accepted-policy configurations** were **0.997168** and **0.971424**. The broad geometric-mean improvement is **only 0.28%**. Two cold trials per configuration cannot establish a general or sustained-performance gain; a reported quick p95 is merely the higher of two samples. Dense-64 and branching-64 policy-4 cases were slower.

**Source integrity and defaults:** The baseline snapshot-reuse shader SHA-256 is `39d7d5e606dfad1cbd71de04e1de68a3d7d008e35f235bfdc01df8814edc233f`. The source compiled in the explicit matched experiment has `G5_SKIP_OVERWRITTEN_RESIDUAL=0` as its default and SHA-256 `a9a8408f46da936140b8e2e6302f49e4de25504289f424d9be6946478f0b3697`; test commands override the flag to 0 or 1. The retained shader source differs only in that macro's **default value of 1**, and has SHA-256 `10c5ee6541c7799119a9578b304c51f8d3de3938e2221613894bc7fae75d5c24`. This difference is intentional; the original test-source SHA does **not** equal the retained file's SHA. The retained policy-1 `ph_ready` and `ph_solve` shader hashes match the explicitly tested candidate variant according to the Windows build log. Relaxation policy **1**, `G5_BODY_CACHE=0`, and `G5_REUSE_MEASURE_BODIES=1` remain the retained defaults. The user-supplied preservation report states that all **313 original tracked files and uncommitted status** remained unchanged in the original workspace; work took place in an isolated copy.

**Decision: RETAIN UNDER THE QUICK RULE, NOT RELEASE-QUALIFIED.** Keep the conditional skip in the local experimental shader. It reduces known redundant execution, but it does not resolve the main cost of ordered FP64 contact/color iterations and slow convergence. The 1,024-body solver still takes **about 154 ms per tick**. G5 remains **NOT QUALIFIED**. No code, shader binaries or test artifacts are committed to GitHub by this documentation checkpoint.

**Evidence:** User-uploaded `G5-Skip-Overwritten-Residual-20261018.zip`, including `source/projected_solver.hlsl`, `baseline/projected_solver.hlsl`, `change.patch`, `evidence/results.json`, `results.csv`, full per-run exports and residual traces, compiled DXIL listings, Windows unit logs, retained-build provenance, and workspace-preservation record. Archive integrity, diff scope, summary data, and available SHA-256 values were checked offline. These are local Windows recordings, **not GitHub CI or an independently rerun GPU qualification**.

### G5 early residual restart — REJECT (2026-10-19)

**Hypothesis:** The residual-gated policy 4 restarts a hard connected island at iteration 512, after using one eighth of its 4,096-iteration budget. A restart might save solver work if the current relaxation has failed to contract the residual. A new **opt-in policy-4-only** check restarts at an earlier complete 64-iteration window after **two consecutive poor-contraction windows** (contraction at least 0.8), once relaxation is above 1 and the settling period has ended. A fast-contraction window resets the evidence. The original iteration-512 checkpoint remains as a fallback; no topology name or body-count rule was used.

**Physics contract:** The experiment preserved the contact equations, normal/tangent impulse projection, FP64 computations, original work and iteration limits, residual/KKT and energy/momentum checks, and rollback. The earlier retained `G5_REUSE_MEASURE_BODIES=1` and `G5_SKIP_OVERWRITTEN_RESIDUAL=1` options remained enabled. No solver policy other than policy 4 was changed. The trace reader gained strict verification of early restart timing and settled poor-residual windows.

**Evidence audit:** The local Windows handoff `G5-Early-Restart-Rejected-20261019.zip` includes 200 serialized, cold single-tick timing runs across ten configurations, five policies, two arms and two samples per arm. It also includes 40 independently instrumented trace trials. **Each arm accepted 90/100 timed trials and rejected 10/100** (six expected PGS rejections and four expected original-adaptive-policy rejections). All **180** accepted trials reported passing invariant checks; all **20** rejected attempts reported verified rollback. All 40 trace trials converged, and the handoff reports **37 passing headless unit tests**. The **50 JSON summary medians** were independently recomputed from the raw runs and checked against the saved CSV, with no mismatches. This is recorded Windows GPU evidence; the D3D12 tests were not repeated during this review.

**Trace findings:** Policy 4 restarted only the 256- and 1,024-body chains in the traced set. In both, restart moved **512 → 256** iterations. Policy-4 trace restart counts stayed at **two per arm** across ten fixtures, while policy-3 remained at **four per arm**. The 1,024-body chain fell from about **4,025 to 3,769** solver iterations. Counts from instrumented traces are **not per-timing-trial measurements**. No 64-body chain or dense/oblique fixture triggered an early policy-4 restart in the reviewed traces.

| Policy-4 workload, one connected island | Retained control GPU p50 | Early-restart GPU p50 | Outcome |
|---|---:|---:|---|
| Chain, 64 bodies | 2.35 ms | 2.35 ms | No early restart |
| Chain, 256 bodies | 32.74 ms | **30.91 ms** | 4,035 → 3,779 iterations |
| Chain, 1,024 bodies | 150.31 ms | **147.05 ms** | 4,025/4,024 → 3,768/3,770 iterations |
| Dense, 64 bodies | **1.86 ms** | 2.05 ms | Slower without restart |
| Dense, 256 bodies | **9.70 ms** | 10.15 ms | Slower without restart |
| Oblique/friction, 256 bodies | **28.79 ms** | 32.65 ms | Slower without restart |

**Performance decision:** The unchanged four-part retention rule requires **both** the geometric mean and summed complete-tick GPU p50 to improve for (1) all ten policy-4 fixtures and (2) all 45 previously accepted policy configurations. Policy-4 geometric-mean ratio was **1.0097496** (0.97% worse) and sum ratio **0.9944305** (0.56% better): the candidate **failed**. Across all accepted configurations, geometric-mean/sum ratios were **0.9929693 / 0.9938164**, but they cannot override the failed policy-4 criterion. Some fixtures with no change in restart behavior grew slower. With two cold trials and variable contact-color ordering, these timing differences cannot be attributed to the new condition with high confidence. Static DXIL instruction-site counts were unchanged for policy 4; no claim about DRAM, occupancy or hardware stall savings is justified.

**Decision: REJECT; RESTORE PREVIOUS SOLVER.** The archive's retained `source/projected_solver.hlsl` has SHA-256 `10c5ee6541c7799119a9578b304c51f8d3de3938e2221613894bc7fae75d5c24`; its experimental `evidence/tested-projected_solver.hlsl` has SHA-256 `b57f6011133a647bf4c787913ed70a8be484923d27edd69a6c1e862ec10c449b`. The recorded restoration report confirms byte-for-byte rollback of the active shader, rebuilt policy-1 and policy-4 shader hashes matching controls, and preservation of the original workspace (388 checked files and dirty status unchanged). This architecture-document update does **not** publish experiment shader code. Keep the production policy-1 default and policy 4 opt-in. G5 remains **NOT QUALIFIED**.

**Next decision:** Before another restart heuristic, isolate run-to-run contact coloring and GPU timing variation by comparing fixed-input traces and matched configuration controls. Quantify whether a smaller restart budget offers a repeatable net improvement across the existing ten fixtures **without** weakening correctness criteria. If the variation cannot be controlled, prefer a targeted solver-algorithm study over threshold tuning. Do not run a long or GUI-based campaign.

### G5 identical-control measurement repeatability — MEASURED; solver unchanged (2026-10-19)

**Why this test exists:** Several prior candidate sweeps showed GPU-time and iteration differences even when the restart behavior did not change. To isolate confounding factors, a local Windows measurement tool ran **identical executable/shader controls labeled A and B**. No solver code, shader, relaxation threshold, acceptance criterion, or default changed. A/B labels carry **no optimization**.

**Test method:** `measure_repeatability.py` reuses the recovered G5 fixture, execution and independent audit. It verifies the same CLI executable, all shader files, ten frozen fixture binaries, source hashes and device identity before/after execution. Four paired AB/BA blocks per fixture produced **80 serialized cold one-tick GPU runs** on an **NVIDIA GeForce RTX 4070 Ti SUPER**: ten topologies/sizes × eight attempts. All **80** runs converged and passed the recorded accepted-state physics checks, with fixed body/contact/island counts. **43 preflight CPU/unit tests passed**. The retained solver-source SHA-256 was `10c5ee6541c7799119a9578b304c51f8d3de3938e2221613894bc7fae75d5c24`; the previously rejected early-restart shader was not used.

**Independent signature checks:** Binary contact/state exports yield distinct hashes for canonical contact geometry, raw contact and root order, contact color assignment, unordered-within-color pass structure, colored stream, local index mapping, immutable free-state inputs, resulting FP64 state, arithmetic schedule and exact dispatch placement. The parser verifies complete contact coverage, prefix ranges, label consistency, and that contacts in one color touch disjoint bodies. Across each fixture's eight trials, the canonical contact set and free state were invariant. Wherever an arithmetic schedule occurred more than once, it produced the same iteration count and final FP64 work state. This is **an observed conditional result**, not a proof of determinism for schedules that never repeated.

| One connected island | Distinct color-pass signatures / 8 | Iteration range | Complete GPU tick range | GPU tick CV |
|---|---:|---:|---:|---:|
| Chain 16 | 1 | 452 | 2.55–2.57 ms | 0.18% |
| Chain 64 | 1 | 367 | 2.30–2.34 ms | 0.60% |
| Chain 256 | 5 | 4,035–4,036 | 32.37–37.98 ms | 6.93% |
| Chain 1,024 | 8 | 4,024–4,026 | 154.64–169.29 ms | 2.95% |
| Branching 64 | 1 | 321 | 2.79–2.80 ms | 0.11% |
| Branching 256 | 7 | 1,194–1,195 | 13.91–16.64 ms | 5.04% |
| Dense 64 | 4 | 107 | 1.79–2.06 ms | 4.81% |
| Dense 256 | 8 | 417–418 | 9.49–10.30 ms | 3.08% |
| Oblique/friction 64 | 3 | 265–309 | 4.71–5.46 ms | 6.39% |
| Oblique/friction 256 | 8 | 816–1,087 | 24.93–32.47 ms | 8.79% |

**Mechanism and bounds:** `physics.hlsl` scatters root contacts with atomic ranks; the greedy `ph_color` pass consumes the resulting order. `ph_members` also allocates local indices with atomic ranks. `ph_color_ranges` changes within-color placement via atomics. These are valid but schedule-dependent choices; the audit did **not** find missing or duplicate contacts. On chain-256, different orders led to **two versus three colors/batches** and an overall GPU-tick CV of **6.93%**. In the five attempts belonging to repeated equivalent-arithmetic cohorts, pooled within-cohort tick CV fell to **0.51%**. Chain-64 changed contact/stream order but held its color-pass schedule and 367 iterations.

Earlier traced records with identical binary and shader hashes confirm that chain-256 and chain-1,024 both restarted at **iteration 512** across the compared runs; color schedules and iteration counts nevertheless differed. Chain-64 did not restart. This restart comparison comes from **archived trace files**, not the new uninstrumented A/A timing runs; per-run restart counts were not measured in those 80 new runs.

**What cannot be inferred:** Every chain-1,024 trial had a distinct color/arithmetic and exact-dispatch schedule. Its **2.95% overall tick CV cannot be called GPU clock/runtime-only noise**; hardware-only variation at an identical schedule is **UNVERIFIED**. The same caution applies to same-iteration groups that change color work. GPU timestamps include upstream spatial work; no physical bandwidth, cache, GPU-clock, stall, or CPU submission attribution is proven.

**Impact on earlier quick-performance claims:** Independent recomputation of A/B medians from the 80 JSON runs yields identical-code **B/A ratios 0.8664725–1.1282261** across fixtures, geometric-mean ratio **0.9888429** and sum-of-p50 ratio **0.9955101**. Thus the previously used two-part aggregate retention rule can show an apparent gain of 1.12% by geometric mean and 0.45% by summed time **without any code difference**. Historical decisions remain documented as taken, but small changes, including the previous 0.28% broad geometric-mean win, are not established as reproducible speedups. These descriptive eight-sample results do not define a statistical significance threshold.

**Measurement-tool correction:** The initial exact-dispatch signature omitted contact-record placement. The analyzer was corrected and passed **seven focused tests**; it reprocessed the same 80 saved GPU exports, with **zero new GPU calls**. Old analysis is preserved in `results-before-dispatch-signature-fix.json` and the previous CSV. The corrected summary matches the 80 raw trials and has zero alerts. One handoff preservation-summary field still lists an older `measure_repeatability.py` hash (`52c21a5a...`), while the archived file and the final source-hash manifest both match `c4fb504149ef21d585e320da79cc5a7664462ebab3d76e8b8aa3b8917ef17643`. Keep the canonical final manifest and reconcile the stale summary when maintaining the tool.

**Decision: MEASUREMENT VARIATION CONFIRMED; NO SOLVER OPTIMIZATION.** This is not a demonstrated contact-coverage, KKT, synchronization or mathematical correctness defect. G5 remains **NOT QUALIFIED**. Production relaxation policy **1**, opt-in policy **4**, and retained solver defaults stay unchanged. No GPU code or runtime/shader binaries are committed in this documentation checkpoint.

**Next action:** Provide a **measurement-only deterministic contact/color schedule or exact-schedule replay** for matched controls, without enforcing its overhead on normal production execution. Prove stable geometry, contact coverage, color conflicts, FP64 execution order, convergence and rollback; measure sorting/replay cost separately from complete-tick time. Once equivalent arithmetic can be reproduced, revisit the hypothesis that reducing color passes improves the large-island solve. Do not tune restart thresholds against unmatched schedules.

**Evidence:** User-uploaded `G5-Measurement-Repeatability-20261019.zip`: preserved prior trace sets, `measure_repeatability.py`, `test_repeatability.py`, a local architecture excerpt, full 80-run JSON/CSV and raw contact/state exports, analysis correction history, 43-test preflight log and SHA-256 manifests. ZIP CRC test passed; JSON statuses, summary medians, A/B ratios and key source hashes were checked offline. The handoff reports that **388 original files and the working-tree status were preserved** in the original workspace. Recorded Windows GPU runs were not independently repeated here.

### G5 bounded deterministic measurement mode — PASS FOR MEASUREMENT ONLY (2026-10-19)

**Revision and scope:** Local, **unpublished** experiment commit `8c1777e1ddcc9fba15073565db62dfab79dc17c3`, branch `g5-deterministic-measurement-20261019`. The new `G5_DETERMINISTIC_MEASURE=1` HLSL path sorts complete contact records **together with their FP64 accumulated impulses** by stable key, rebuilds canonical member indices/root-contact ordering and per-color streams, and verifies a conflict-free schedule before solver execution. The existing greedy coloring and `projected_solver.hlsl` equations are unchanged. The bounded test mode accepts only **fixture 0**, flags **0/2**, at most **1,024 bodies**, **2,048 contacts**, **one connected island**, and **no contact graph expansion after the first round**. Unsupported cases fail before publication, with unchanged rollback. The sort is serial **O(C²)**; this is a correctness/measurement instrument, **not a proposed production scheduling algorithm**. The original workspace had all **390 checked file hashes and dirty status preserved**, per the handoff.

**Production isolation:** Normal shader compilation has `G5_DETERMINISTIC_MEASURE=0` and normal C execution has `G5_MEASURE_TIMESTAMPS=0`. The default-off C preprocessor token stream is byte-for-byte equivalent to the retained native source, and all four affected default-off DXIL shader outputs match the baseline hashes. Eight measurement timestamps fit inside the already reserved 64 query slots (40 normal slots); recorded brackets include dispatch/barriers/base bookkeeping, and no mid-pass CPU/GPU synchronization is added. The retained solver shader SHA-256 is `10c5ee6541c7799119a9578b304c51f8d3de3938e2221613894bc7fae75d5c24`. Production policy **1**, opt-in policy **4**, `G5_BODY_CACHE=0`, `G5_REUSE_MEASURE_BODIES=1`, and `G5_SKIP_OVERWRITTEN_RESIDUAL=1` stay unchanged.

**Windows recorded validation:** One serialized `python measure_deterministic.py` run on **NVIDIA GeForce RTX 4070 Ti SUPER** recorded **180 cold, one-tick GPU trials**: eight deterministic policy-4 runs per fixture (**80**), two ordinary native policy-4 controls per fixture (**20**), and two deterministic trials for each policy 0–3 per fixture (**80**). Of **160** deterministic trials, **150 converged**, and ten expected PGS/old-adaptive trials rejected with exact verified rollback. All **20** native policy-4 references converged. Two additional unsupported-envelope cases—**1,025 bodies** and **two islands**—returned error **64**, rejected without publication, and verified exact rollback. Initial **48 unit tests** and five focused post-setup-fix tests passed. Recorded verification covers independent contact coverage, single-island size, coloring conflicts, KKT, impulse reconstruction, energy/momentum and rollback.

**Independent audit:** ZIP CRC passes. All **1,513** archived file hashes match `manifest.json`, all **ten** JSON summary medians match the raw eight deterministic policy-4 trial timings and the saved CSV, and no accepted/rejected proof flag differs from the documented result. All deterministic fixture/policy combinations repeat identical **contact-set, contact-order, color assignment, per-color stream, local mapping, exact dispatch, FP64 work-state and published-state hashes**, together with constant solver iterations. This is an observed same-device/compiler bounded result, not a cross-device numerical determinism guarantee.

| Policy 4, connected island | Contacts | Solver iterations | Deterministic tick p50 | Scheduling bracket p50 | Native scheduling p50 | Tick CV |
|---|---:|---:|---:|---:|---:|---:|
| Chain 64 | 63 | 367 | 2.855 ms | 0.049 ms | 0.009 ms | 12.78% |
| Chain 256 | 255 | 4,035 | 36.246 ms | 2.985 ms | 0.011 ms | 1.74% |
| Chain 1,024 | 1,023 | 4,024 | 194.935 ms | **46.954 ms** | 0.017 ms | 2.11% |
| Branching 256 | 255 | 1,194 | 19.115 ms | 3.764 ms | 0.011 ms | 4.30% |
| Dense 256 | 480 | 417 | 19.715 ms | 9.182 ms | 0.011 ms | 18.57% |
| Oblique/friction 256 | 480 | 1,016 | 37.972 ms | 10.282 ms | 0.013 ms | 10.57% |

**Measurement limits:** Deterministic schedules do **not** make GPU execution time deterministic. On the 1,024-body chain, the **solver alone** spans **139.626–147.381 ms** despite an identical 4,024-iteration arithmetic schedule; its solver CV is **1.79%**. The complete GPU tick includes scheduling and timestamp instrumentation. The **46.954 ms** scheduling bracket is **not** a pure sorting-instruction cost, and a native run may solve with a different arithmetic schedule. The bounded serial sort is deliberately unsuitable for production or general larger/multi-island graphs. Eight cold samples are exploratory; no p99, thermal-stability, memory-stall attribution or cross-device result is established.

**Recovery/provenance:** Two setup-only failures (log-header comparison and pre-existing output directory) happened **before any GPU run**; preserved failure records are superseded by the successful `results.json`. The preceding repeatability archive's delivered helper `measure_repeatability.py` hashes to `c4fb504149ef21d585e320da79cc5a7664462ebab3d76e8b8aa3b8917ef17643`, matching its final manifest, while one supplemental summary incorrectly lists `52c21a5a...`. The helper hash at the **original previous GPU-execution time** remains **UNVERIFIED**. This deterministic batch recorded and verified its input/helper hashes before and after execution.

**Decision: RETAIN THE BOUNDED MEASUREMENT TOOL; DO NOT QUALIFY G5.** The original repeatability blocker is resolved **inside the declared envelope**. It does not demonstrate a faster general engine, strict immutable state-buffer publication, GPU-02 displayed FPS, sustained simulation, or a production-ready canonical scheduler. **No solver or runtime code is pushed** to GitHub by this documentation-only update.

**Next action:** Use the fixed-schedule measurement control to study one actual large-island **FP64 solver/color-pass work reduction** while reporting solver-only timings, iteration counts, matched correctness and exact arithmetic signatures. Separate deterministic schedule-building overhead from execution, avoid applying the serial O(C²) sorter to production, and stop if new arithmetic schedules or insufficient repeatability make a small claimed speedup inconclusive.

**Evidence:** User-uploaded `G5-Deterministic-Measurements-20261019.zip` with `source/`, `reference/`, `changes.patch`, `evidence/current-batch/results.json`, `summary.csv`, full raw exports, two explicit rejection proofs, output/shader hashes, test logs, and prior-handoff hash reconciliation. The GPU run occurred on the recorded Windows machine and was **not independently rerun** for this documentation review.

### G5 post-color device-barrier coalescing — REJECT (2026-10-19)

**Experiment and source:** Local branch `g5-color-boundary-measurement-20261019`, revision `960722f7351d691f8d33b2ef627365d8c1a9d01b`. An opt-in compile flag `G5_COALESCE_COLOR_BARRIER=1` omitted the **outer** `DeviceMemoryBarrierWithGroupSync()` after a complete color pass and after mandatory reconstruction, **only for a nonempty global-memory island**. The final nonempty color's final batch already uses a device/group barrier in `applyColor()`. Local-storage islands (`localMode==1`) and zero-color islands kept the outer device barrier. The intent was to avoid **two redundant outer device/group barriers per solver iteration** without changing the final color's existing device/group synchronization. The patch changes the barrier boundary around the loop, not the FP64 contact equations, normal/tangent projection, KKT scan, iteration budget or relaxation/restart logic.

**Existing baseline:** The retained source is still SHA-256 `10c5ee6541c7799119a9578b304c51f8d3de3938e2221613894bc7fae75d5c24`, and the exact tested candidate source is `f78f5a2232e0808d3aba58ab0e91e929a29410ee7b1c98f2200a4104effb2f2d`. Candidate and control variants were built for all policies 0–4, with `G5_BODY_CACHE=0`, `G5_REUSE_MEASURE_BODIES=1`, `G5_SKIP_OVERWRITTEN_RESIDUAL=1`, and the previously rejected `G5_EARLY_RESIDUAL_RESTART=0`. Test-only canonical contact scheduling remained on; ordinary default production policy is still 1 with deterministic measurement off. Disassembled candidate and control policy-4 `ph_solve` contain **20 static barrier instruction sites** each: the change alters which branch executes a barrier, not the static DXIL site count. Static/source-derived execution counts are **not** measured GPU stall or cache counters.

**Recorded headless test:** One serialized Windows CLI batch on **NVIDIA GeForce RTX 4070 Ti SUPER** ran **240 single-tick trials**: eight *paired* control/candidate policy-4 samples for each of ten frozen fixtures (**160** runs), plus one matched pair for each of four other solver policies per fixture (**80** runs). Per arm, **115 converged** and **five expected PGS/original-adaptive attempts rejected**. All **230 accepted** trial records passed independent invariant audits; all **ten rejected** trial records verified rollback. Each paired policy/fixture preserved the exact contact set, colored stream, arithmetic schedule, iteration count, FP64 work/impulse values and final published-state signature. The recorded preflight had **46 passing unit checks**; after restoring the baseline, **49 unit tests passed**. The targeted test intended to reject the pre-change source also failed as expected before the candidate patch, and that log is retained. No GPU run was performed during this documentation update.

| Deterministic policy-4 fixture | Solver p50 control → candidate | Complete tick p50 control → candidate | Iterations |
|---|---:|---:|---:|
| Chain 64 | 2.322 → 2.104 ms | 3.264 → 3.268 ms | 367 |
| Chain 256 | 32.021 → 32.117 ms | 35.689 → 35.195 ms | 4,035 |
| **Chain 1,024** | **147.503 → 143.696 ms** | **193.720 → 191.815 ms** | **4,024** |
| Dense 256 | 6.819 → 7.053 ms | 20.619 → 17.036 ms | 417 |
| Oblique/friction 256 | 25.328 → 25.323 ms | 36.261 → 40.172 ms | 1,016 |

**Predeclared retention test:** The 1,024-body policy-4 *solver-stage paired geometric* ratio is **0.98847**, with 95% paired-bootstrap interval **[0.97077, 1.00718]**. The medians above give a nominal 2.6% solver-stage improvement, but the same-batch control A/A p95 deviation/noise floor is **4.3576%** and the interval includes no improvement. The required gain `>max(3.6%, A/A noise floor)` was **not met**. Across all ten policy-4 fixtures, the equal-fixture complete-GPU-tick aggregate ratio is **0.9981204** with 95% interval **[0.9717317, 1.0254798]**; the aggregate interval is not fully below 1, so the second performance gate **also fails**. Complete-tick changes include ~45 ms of test-only deterministic scheduling on the 1,024-body chain, and its scheduling bracket is not an independent sorting-only hardware cost. Eight paired cold samples per policy-4 fixture support only this limited noisy comparison—not stable p99, sustained simulation, or a universal speedup.

**Independent archive checks:** Uploaded `G5-Deterministic-Solver-Work-20261019.zip` contains **1,985 ZIP members** (including `manifest.json`) and **1,984** per-file SHA-256 entries; all matched. ZIP CRC passed. All ten summary rows' recorded control/candidate GPU-tick and solver medians were recalculated from the corresponding eight raw runs and matched. The manifest, source diff and `restoration.json` identify the correct retained-versus-executed shader copies. Compiled binaries and build caches are not included, so this is evidence of a recorded Windows test, not independently rerun GPU qualification.

**Decision: REJECT AND RESTORE.** The candidate is correct in the recorded deterministic measurement envelope but cannot meet the predeclared noise-aware performance criteria. The archive confirms the active retained shader was restored byte-for-byte to SHA-256 `10c5ee6541c7799119a9578b304c51f8d3de3938e2221613894bc7fae75d5c24`. Neither the original working tree nor the production solver's settings changed; G5 remains **NOT QUALIFIED**, GPU-02 displayed-frame validation remains unverified, and G6 is unauthorized. **No experimental solver source is committed to GitHub** by this documentation checkpoint.

**Next action:** Stop barrier coalescing experiments. Inspect repeated *contact-local FP64 body loads* in `applyColor()` while preserving the updated normal-impulse state used for subsequent tangential projection. Make one narrowly justified correctness-first change only if data dependencies permit it. Use identical deterministic contact schedules, a matched paired control and candidate, and a noise-aware full-tick/solver criterion in one bounded headless batch. Reject if the change is not clearly measurable or changes exact FP64 acceptance/rollback.

### G5 contact-local FP64 body snapshot reuse — REJECT (2026-10-19)

**Hypothesis and source:** A new, opt-in HLSL `G5_CONTACT_SNAPSHOT=1` path loads both bodies once per contact into lane-private `Body` structures instead of repeatedly calling `relative()` and `delta()` in the normal and tangential impulse phases. In `applySnapshotContact()`, the normal impulse is projected and applied first; `deltaSnapshot()` mutates the same local `Body a/b` values **and preserves the original ordered body stores and wake operations**, then the tangent impulse reads that **updated** local state and uses the same Coulomb constraint. Conflict-free contact colors ensure no other lane writes either body during that color. Rebuild, other color passes, FP64 arithmetic, contact equations, barriers, KKT acceptance, energy/momentum bounds, solver policies, rollback and iteration/work caps are unchanged. The previously rejected early-restart and post-color-barrier modifications were **not** reapplied.

**Compile-mode and SHA evidence:** The experimental macro defaults **off** (`G5_CONTACT_SNAPSHOT=0`) and was toggled through separately compiled candidate/control policy 0–4 shaders. The exact tested candidate `projected_solver.hlsl` has SHA-256 `49067a3ed2cc01fad8c0a5ef77ae8b97a1a2dbe0748736a6a3334dbd6e2d66d3`. The exact retained/current solver and archived unchanged control both match SHA-256 `10c5ee6541c7799119a9578b304c51f8d3de3938e2221613894bc7fae75d5c24` byte-for-byte. Static disassembly of policy-4 `ph_solve` reports **191 → 160** buffer-load **instruction sites**; **153 FP64 arithmetic sites** and **20 barrier sites** remain unchanged. These site counts are **not** measured physical GPU memory transactions, bandwidth, occupancy, or execution stalls. The source uses legacy `bufferLoad`; `rawBufferLoad` zero counts in the preliminary DXIL script do **not** mean the shader performs no reads.

**Matched Windows headless evidence:** An isolated Windows GPU batch ran **240 cold one-tick trials**: eight matched, AB/BA policy-4 control/candidate pairs for each of ten frozen chain/branching/dense/oblique fixtures (**160** trials) plus one control/candidate pair per fixture for each of policies 0–3 (**80** trials). Recorded GPU: NVIDIA GeForce RTX 4070 Ti SUPER. **Per arm, 115 converged and five expected PGS/original-adaptive cases rejected.** All **230** accepted trials verified the invariant/KKT/impulse reconstruction/energy/momentum checks, while all **ten** rejected trials verified exact rollback; no timeouts or runtime errors were reported. All 50 policy/fixture comparisons have **identical** contact/color/arithmetic/dispatch schedules, iterations, FP64 work-state, contact impulses and accepted published-state hashes. All **ten** summary rows' medians were independently recomputed from underlying timing runs, with no mismatches. Recorded preflight: **46 passing tests**; post-restoration baseline: **49 passing tests**. These are related test suites, not 95 independent coverage areas. Windows GPU execution was **not independently rerun** by this documentation reviewer.

| Policy-4 deterministic fixture | Solver GPU p50 control → candidate | Complete GPU tick p50 control → candidate | Iterations |
|---|---:|---:|---:|
| Chain, 16 bodies | 2.742 → 2.502 ms | 3.150 → 2.919 ms | 452 |
| Chain, 64 bodies | 2.224 → 2.304 ms | 3.135 → 3.001 ms | 367 |
| Chain, 256 bodies | 32.037 → 31.550 ms | 35.633 → 35.120 ms | 4,035 |
| **Chain, 1,024 bodies** | **142.926 → 138.685 ms** | **192.734 → 189.745 ms** | **4,024** |
| Oblique/friction, 256 bodies | 25.352 → 24.354 ms | 38.907 → 33.531 ms | 1,016 |

**Uncertainty-aware decision:** The chain-1,024 paired geometric solver ratio is **0.97490945** (nominal 2.51% gain by paired ratio, versus 2.97% reduction in unpaired medians), with paired-bootstrap 95% interval **[0.94898109, 1.00295631]**. The same-batch control A/A p95 deviation/noise floor is **5.3183%**, greater than both the nominal and paired gains and the historical 4.3576% minimum. The primary predeclared rule requires the solver gain to exceed the larger floor **and** the 95% paired interval to be wholly below 1: **FAIL**. Across ten policy-4 fixtures, the geometric aggregate complete-tick ratio is **0.96623219**, 95% interval **[0.93714076, 0.99502117]**, which **passes the separate aggregate criterion**. The primary failure vetoes retention. The test-only deterministic schedule bracket on chain-1,024 was **45.850 → 46.994 ms**, and CPU record+submit median **3.505 → 3.516 ms**. Eight cold matched samples per fixture do not establish p99, sustained simulation speed, or cross-device reproducibility.

**Source integrity and GitHub history:** The user's `G5-FP64-Body-Loads-20261019.zip` passes ZIP CRC; **all 1,986 manifest-listed file SHA-256 hashes** match the archived bytes. The isolated experiment branch `g5-contact-snapshot-20261019` was already pushed to GitHub by the Windows Codex run at revision `fa4a11914879455cada2115e50d38d6936ab753a`; its architecture file is a local branch-specific report, **not** a replacement for the complete continuously updated `main`/playable records. The rejected candidate patch is archived on that branch but is **not merged** into the production branch. The archive reports original-workspace preservation for **394 checked files and unchanged working-tree status**. Its active retained shader and source hashes are verified offline here; there is no claim of a live Windows rebuild.

**Decision: REJECT / EXACT RESTORATION.** The contact-local snapshot is a correctness-preserving optimization **in the tested bounded deterministic envelope**, but its key 1,024-body solver gain cannot be distinguished from the measured A/A variation at the predefined threshold. The original solver source was restored byte-for-byte. Retain existing local `G5_REUSE_MEASURE_BODIES=1` and `G5_SKIP_OVERWRITTEN_RESIDUAL=1`; keep `G5_BODY_CACHE=0`, production relaxation policy **1**, opt-in policy **4**, and test-only deterministic scheduling **off** by default. G5 remains **NOT QUALIFIED**; G6 unauthorized and GPU-02 displayed FPS unverified.

**Next action:** Stop isolated low-single-digit load/barrier micro-optimizations. Use deterministic contact schedules to analyze the roughly **4,024 required iterations** on the 1,024-body connected chain: residual contraction, color-pass count and convergence bottleneck. Produce a source/trace-backed choice of **one topology-independent algorithmic approach** to reduce required solver work, with a carefully defined correctness contract, and test it against matched native/control builds only after the hypothesis is justified. Keep the serial deterministic scheduler measurement-only and account for its overhead separately. Do not weaken KKT, energy/momentum, rollback, or contact coverage.

**Evidence:** `G5-FP64-Body-Loads-20261019.zip`: `README.txt`, `manifest.json`, retained/experimental HLSL sources and patch, `evidence/results.json`, `summary.csv`, complete 240-trial exports, DXIL analysis, build/test logs, restoration checks, and GitHub push/verification logs. Results reflect one recorded serialized Windows GPU batch; they are **not** GitHub CI or an independently rerun qualification.

### G5 bounded Anderson convergence experiment — REJECT / CURRENT SPRINT CLOSED (2026-10-19)

**Cause analysis:** The tested 1,024-body collinear, unit-inverse-mass chain has 1,023 adjacent normal constraints. Its settled linearized normal operator is `tridiag(-1,2,-1)`, with condition number approximately **424,971**. The measured post-restart residual envelope for deterministic policy 4 decays by about **0.99500435 per sweep**, consistent with the retained fixed-SOR damping near 0.995; the control requires **4,024 sweeps** (512 adaptive plus ~3,512 fixed-SOR). This is a **fixture-specific linearized explanation**, not proof that frictional contact networks with changing active sets follow the same operator. Optimizing FP64 loads, residual scans or barriers alone cannot remove this long-range coupling.

**Tested change:** An opt-in, depth-one safeguarded Anderson extrapolation on the existing eight-sweep impulse map. The trial limits acceleration coefficients, projects impulses, requires a reconstructed KKT check, restores checkpoints on rejected attempts, resets history, and charges scans/trials against the **existing** work cap. The implementation uses checked, arena-backed scratch of **48 bytes/contact**, up to **64** trials, no new scheduler or GPU allocation. Sleeping/insufficient-capacity fallback source guards were **not** separately GPU-qualified. This is an algorithmic candidate, not a new default.

**Recorded Windows evidence:** `G5-Algorithmic-Convergence-20261019.zip` from local revision `a147f6bf265bc82060107358cd41157e38d371c2` on pushed **evidence branch** `g5-convergence-anderson-20261019`. The archive passed ZIP CRC and all **2,159** listed SHA-256 checks. It contains **240 serialized one-tick GPU trials** (ten existing fixtures × policies 0–4 × matched control/candidate; eight samples/arm for policy 4 and one sample/arm for each other policy) plus **20** deterministic residual probes. The independent acceptance and rollback flags were recorded; the control had **115 accepted / five expected rejected**, while the candidate had **93 accepted / 27 rejected**. Its **22 extra rejected trials** represent **eight distinct previously converging topology/policy configurations**, not 22 unrelated configurations. All rejected attempts verified rollback; all accepted attempts passed the recorded invariant audits. Baseline preflight **46** and restored-baseline **49** unit tests passed. The Windows GPU commands were not rerun during this documentation review.

| Policy-4 deterministic fixture | Baseline sweeps | Candidate sweeps | Candidate outcome |
|---|---:|---:|---|
| Chain 16 | 452 | 65 | Accepted |
| Chain 64 | 367 | 664 | Accepted, more work |
| Chain 256 | 4,035 | 3,397 | **REJECTED** |
| Chain 1,024 | 4,024 | 3,445 | **REJECTED** |
| Branching 256 | 1,194 | 357 | Accepted |
| Dense 256 | 417 | 64 | Accepted |
| Oblique/friction 256 | 1,016 | 235 | Accepted |

The two hard-chain rejected cases spent another ~699/651 units of charged trial work, respectively. On chain-1,024, reconstructed terminal KKT ratio increased **0.9830 → 107.98**. The nominal policy-4 solver/tick timing **143.393/193.555 → 130.096/178.800 ms** belongs to a **rejected attempt**, cannot be reported as simulation acceleration, and must not be counted as a qualified performance gain. Attempted-tick aggregate statistics likewise include rejected runs and are **not valid qualified throughput comparisons**. The candidate loses convergence for chain-64 policies 1 and 3, chain-256 policies 1/3/4 and chain-1,024 policies 1/3/4.

**Decision: REJECT AND RESTORE.** The tested `projected_solver.hlsl` SHA-256 is `53e7957940c76790a4d00b943b1c05c6acd662ebe0445858e3e7f70bb93bae7e`; the exact retained shader SHA-256 is `10c5ee6541c7799119a9578b304c51f8d3de3938e2221613894bc7fae75d5c24`. The handoff's preservation record reports the latter restored byte-for-byte, with production relaxation **policy 1**, prior retained local snapshot-reuse/skip-overwritten-residual logic, body cache off and test-only deterministic scheduler off by default. The experimental branch was pushed but not merged into `main` or the playable branch. G5 did **not** pass its large-island convergence or performance gate.

**Project-level disposition — CLOSE THE CURRENT G5 WORKSTREAM AS DEFERRED, NOT PASSED:** Stop repeated G5 micro-optimization and acceleration experiments. Preserve the baseline, the rejected-candidate evidence, the quick fixture/correctness tests, and the risk description. Mark G5 **DEFERRED / NOT QUALIFIED** in the gate table. This is an explicit scheduling/priority decision, **not** a technical pass, a waiver of the large-island limitation, a full-engine release approval, or evidence of sustained 1,024-body real-time physics.

**Proceed independently where safe:** Work may continue on resource planning, state isolation, scheduler/host interfaces, smaller/scattered-island workloads, error handling and headless coverage **without claiming that G5-dependent acceptance criteria are satisfied**. G6 **preparation and scope definition** are permitted, but **formal G6 foundation approval remains unauthorized** until its relevant technical gates pass or an explicit, separately approved scope/risk-acceptance decision is documented.

**Reopen G5 only when:** (a) a representative application scenario actually requires the large-connected-island target, or (b) an evidence-backed architecture change offers a material improvement worth a dedicated prototype; set explicit target latency/throughput and acceptable failure handling first. Explore multilevel/global low-mode correction, a domain-decomposed or parallel solver, or an alternative constraint formulation **as separate proposals**, not as automatic follow-on benchmark loops. Preserve correctness, KKT, rollback, multi-island generality and full-tick cost accounting.

### G6-P1 immutable consumer-state publication — LOCAL PREPARATION PASS (2026-10-19)

**Implementation / provenance:** User-supplied `G6-P1-State-Isolation-20261019.zip`, local implementation revision `603fd67506ede889bf6c7bc4b9cd034183d97ccb`, branch [`g6-p1-state-isolation-20261019`](https://github.com/Cryosimorgh/GPU-physics-engine/tree/g6-p1-state-isolation-20261019), base `a147f6bf265bc82060107358cd41157e38d371c2`. New `state-publication.h/.inc`, `publication-runtime.inc`, and bounded changes to physics/runtime/viewer/CLI tests. The experiment **is committed on a separate branch**, not merged to `main` or the playable branch. The original working tree and its three dirty compiled artifacts remain unchanged according to the handoff receipts. **G5 remains DEFERRED / NOT QUALIFIED; G6 formal approval remains NOT QUALIFIED.**

**State lifecycle and invariants:**

1. The legacy G1 source/identity buffers are **producer-private borrows**, not stable immutable consumer leases. The existing trial, discovery, contact, solver, GPU guards, and `ph_publish` path continue to run in their original sequence. After publication, a GPU copy captures 64 bytes/capacity body components, a 256-byte header, 12 bytes/capacity identity maps, and, for fixture 13, 160 bytes of persistent pool material/rolling state into a **separate immutable GPU buffer**. No trial scratch is exposed.
2. The writer selects a free publication slot that is neither currently accepted, reader-pinned, pending, nor fence-incomplete. GPU copies and transitions to COMMON are ordered in the compute queue, then fenced. The CPU marks the new slot accepted only after the terminal GPU fence and completed-frame acceptance header agree on error state, tick, epoch and body count. Rejected solver states do not displace the last accepted snapshot. Failed completion poisons the Physics instance rather than silently publishing.
3. Every consumer obtains a read-only `PhStateLease` carrying runtime/context identity, nonwrapping publication serial, unique nonce, generation, tick/epoch, buffer and readiness fence. A 64-entry table checks the exact handle and refuses stale/forged/double releases. Any asynchronous GPU consumer must register **its completion fence before submitting commands**; the lease cannot release until that fence signals. A CPU-only holder may release after CPU use; raw legacy source handles are never permanent GPU leases. The owner-thread API is **serialized**, not a thread-safe concurrent host interface.
4. Two slots are pre-admitted by default; explicit reserve allows up to four. If no slot is free, the candidate returns bounded **error 60** *before* advancing the simulation tick or overwriting accepted state. No implicit eviction or allocation during normal ticks. Destroying Physics with live leases is refused; closing Storage with live Physics owners is refused. Structural mutation requires drained producer work and no live leases. Runtime identity and fence ownership checks block stale contexts and foreign-device use.
5. Injected GPU command-recording failure restores resource-state bookkeeping and discards an unsubmitted packet; previously submitted split packets retain their fence ownership. This is **not** a demonstrated physical dispatch/device-loss recovery. Native D3D12 `ID3D12Device` objects were **shared** between test runtime instances despite distinct StorageDevice identities; cross-physical-device cases remain untested.
6. Existing viewer legacy source reading retains same-queue graphics/compute synchronization and fenced per-frame copies; the candidate viewer source was **compiled but not launched**. No networking consumer is currently implemented. The lease mechanism is not proof that all future consumers are correctly integrated.

**Verification:** One final serialized Windows `python run_g6_p1.py` batch recorded **21/21 PASS processes**, including publication, regression (idle, collisions, energy, discovery, ownership), device identity, recycling/delete, and twelve AB/BA workload timing processes. GPU errors reported by the final tests: **zero D3D12 validation errors**. The handoff also archives earlier preflight/fence-harness failures separately; they are not counted as passing results. The supplied ZIP passed CRC and all **422 manifest-listed SHA-256 file checks**. Candidate/source artifacts in the uploaded ZIP match the separately pushed implementation branch. Shader sources and **all candidate/control DXIL shader outputs** are recorded unchanged, including the retained `projected_solver.hlsl` SHA-256 `10c5ee6541c7799119a9578b304c51f8d3de3938e2221613894bc7fae75d5c24`. This is **recorded Windows GPU evidence, not independently rerun testing or GitHub CI**.

**Bounded overhead:** Each committed immutable publication slot reserves `76*C + 256 + (fixture13 ? 160 : 0)` logical bytes, aligned using the D3D12 allocation info. At capacity **C=32**, two default slots add **131,072 bytes (128 KiB)** of committed GPU allocation, with **zero normal-tick slot allocations**, **zero additional CPU uploads**, and **zero additional per-tick GPU-to-CPU readback bytes**. The per-tick GPU copies of accepted state are **not zero**; they are approximately `76*C + 256` bytes plus the optional 160 bytes for pool state. For an idle workload, the logged 64 warm samples per arm (two 32-sample AB/BA repeat blocks) give total GPU tick **p50 262 → 263.75 μs**, **p95 265 → 267 μs**, and CPU record + queue-submit p50 **212.5 → 213.5 μs**. The publication-tail reported median is **3 → 5 μs**. Moving p50 remains approximately **398 → 398.5 μs**. No sustained, p99, heterogeneous workload, or broad throughput guarantee is established.

**Timing accounting caution:** The reported `break` p50 (control **856 μs**, candidate **761 μs**) does not agree with a direct recomputation of pooled 64 raw trials using the *last* exported `gpu_cumulative_us` timestamp (approximately **863.5 μs** control, **808.25 μs** candidate). The CLI's reported timing definition and last cumulative timestamp may differ, but the archive does not establish the reason. **Do not use this discrepancy to claim a solver speedup** or a reliable break-case gain; reconcile timestamp accounting before a performance gate.

**Disposition: RETAIN AS G6-P1 LOCAL PREPARATION PASS, NOT G6 GATE QUALIFICATION.** Immutable accepted generations now have a bounded, explicitly fenced consumer API within the tested owner-thread contract. However, real hardware dispatch failure, physical device removal/recovery, true cross-native-device safety, full viewer lifecycle, consumer API integration outside the tests, and sustained execution remain **UNVERIFIED**. Do not promote this branch as an approved engine foundation, and do not reactivate G5.

**Next action:** Establish a small, bounded G6-P2 resource/scheduler and consumer-integration contract around the new lease API: explicit resource admission and ownership, per-queue completion handoff, backpressure, error propagation, and a headless real consumer scenario. Start with an audit; avoid a wholesale scheduler rewrite. Track the distinct native-device/unverified device-loss boundary. Keep graphical or network integration claims unqualified without actual end-to-end evidence.

### G6-P2 resource ownership and bounded task dependencies — LOCAL PREPARATION PASS (2026-10-19)

**Scope and implementation:** The user-uploaded `G6-P2-Resource-Ownership-20261019.zip` contains an isolated Windows implementation at revision `7fdd05e38acfe04c264997f880a665f48affe799`, branch [`g6-p2-resource-ownership-20261019`](https://github.com/Cryosimorgh/GPU-physics-engine/tree/g6-p2-resource-ownership-20261019), based on G6-P1 revision `603fd67506ede889bf6c7bc4b9cd034183d97ccb`. The branch is **not merged** into `main` or `billiards-playable-requalification-20261018`. New `work-ownership.h/.inc`, `resource-claims.inc`, headless ownership tests and bounded updates to the P1 physics/runtime/publication interfaces implement **resource admission and completion tracking on existing D3D12 queues and snapshot leases**. There is **no new general-purpose task scheduler**, solver modification, normal-tick GPU allocation, or added per-tick CPU readback/wait.

**Resource and task contract:** Each consumer task owns a P1 immutable accepted-state read lease plus **at most three additional resources**, declared with exclusive-write/shared-read access. The resource ledger checks buffer validity, retirement/transition conflict, outstanding writer/reader claims, and external resource availability; partially acquired claims unwind on admission failure. Producer work exposes up to **32 explicit resource dependencies** with queue/fence and publication-generation provenance. A fixed **64-entry lease/task table** admits requests without hidden task eviction or new GPU allocations. The CPU API is **owner-thread serialized**, not a general concurrent host scheduler. Both producer and consumer work retain resource claims/immutable state until their respective recorded completion fences allow safe release. Buffer retirement and conflicting state changes are blocked while claimed.

**Submission and cancellation:** Consumer submission retains a queue only when it belongs to the expected native D3D12 device, validates the future external completion fence and registers it **before externally submitted work**. A duplicate, already signaled, or foreign-device fence cannot silently acquire ownership. Pre-submit cancellation/failure releases claims immediately. After submission, `cancel` and `fail` mark work pending and **do not preempt GPU commands** or release the consumer snapshot/output until the completion fence signals. Stale task handles and cross-context references fail. Producer failure preserves existing published generations and consumer ownership. No assumption is made that this protects arbitrary shaders which bypass the declared resource dependencies.

**Final headless evidence:** A serialized `python run_g6_p2.py` Windows batch recorded **22/22 PASS process runs**, all return codes zero, on the existing device/driver with **zero reported D3D12 debug validation errors**. Coverage includes read/write resource conflicts, shared readers, immutable snapshot write rejection, native copy-queue consumer overlap, delayed consumer fences, pre- and post-submit cancellation, queued failure cleanup, slot/task exhaustion, claim rollback, stale/context handles, producer failure, ordinary physics regressions, memory and timing scripts. The test suite covers **one producer and bounded GPU consumers**, not arbitrary multi-device producers, custom untrusted shader access, or a real application/network consumer. The viewer was **compiled successfully but not launched**. The failed initial attempt used the wrong memory-probe warmup setting; `initial-attempt/` keeps that history, and the corrected **final** evidence is in `evidence/g6-p2/results.json`.

**Audit and source integrity:** The archive's CRC is valid, and all **252** `manifest.json` file SHA-256 entries match the ZIP contents. The uploaded handoff's `changes/` source snapshots match their manifest source hashes, and the core `work-ownership.inc`, `resource-claims.inc`, and `runtime.c` are available on the pushed isolated branch. The final `gate-G6-P2.json` states G5 remains deferred and G6 unqualified; all baseline and candidate DXIL shader hashes match, including unchanged `projected_solver.hlsl` and `physics.hlsl`. Original P1 workspace preservation of **327 tracked file hashes** and the four pre-existing dirty build outputs is reported by the local Windows handoff, not independently established on the remote machine. This review checked local archive records; it did **not** rerun Windows GPU execution.

| Measured headless fixture (64 warm samples per arm; two repeated AB/BA blocks) | P1 control | G6-P2 candidate |
|---|---:|---:|
| Idle complete GPU tick p50 / p95 | 266.75 / 269 μs | 266.5 / 269.5 μs |
| Moving-contact GPU tick p50 / p95 | 406.75 / 408.5 μs | 406.75 / 409.75 μs |
| Idle CPU record + submit p50 | 217.5 μs | 213.6 μs |
| Moving CPU record + submit p50 | 240.1 μs | 242.7 μs |
| GPU allocations | 23 | 23 |
| GPU committed bytes | 1,507,328 | 1,507,328 |

**Performance interpretation:** These bounded comparisons show no material added GPU memory or complete-tick time in the tested 32-body workflows; they **do not** demonstrate a throughput improvement, device-loss recovery, or sustained tail latency. No added GPU allocations/committed memory were observed even on task exhaustion. The third `break` workload is explicitly **excluded** from performance conclusions: `p1-break-audit.json` reproduces historical printed quantiles from the raw samples, and the new batch satisfies timestamp ordering, but an unexplained approximately **95 μs** execution-time mode shift remains. This is an attribution problem, not evidence of failed ownership correctness.

**Decision: RETAIN P2 ON THE ISOLATED DEVELOPMENT BRANCH; FORMAL G6 NOT QUALIFIED.** Safe bounded task/resource ownership has passed the recorded local envelope. The work is **not** proof of physical device removal/recovery, arbitrary user-written shader resource safety, multi-producer/multi-device scheduling, live viewer/network integration, formal GPU-02 displayed FPS, or universal engine foundation readiness. G5 stays **DEFERRED / NOT QUALIFIED**, and G6 may continue independent preparation without waiving those gates.

**Next action:** In G6-P3, integrate one **real native application consumer** of accepted GPU snapshots (the existing renderer is preferred), using the P1/P2 lease/task contract with explicit producer→consumer queue wait and registered completion fence, and verify its lifecycle through a bounded headless run. Make device-loss/teardown behavior explicit and test supported failure paths, but do **not** claim real physical device-loss recovery unless an actual removal/recreation test completes. Do not create a new scheduler or reopen G5.

### G6-P3 real application GPU renderer consumer — LOCAL PREPARATION PASS (2026-10-19)

**Implementation and provenance:** User-supplied `G6-P3-Real-Consumer-20261019.zip`, experiment revision `621f6d626cabd2ccf187db695b658f99a80c9586` on branch [`g6-p3-real-consumer-20261019`](https://github.com/Cryosimorgh/GPU-physics-engine/tree/g6-p3-real-consumer-20261019), based on G6-P2 `7fdd05e38acfe04c264997f880a665f48affe799`. `viewer.c`, `render-consumer.inc`, `state-publication.inc`, `work-ownership.inc/.h`, `render-consumer-tests.inc`, HLSL renderer/layout and pool snapshot schema were updated. The implementation is committed **only on the isolated branch**; the authoritative `main` and playable branches contain this documentation decision, **not** the P3 production source integration. G5 remains **DEFERRED / NOT QUALIFIED** and formal G6 approval remains **NOT QUALIFIED**.

**Actual application consumer:** The existing viewer `vrender()` and its real D3D12 pipeline states, resource bindings and `DrawInstanced` calls now use a G6-P1 immutable **accepted** state snapshot through G6-P2 `PhWorkHandle` dependency admission. The consumer acquires and pins an accepted generation, records bounded read/write dependencies, registers its graphics queue and future completion fence **before** external GPU execution, explicitly inserts `ID3D12CommandQueue_Wait` on the producer readiness fence, renders from leased state/body/map/header/persistent pool fields, and holds the lease/resources until graphics-fence completion. Delayed readers, cancellation and failure remain bounded; rejected unpublished generations cannot replace the last accepted one. The legacy fenced private-source copy route is kept only as a **matched test control**; normal intended renderer path is the lease-driven consumer.

**Correctness and scope:** The functional `render_consumer.exe --profile 13 --samples 0` invokes the actual application renderer and shows **495 pipeline vertex invocations**, nonzero pixel-shader activity, and **16 rendered instances per frame** with real D3D12 commands. Headless proof includes two-queue producer/consumer overlap, a blocked graphics fence, safe snapshot reuse, stale/failed task cleanup, bounded backpressure, poison of producer-private buffers while the accepted immutable generation remains readable, attempted rejected-tick withholding, pool snapshot bounds and pick/verification metadata. Pool-status source and snapshot offsets were corrected together; all **32 physics DXIL** control/candidate pairs are **byte-identical** and no solver mathematics, KKT limit, fixed timestep or production relaxation policy changed. This is **offscreen functional evidence**, not visual pixel-image correctness or live interactive presentation: no HWND, swap chain `Present`, screenshot/pixel readback or physical device-loss test ran. A synthetic rejected state and injected recording failure do not establish true device-removal recovery.

**Recorded test evidence:** The final one-batch Windows `python run_g6_p3.py` evidence lists **14/14 PASS serialized process runs**, including real renderer consumer, G6-P1/P2 publication and ownership regression tests, pool idle/contact/energy/discovery tests, paired 16-sample/arm render timing in each of two AB/BA blocks, and independent 32-body memory/control tests. The functional scenario enables D3D12 debug validation and records zero errors in related physics/publication/ownership checks; recorded per-render timing processes do not enable validation. The original workspace's **333 tracked file hashes and dirty status were reported unchanged**. ZIP CRC and **all 877** manifest-listed SHA-256 hashes were verified; changed source snapshots were checked against the source manifest. The pushed branch contains the new renderer integration. Windows GPU execution was **not independently rerun** in this review.

| Offscreen P2/control vs P3/candidate (32 samples/arm) | Control | Candidate |
|---|---:|---:|
| Graphics GPU render p50 / p95 | 18.432 / 18.848 μs | 18.432 / 19.456 μs |
| CPU record + submit p50 / p95 | 434.5 / 471.3 μs | 450.9 / 799.6 μs |
| CPU blocking acceptance wait p50 / p95 | 0 / 0.100 μs | **1,131.8 / 2,026.2 μs** |
| Complete GPU tick p50 / p95 | 1,259 / 1,690 μs | 1,174 / 1,870.25 μs |
| Offscreen total committed GPU allocation | 2,883,584 bytes | 2,686,976 bytes |
| Offscreen GPU allocation count | 42 | 39 |

**Performance interpretation:** Published p50 values use the **lower middle sample** of the 32 sorted samples, not the arithmetic average of the middle pair; this convention reproduces every reported CSV p50. The paired `control` adapter and `candidate` run the same real viewer rendering pipelines in offscreen mode but are **not byte-identical interactive runtime builds**; no throughput or frame-rate speedup is proven. Render GPU time remains about **18.4 μs**; memory is **196,608 bytes (192 KiB)** and **three allocations** lower in this specific offscreen comparison. The mandatory CPU-side accepted-state decode/check currently calls `gp_wait` before renderer submission and introduces a material **~1.13 ms median blocking wait**; it can limit overlap even though the graphics queue also has a GPU readiness wait. The full-tick p95 worsens and the timing sample distribution is wide. Avoid treating smaller p50 tick as an engine-performance gain. The previous P2 `break` fixture's unexplained ~95 μs time-mode discrepancy remains separate and unresolved.

**Resource contract correction needed:** P3 increases `PH_WORK_EXTRA` from **three to five** to cover actual renderer diagnostic/readback/timestamp/HUD/capture dependencies. The bounded CPU-owner-thread API still has 64 lease/task entries and 32 producer dependencies. The public `work-ownership.h` comment still says "*at most three separately owned resources*" and is **stale**; align it with the actual verified bound before any public API guarantee. The headless combination of capture plus pipeline stats is not admitted if it exceeds five extras, by design. This is not evidence of a general-purpose resource scheduler or arbitrary external-shader safety.

**Decision: RETAIN G6-P3 AS LOCAL PREPARATION PASS; DO NOT QUALIFY G6.** One genuine renderer consumer is now integrated and verified in a bounded offscreen application test. It establishes more than mocked ownership but does **not** prove interactive frame presentation, real screen scanout (GPU-02), pixel output, fully async nonblocking host rendering, physical device removal/recreation, long-run multi-consumer workloads, or a general released engine. G5 remains parked, and `G6_RENDER_LEGACY_CONTROL=1` remains a **test-only** comparison path.

**Next decision:** The most important demonstrated runtime bottleneck is the **host acceptance wait** before graphics submission; first determine whether ready accepted generations can be consumed without blocking the CPU while pending producer ticks are deferred, using only the existing fence/lease APIs. Keep rejected frames unpublished, preserve backpressure and last accepted visibility, and make no GPU solver/scheduler changes. Separately specify a bounded teardown and error policy for a truly removed D3D12 device; do not claim recovery without a real removal/recreation test. Close the stale `PH_WORK_EXTRA` API comment and report GPU/CPU latency, queue readiness and rollback in one headless matched test.

**Evidence:** `G6-P3-Real-Consumer-20261019.zip`; `DECISION.txt`, `REPRODUCE.txt`, `MANIFEST.json`, `changes.patch`, `changes/render-consumer.inc`, `changes/viewer.c`, `evidence/g6-p3/results.json`, `results.csv`, `gate-G6-P3.json`, raw offscreen timing samples, test logs and compiled D3D12/DXIL artifacts. Logged Windows results are evidence of a local developer run; this document-only update is not CI evidence.

### G6-P3 source integration with main — CONFLICTS RECONCILED / NOT A QUALIFICATION PASS (2026-10-19)

**Merge contract:** This source-integration merge joins the cumulative `g6-p3-real-consumer-20261019` development ancestry (which contains G6-P1, P2, P3 and the requalified billiards/playable source) with the separate documentation-only `main` history. The common ancestor was `4bfae94e41ccef6766a52d224a24eec907e2e378`. `main` had only three changed files since that ancestor: `README.md`, `AGENTS.md` and `docs/ENGINE_ARCHITECTURE.md`. No production C/HLSL/Zig source was independently edited on `main` since that ancestor. Therefore the exact G6-P3 code tree was preserved, with deliberate resolution of those three overlapping documentation paths.

**Conflict resolution:** Keep the current comprehensive `main` architecture record, including every G5 rejection and G6-P1/P2/P3 breakpoint; **do not replace it with the shorter stale architecture file on the G6 branch**. Keep the more complete playable/G6 development `README.md` (it already contains the link to the living architecture record from `main`) and the more detailed development `AGENTS.md`, which retains the mandatory documentation workflow and headless/short-test requirements. Correct only the stale `work-ownership.h` explanatory comment from “three” to “five” extra resources to match the already-tested `PH_WORK_EXTRA 5` contract. No solver or D3D12 behavior was modified in the conflict resolution.

**Version and status:** The merge includes historical experimental scripts and `experiments/g5-*.patch` records. Their presence **does not activate rejected solver experiments**. The restored production solver defaults remain policy 1, policy 4 opt-in; G5 is **DEFERRED / NOT QUALIFIED**. P1–P3 have bounded headless local evidence, **not** CI or formal G6 approval. The integration is a code/version-control consolidation, not a Windows GPU retest, device-recovery proof, physical displayed-FPS validation, or release candidate. Windows x64 D3D12 tests must be rerun on the actual integration head before claiming an integrated build is verified. The P3 host acceptance wait (~1.13 ms median), displayed GPU-02, real device-loss/recreation, and sustained workload coverage stay open.

**Repository hygiene after integration:** Compiled `.dxil` and `.exe`, historic release `.zip`, screenshots/videos and captured benchmark data are tracked across this historical tree. No binary was manually rewritten during this merge. Track generated/release artifacts deliberately and add a Windows CI sanity workflow in a separate scoped change, without deleting provenance evidence as part of conflict resolution.

### G6-P4 nonblocking accepted-generation rendering — LOCAL PREPARATION PASS (2026-10-19)

**Scope, version and integration:** User-uploaded `G6-P4-Nonblocking-Consumer-20261019.zip` was generated from local Windows commit `aa7d77cdfcef0efe777539aa876d2a5b05cb7ba3` on the independently pushed branch [`g6-p4-nonblocking-consumer-20261019`](https://github.com/Cryosimorgh/GPU-physics-engine/tree/g6-p4-nonblocking-consumer-20261019), based on the previously tested G6-P3 commit `621f6d626cabd2ccf187db695b658f99a80c9586`. This branch is **not merged** with `main` or the playable branch at this documentation checkpoint. Since P3, `main` integrated the earlier playable/P1–P3 source and underwent branch/history reconciliation in PRs #1/#2. **The P4 results come from the pre-integration P3 source lineage**; integrated-head source/Windows tests are still needed before promotion. The original workspace had **338 file hashes checked** and dirty working-tree status reportedly preserved. The authoritative living architecture history in `main` and playable must never be replaced by the shorter local branch copy.

**Behavior and contract:** The existing actual viewer `vrender()`, offscreen renderer and per-frame `vfinish()` are changed to allow *ordinary*, command-free frames to acquire the **latest already accepted immutable P1 snapshot** through P2 `PhWorkHandle` while a newer tick is being recorded, submitted, or awaiting validation. A graphics-queue wait on the snapshot's producer-ready fence and a registered graphics-completion fence still protect the consumer lease and resource claims; the newer producer's pending/failing generation is **not** bound for rendering. The newer tick is validated/decoded on ordered retirement, so failed ticks do not silently become accepted. User-input/command acknowledgment still takes the **matching-tick synchronous acceptance path**, preserving the command result contract. A bounded retirement/retry path handles resource error 60 (publication-slot exhaustion) before advancing an unsupported tick; failure/poison and draining semantics remain. The default nonblocking handoff is guarded by a test switch `G6_P3_BLOCKING_CONTROL=1` to compile a matched old-handshake comparison; P3's legacy renderer source-copy control remains a distinct test-only mode. This does **not** introduce a scheduler, extra GPU buffer, new CPU readback, different shader, or solver/relaxation change.

**Actual GPU correctness proof:** The archived `nonblocking-consumer-tests.inc` submits two real offscreen D3D12 renders while the **producer compute queue is held on a native test fence**, so neither newer physics fence has completed. Both renders successfully read the previously accepted generation **0**, have observed snapshot ages **one and two** ticks, and prove GPU draw work completes before the producer is released. The test also checks 64-task exhaustion, stale lease/handle rejection, blocked publication returning error **60** without advancing the tick, held immutable state across accepted later ticks, rejected generation withholding, delayed cancellation completion, and no memory allocation growth. The accompanying existing real renderer lifecycle test records **495 vertex shader invocations**, full 16-body coverage and zero reported D3D12 debug errors. No window, `Present`, image readback, actual physical device removal, or independent displayed-FPS verification was performed.

**Headless batch audit:** One final `python run_g6_p4.py` Windows batch reports **11 PASS records**: **six fresh process runs** (nonblocking, lifecycle and two AB/BA control/candidate render pairs) plus **five unchanged-binary reused tests** (publication, ownership, pool idle/collisions/energy), with original executable hashes and exact commands checked. Prior `harness-contract-failure/` logs show an obsolete test-driver assumption; it was corrected **before** the final timed batch and is not counted as a successful initial attempt. All **149** uploaded `MANIFEST.json` file SHA-256 entries match the archive, the ZIP CRC passes, and the included `verify_handoff.py` returned `PASS 149 payload hashes; no GPU work executed` on independent local verification. The archived executed driver hash, control/candidate EXE hashes and all **14** timing CSV summaries reconcile exactly against raw samples. No Windows GPU commands were rerun by this documentation review. The P4 branch comparison against P3 changes ten text/source files and **no** DXIL physics shaders.

| One offscreen 16-body workload, 32 samples per arm | Matched blocking P3 control | Nonblocking P4 |
|---|---:|---:|
| CPU acceptance wait p50 / p95 | 366.5 / 583.7 μs | **0 / 0 μs** |
| CPU total handoff p50 / p95 | 751.3 / 1,028.1 μs | **347.0 / 565.2 μs** |
| CPU record + submit p50 | 363.5 μs | 341.1 μs |
| GPU complete physics tick p50 / p95 | 602.5 / 801.75 μs | **786.5 / 873.75 μs** |
| GPU render p50 / p95 | 16.384 / 16.448 μs | **22.528 / 25.6 μs** |
| Accepted snapshot age p50 / p95 | 0 / 0 ticks | **1 / 1 tick** |
| GPU allocations / committed bytes | 39 / 2,686,976 | 39 / 2,686,976 |

**Measurement interpretation and tradeoff:** These are same-batch controls with the common `G6_P3_BLOCKING_CONTROL` instrumentation, **not** a byte-identical recreation of the preceding P3 handoff's historical **1.13-ms** acceptance-wait measurement. Report this batch's **366.5 μs → 0** improvement, not an invented paired 1.13-ms → 0 result. p50 is the **lower middle** of 32 sorted samples; p95 is the empirical nearest rank; raw samples reconcile with all 14 rows and recorded maxima. The `retirement_blocking_us` column (366.6 → 431.7 μs p50) measures an **inclusive existing frame-backpressure field**, not strictly delayed-retirement blocking. Deferred work still stalls on fence/slot reuse when necessary; the GPU physics and rendering p50 and p95 **increase** in the candidate. GPU queue overlap could contribute to wider intervals, but **hardware-level cause is unproven**; there is **no demonstrated overall throughput or FPS speedup**. The one-tick steady-state snapshot age is **7.8125 ms of simulated time** at the fixed 128-Hz step; it is **not measured display latency**, and the deliberately stalled producer observed two ticks. Performance envelopes, buffering/backpressure and visual freshness must be chosen together.

**Decision: RETAIN G6-P4 AS LOCAL CORRECTNESS/CPU-LATENCY PREPARATION PASS, NOT A FULL ENGINE PERFORMANCE PASS.** The tested nonblocking handoff safely uses previously accepted state and removes synchronous acceptance waits in normal command-free submissions while preserving the matching-tick command acknowledgment contract. However the GPU tick/render regressions, one-tick freshness tradeoff, limited 16-body offscreen test, unexplained P2 break-mode timing shift, no post-merge integrated Windows verification, actual physical device-loss and interactive GPU-02 remain open. The original G5 gate stays **DEFERRED / NOT QUALIFIED** and G6 **NOT QUALIFIED**. Keep the P4 code isolated until integrated behavior is validated; do **not** silently replace the production renderer, widen G6 release claims, or resume G5.

**Next action:** Confirm the P4 change applies cleanly to the **newly merged integrated head**, preserve current `docs/ENGINE_ARCHITECTURE.md` and both branch ancestries, run one focused Windows real offscreen consumer plus physics/ownership regression check there, and report measured CPU/GPU/age tradeoffs. After that, address **bounded device-loss detection, teardown, invalid lease/queue cleanup and explicit reinitialization limits** as a separate G6 preparation checkpoint. Injected errors may validate the software failure paths; only real device removal and re-creation tests can qualify physical recovery. No viewer screenshots, mass benchmarking, speculative scheduler or FP64 solver experiments.

**Evidence:** `G6-P4-Nonblocking-Consumer-20261019.zip`, `DECISION.txt`, `REPRODUCE.txt`, `MANIFEST.json`, `changes.patch`, `changes/{viewer.c,render-consumer.inc,nonblocking-consumer-tests.inc,...}`, `evidence/g6-p4/{results.json,results.csv,nonblocking.json,gate-G6-P4.json}`, archived logs, DXIL and candidate/control executable hashes.

## 9. Global time, sleeping, and simulation state

**Code:** `physics.c`, `physics.hlsl`, `viewer.c`.

The simulation uses one global fixed timestep. The controlled physics fixtures use **1/128 second**. The rendering rate can differ from the physics rate. Sleeping means that some work can be skipped; it must **not** give an entity its own simulation clock.

The intended state contract is:

1. Read the completed state `S(t)`.
2. Apply user commands at the tick boundary.
3. Calculate a provisional next state in scratch storage.
4. Detect and solve contacts using ordered GPU passes.
5. Run global validation and guard checks.
6. Publish only the accepted `S(t+1)` generation.
7. Allow rendering to consume a completed, versioned generation.

**Current qualification:** The code has separate passes, a provisional trial buffer, validation checks, and generation diagnostics. However, G4 still publishes into the original source buffer per body after validation. A full immutable-source and atomic-generation-swap implementation is **not yet proven**. This is a required production gate, not an optional style change.

The project tests rejected ticks and rollback behavior. A rejected attempted state must not be called a completed simulation result.

## 10. Fast paths and GPU-driven work control — later local experiments

A sequence of local experiments reduced the reported headless 16-ball idle tick from roughly **669 µs to 249–251 µs**. The improvements include:

- Skip costly square roots for pairs that are clearly too far apart, while keeping precise checks close to contact.
- Use GPU-side predication to bypass graph and solver work when no work is required.
- Stop redundant discovery rounds when the previous GPU result proves no more rounds are needed.
- Reduce the number of CPU command-list submissions for the idle path.

These figures are **headless, workload-specific handoff measurements**. They are not the same measurement as the graphics viewer's complete frame time. They are also not evidence of faster active large-island solving.

**Innovation / value:** GPU-side decisions reduce both wasted GPU passes and CPU synchronization. The engine can leave the state on the GPU and still avoid unnecessary work. Predication and early termination must preserve wake-up, the first new contact, error flags, and validation.

## 11. Rendering, presentation, and interactive use — G4

**Code:** `viewer.c`, `render.hlsl`, `hud.hlsl`; on the playable branch also `play_ui.cpp`, `playground_view.inc`, `pool.hlsl`.

The viewer draws GPU-resident positions without reading back all entity coordinates. It supports one to three frames in flight. The render path can consume a protected snapshot. Swap-chain, queue, and fence ownership control when graphics resources can be reused.

The G4 demonstration draws two-dimensional disks as shaded sphere impostors. On large overview scenes, it may render **at most 50,000 samples** while the GPU still simulates all entities. Rendered instance count and simulated entity count are separate metrics.

The later playable branch adds a 16-ball pool scene, cue input, physical rail and cloth parameters, and live telemetry. It is a **planar billiards approximation**; pockets, scoring, elevated cue strikes, and full 3D ball dynamics are not qualified features.

**Historical G4 mixed-billiards measurements:** 10K bodies about **1.85 ms**, 100K about **5.47 ms**, and 1M about **43.71 ms** per physics tick (reported p50 in the G4 handoff). These figures cannot be compared directly to the synthetic G1/G2 kernels or to later playable-pool frames.

The distinction between metrics matters:

| Metric | What it measures |
|---|---|
| Physics ticks per second | Accepted global simulation steps per second. |
| GPU physics time | GPU timestamps around defined physics work. |
| CPU record/submit time | Host work to build and submit GPU commands. |
| Render FPS / Present calls | Application rendering or presentation activity. |
| Physical displayed FPS and scanout delay | Display-system evidence, which can be unavailable in RDP. |

**G4 status:** Conditionally accepted for scoped simulation/render execution. Formal physical-display correlation (**GPU-02**) remains **unverified** unless a local trace closes it.

## 12. Billiards material physics — playable branch

**Code:** `pool.hlsl`, `pool-schema.json`, `pool_tests.zig`, `test_billiards_physics.py` on the playable branch.

A scientific stress test must keep contacts active to measure throughput. A realistic pool game must behave differently:

- One cue ball and 15 numbered object balls begin at rest.
- A cue strike adds a bounded impulse at a global tick boundary.
- New impacts use restitution; resting contacts must not bounce repeatedly.
- Rails apply normal restitution and tangential response.
- Cloth friction transfers motion from sliding to rolling and then slows the ball.
- Sleeping and exact stopping prevent idle drift.

The playable branch reports independent tests for collision impulses, energy, rolling, sleep/wake, and a long stationary-rack run. Material settings are **chosen parameters**, not certified measurements of a commercial table. This scene is not a replacement for the frozen scientific G4 fixtures.

**Engineering lesson:** Separate a physical product demonstration from a synthetic stress workload. Otherwise the test's artificial forces and initial velocities appear as game-physics defects.

## 13. Verification and low-cost test workflow

**Code:** `physics_verify.c`, `physics_tests.c`, `tests.zig`; on the playable branch `dev_test.py`, `test_dev_workflow.py`, and the billiards test scripts.

Validation has several levels:

1. **Unit contracts:** Checked arithmetic, entity identity, mappings, generation reuse, and transaction rollback.
2. **Small analytical physics tests:** Head-on and oblique impacts, friction, rails, energy and momentum checks.
3. **GPU correctness runs:** Contact count, island size, residuals, guard regions, rejected-state behavior, and resource ownership.
4. **Comparative performance:** Identical fixtures and hardware; separate CPU, GPU, renderer, and presentation costs.
5. **Full gate qualification:** Broader workload coverage and a recorded report. It is not part of every code edit.

For routine physics work, use the **headless CLI**. The playable branch's `python dev_test.py` supports quick, affected-file, and full levels. Its build cache hashes the source dependency graph, compiler, options, and output artifacts; it must not trust timestamps alone.

**G5 sweep method:** Run all specified topologies in one sequential CLI batch; write JSON/CSV evidence; show one compact summary. A two-sample quick sweep is exploratory. Do not treat its p95 as a stable tail-latency estimate.

Screenshots and video belong to an explicit **graphics/UX** task or a release milestone. They are not necessary to prove headless solver correctness.

## 14. Main technical contributions and their limits

These are **engineering contributions**, not claims that a method is new to computer science.

| Area | Contribution | Current limit |
|---|---|---|
| GPU-first state | Keep hot simulation data resident on the GPU. | Some setup, command, and diagnostics still use the CPU. |
| Entity lifetime | Generation-safe identity with GPU dense storage and verified growth. | Growth can stall; capacity and active count differ. |
| Measured layout selection | Compare AoS, SoA, and AoSoA before choosing SoA. | Selection depends on the measured passes. |
| Spatial search | Compare hash and radix under real candidate workloads. | Search speed does not imply fast constraint solving. |
| Island-level solve | Detect and process independent contact graphs; color conflicting contacts. | Large connected islands remain costly. |
| Numerical verification | Combine KKT residuals, energy checks, guards, and rollback. | Strict source-buffer isolation remains open. |
| GPU fast paths | Predication and early exit without per-tick CPU readback. | Local 16-ball measurements are not large-scene proof. |
| Rendering link | Draw completed GPU state with measured queue ownership. | Displayed FPS/scanout qualification remains open. |
| Reproducible test loop | Deterministic fixtures, hash-checked builds, headless batch sweeps. | Local handoffs must be committed or archived to persist. |

A high entity count is a storage and dispatch result unless the test also reports actual contacts, island structure, convergence, and accepted ticks.

## 15. Breakpoints and qualification record

A **breakpoint** is a formal gate close, a gate reopen, a changed system contract, a release candidate, or a validated performance decision. An ordinary small code edit is **not** a breakpoint.

| Breakpoint | Scope | State as of this record | Evidence / open issue |
|---|---|---|---|
| **G0** | Capacity limits and legal GPU resource plans | **Passed as planning** | No large-execution performance claim. |
| **G1** | ECS, storage layout, lifetime, growth | **Passed in historical scoped tests** | SoA selected; 10M storage workload measured. |
| **G2** | Spatial search and contacts | **Passed in historical scoped tests** | Hash selected; contact construction verified. |
| **G3** | Integrated evolving physics | **Scoped results available** | Large connected workloads exposed severe cost. |
| **G4** | Graphics, overlap, playable viewer | **Conditional GO** | GPU-02 physical displayed FPS not closed. |
| **G5** | Large islands, convergence, robust solver performance | **DEFERRED — CURRENT WORKSTREAM CLOSED; NOT QUALIFIED** | Algorithmic Anderson candidate rejected: eight formerly converging configurations lost convergence. Retained shader restored; large connected-island latency/convergence remains an accepted *development risk*, not a gate pass. Restart only on a demonstrated workload need or a separately authorized architecture prototype. |
| **G6** | Reproduce applicable gates, approve an engine foundation | **P1–P3 source integrated; P4 LOCAL PREPARATION PASS; formal G6 NOT QUALIFIED** | P4 isolated nonblocking accepted-state consumer: 11 PASS records, CPU wait p50 366.5→0 μs, GPU tick p50 602.5→786.5 μs and snapshot age 0→1. Source not merged or Windows-retested on current integrated head; device loss and display remain open. |

### Current G5 decision (2026-10-19)

**Finding:** The large-chain bottleneck is substantially algorithmic: the verified unit-mass 1,024-body chain has a poorly conditioned normal operator (about **424,971**) and the deterministic post-restart residual envelope contracts by about **0.995 per sweep**. The bounded depth-one Anderson trial greatly reduced iterations on some branching/dense/oblique fixtures but introduced **eight previously passing topology/policy convergence failures**, including policy-4 chains of 256 and 1,024 bodies. On chain-1,024, the candidate had **KKT ratio 107.98** and was correctly rejected/rolled back. Lower timing for this failed attempt is not a simulation speedup. Control accepted **115/120**, candidate **93/120**; all **27** candidate rejections verified rollback. The retained shader was restored exactly.

**Decision: G5 DEFERRED / CURRENT OPTIMIZATION WORKSTREAM CLOSED — NOT QUALIFIED.** No more G5 tuning or GPU micro-optimization sweeps are scheduled. Preserve the previously retained small safe optimizations, production policy **1**, opt-in policy **4**, `G5_BODY_CACHE=0`, `G5_REUSE_MEASURE_BODIES=1`, `G5_SKIP_OVERWRITTEN_RESIDUAL=1`, and `G5_DETERMINISTIC_MEASURE=0` by default. The test-only O(C²) scheduler and rejected Anderson experiment must never be promoted by default.

**Next work:** Shift to independently valuable GPU engine tasks: strict generation-state isolation, resource/scheduler design, public host API, recovery and error handling, representative smaller/scattered-island workflows, and missing G4 real-display verification when display claims matter. **G6 scoping/preparation may begin** with a written, limited application envelope, but **formal G6 foundation qualification is not authorized** by deferring G5. Revisit G5 only when a target workload and a potentially material architectural alternative justify it. Do not claim large-connected-island real-time throughput, million-body full physics or G5 pass.

**Evidence:** `G5-Algorithmic-Convergence-20261019.zip`, 2026-10-19, evidence branch `g5-convergence-anderson-20261019`, revision `a147f6bf265bc82060107358cd41157e38d371c2`. ZIP CRC and 2,159 file hashes verified; 240 recorded Windows runs, 20 residual probes, independent statuses/invariant/rollback checks and 46/49 unit-test logs inspected. No independent Windows GPU test or production shader merge was performed for this documentation decision.

### Current G6 preparation decision (2026-10-19)

**Finding:** P1–P3 source and playable renderer were integrated into `main` and the playable branch in PRs #1/#2, preserving both histories and the complete architecture record. The new P4 experiment is **separate**: it compiles the real offscreen renderer to lease the last accepted generation while a newer compute tick is pending and validates the newer tick at ordered retirement. A native gated-producer test proved two GPU draws from generation 0 while newer work was blocked (ages 1/2) with successful later release, rejection/rollback, lease exhaustion and delayed cancellation. The Windows evidence records 11 passed tests (six freshly executed, five unchanged-binary reuses). In one matched 32-sample-per-arm headless timing set, median CPU acceptance blocking fell **366.5→0 μs** and CPU handoff **751.3→347.0 μs**, but physics GPU tick increased **602.5→786.5 μs**, renderer GPU time **16.384→22.528 μs**, and accepted snapshot age rose from **zero to one tick**.

**Decision: G6-P4 LOCAL PREPARATION PASS / DO NOT CLAIM THROUGHPUT IMPROVEMENT; FORMAL G6 NOT QUALIFIED.** Retain the correct nonblocking mechanism on the independent `g6-p4-nonblocking-consumer-20261019` branch; do not confuse it with a tested merged `main` build. Ordinary frames may use a previous accepted immutable generation; command acknowledgment still requires matching-tick acceptance and may block. No physics/shader change or additional GPU allocation is established; full frame throughput and interactive display are not. G5 stays **DEFERRED / NOT QUALIFIED**; physical device-loss recovery, GPU-02 displayed FPS and G6 foundation signoff remain unverified.

**Next action:** First reconcile P4's post-P3 branch onto the current **integrated main** source history without replacing the complete architecture doc, and run a limited Windows proof of actual renderer lease correctness and accepted-state age/cost on that merged code. Then investigate a **bounded device-loss/teardown/reinitialization contract** separately. Model injected faults accurately, handle invalid fences and held consumer leases, and do not claim device-removal recovery without actual device-removal/recreation tests. Avoid further G5/solver optimization campaigns.

**Evidence:** `G6-P4-Nonblocking-Consumer-20261019.zip`, commit `aa7d77cdfcef0efe777539aa876d2a5b05cb7ba3`; 149/149 archive hash checks and offline verifier pass; recorded 11 PASS test entries, control/candidate EXE hashes and all 14 raw-timing reconciliations checked; no independent Windows GPU run during this GitHub documentation update.

## 16. Risks and work still required

1. **State publication and freshness:** P1–P3 source is integrated; P4 has a separate local correctness pass for rendering the last accepted immutable generation while producer work is pending. Normal command-free submit is nonblocking but frames are one tick older in the measured case (two under gated-producer test); command acknowledgment still waits. Validate P4 on the newly merged source and prove user-visible freshness/interaction separately before treating this as a production default.
2. **General island convergence — deferred G5 debt:** Policy 4 remains opt-in with limited, valid quick-sweep results; it is not qualified for sustained/general workloads. The rejected Anderson trial lost previously accepted configurations. Do not loosen KKT/rollback or describe G5 as passed; reopen only against an explicit large-island requirement and new algorithmic design.
3. **Large-island architectural limitation — parked:** The 1,024-body chain requires about 4,024 sweeps, with ~140 ms of solver execution in deterministic test conditions. Its settled chain operator is poorly conditioned (~424,971). Recent noise-aware micro-optimizations were inconclusive; a bounded Anderson method broke convergence. The serial O(C²) deterministic sorter remains measurement-only. Do not initiate further G5 experiments without an authorized performance target and a new architecture hypothesis.
4. **Scheduler and resource-management scope:** G6-P3 raises the bounded consumer extra dependency count to **five** for the actual renderer; the stale header comment was corrected at integration. The API stays CPU-owner-thread serialized with 64 task/lease entries and 32 producer dependencies. Queue/fence claims do not implement a general multi-producer scheduler or GPU core allocator.
5. **Display verification:** Collect real local display evidence for GPU-02 when required. Do not confuse Present calls with scanout.
6. **Evidence and deterministic replay:** The isolated policy-4 baseline has been recovered with all 25 source hashes and a successful 80-run behavioral sweep. Historical and rebuilt CLI hashes differ and the comparison reports 156 numerical and 23 color-count differences. Track compiler/link inputs and exact revision, shader hashes, fixtures and GPU/driver context; do not claim byte-identical replay.
7. **G6 performance, device loss and qualification:** P4 eliminates the measured CPU pre-submit acceptance wait (366.5→0 μs), but same-batch GPU tick (602.5→786.5 μs) and render (16.384→22.528 μs) p50 worsen, and one tick of accepted-state age is introduced. P3's historical ~1.13-ms wait is from another measurement set; do not combine it as a paired comparison. The test remains offscreen without physical D3D12 removal/recreation, `Present`, network consumers, or formal G6 signoff. P2 break-workload timing mode remains unresolved. G4/G5 claims are not waived.

## 17. How to update this living document

On **each breakpoint**, update this file **in the same change** as the breakpoint decision. Do not create a parallel architecture report as the only record.

Required update procedure:

1. Identify the breakpoint name, code revision, and date.
2. Update the affected technical sections if behavior or design changed.
3. Mark each claim as implemented, measured, experimental, conditionally accepted, or planned.
4. Add measured workload, hardware, sample count, and a link or path to evidence. If evidence stays local, say so.
5. Update the qualification table and the active risks. Retain failed results and prior decisions.
6. Add one short entry to the change log below.
7. Commit the document with the related code, or in the same breakpoint documentation commit. A gate is not closed if this step is missing.

For routine small fixes, update the relevant existing paragraph only if the technical contract changes. Do **not** run a full test campaign or rewrite the entire record to change a sentence.

### Breakpoint entry template

```text
Date and breakpoint:
Revision / branch:
Change:
Why it matters:
Evidence: fixture, hardware, samples, exact file/URL
Result: PASS / CONDITIONAL / FAIL / UNVERIFIED
Known limits:
Next action:
```

### Change log

| Date | Breakpoint | Record update |
|---|---|---|
| 2026-10-18 | Baseline document | Established the technical inventory, G0–G5 history, evidence labels, known risks, and mandatory breakpoint update process. No new gate was approved by this documentation commit. |
| 2026-10-18 | G5 adaptive-solver decision — FAIL | Reviewed 60 CLI runs and matching JSON/CSV summary. The adaptive policy converged in 16/20 runs but failed the 256- and 1,024-body chains. It was rejected; the previous policy remains the local baseline, and G5 stays open. |
| 2026-10-18 | G5 bounded-restart candidate — CONDITIONAL | Reviewed 60 headless GPU runs and six diagnostics. Policy 3 converged in 20/20 local attempts, but 256/1,024-body chains and several branching/oblique networks suffered performance penalties. Production remains unchanged; G5 remains unqualified. |
| 2026-10-18 | G5 residual-gated restart — OPT-IN RETAIN | Audited 80 short GPU timing runs, 10 trace checks and 17 reported sweep unit tests. Policy 4 converged in 20/20 and lowered aggregate GPU p50 sum by 13.5% relative to policy 3, but remained slow on large chains. Production policy 1 unchanged; G5 unqualified. |
| 2026-10-18 | G5 shared-body-cache experiment — REJECT | Audited 100 CLI timing trials, 22 probes, 22 unit tests and the HLSL source. 1,024-body GPU p50 improved 170.13→152.69 ms, but aggregate geometric mean worsened 4.25%. Hardware counter attribution is unverified. Default remains cache-off; G5 open. |
| 2026-10-18 | G5 baseline-recovery blocker — BLOCKED / PARTIAL RECOVERY | Local Codex run made no solver or GPU-test change after losing the policy-4 baseline. Exact 3.6 MB archive and workflow dependencies were found and SHA-verified, and a read-only recovery kit was made. Four source matches and Windows retest remain outstanding. |
| 2026-10-18 | G5 isolated baseline — RECOVERED / NOT QUALIFIED | Restored 25 source files and six workflow hashes; archived 33 passing workflow tests, an 80-run Windows sweep, and 74 accepted/six expected rejected trials. Policy 4 passed 20/20. Rebuilt CLI differs in SHA and the per-run record has 156 numerical differences, so exact replay remains unverified. |
| 2026-10-18 | G5 residual body-snapshot reuse — RETAIN LOCALLY | Audited a small HLSL change, static DXIL reductions, 200 control/candidate GPU trials and 33 unit tests. Retained after independent correctness checks and aggregate p50 improvements. 1,024-body GPU p50 167.33→162.99 ms, with individual fixture regressions and no formal G5 qualification. |
| 2026-10-18 | G5 skip overwritten residual scans — RETAIN LOCALLY | Audited a conditional skip before mandatory reconstructed-state residual checks. Reviewed 200 recorded headless timing trials, six traces, 34 final unit tests, matching JSON/CSV summaries and source hashes. Policy-4 chain-1,024 p50 165.61→155.86 ms; 4,026 iterations unchanged. Broad geometric-mean gain only 0.28%. G5 remains unqualified. |
| 2026-10-19 | G5 early residual restart — REJECT / ROLLBACK | Audited 200 timed trials, 40 traces and 37 unit tests. Early policy-4 restarts saved 256 iterations on large chains, but its ten-fixture geometric-mean GPU p50 worsened 0.97%, failing the retention rule. Tested shader rolled back byte-for-byte; production policy 1 remains unchanged. |
| 2026-10-19 | G5 A/A repeatability — MEASURED / NO SOLVER CHANGE | Audited 80 same-binary GPU trials (8 per fixture), 43 preflight tests and corrected signature analyses. Geometry and accepted-state checks stayed fixed; atomic ordering changed solver color schedules. Identical-code GPU p50 B/A ranges 0.8665–1.1282, so subpercent cross-schedule wins are unqualified. Next: measurement-only deterministic arithmetic replay. |
| 2026-10-19 | G5 deterministic measurement — BOUNDED PASS / TEST ONLY | Reviewed local 180-run headless batch, 150 deterministic accepts/10 expected rejections, 20 native accepts, two safe-envelope failures, and 1,513 verified file hashes. Canonical schedules, iterations and FP64 results repeat; 1,024-body scheduling cost ~46.954 ms, runtime still varies. Default production and solver unchanged; G5 open. |
| 2026-10-19 | G5 post-color barrier coalescing — REJECT / RESTORE | Verified 1,984 archived file hashes, 240 serialized headless runs, all ten matched summary rows, 46 preflight and 49 restored-baseline tests. Control/candidate physics and FP64 signatures matched exactly; 1,024-body nominal solver gain was below 4.36% A/A floor, and aggregate full-tick interval crossed no-effect. Active shader restored byte-for-byte; G5 remains open. |
| 2026-10-19 | G5 contact-local FP64 body snapshots — REJECT / RESTORE | Checked all 1,986 archive hashes, 240 same-schedule GPU trials, 230 accepted + 10 expected rollback-verified rejects, 46 preflight and 49 restored-baseline tests. Solver p50 142.93→138.69 ms at 1,024 bodies; paired ratio 0.97491 CI crosses 1 and 5.32% A/A floor. Aggregate complete-tick test passed, primary failed; retained shader restored. Separate experiment branch pushed, not merged. |
| 2026-10-19 | G5 bounded Anderson convergence — REJECT / RESTORE | Audited 240 recorded Windows trials, 20 residual probes, 2,159 file SHA-256 entries and unit logs. Candidate had 93 accepted vs 115 controls, losing convergence in eight prior-passing fixture/policy configurations. Lower candidate timing on rejected ticks cannot count as speedup. Shader restored exactly; experiment evidence branch remains unmerged. |
| 2026-10-19 | G5 priority gate disposition — DEFERRED / CURRENT WORKSTREAM CLOSED | Ended active G5 optimization after repeated inconclusive micro-gains and algorithmic convergence regression. G5 remains technically not qualified; keep baseline and proofs. Allow independent G6 scoping and other engine development, but do not approve formal G6, large-island claims or release without scope-specific qualifying evidence/risk decision. |
| 2026-10-19 | G6-P1 immutable accepted-state publication — LOCAL PREPARATION PASS | Audited `g6-p1-state-isolation-20261019` source and recorded 21/21 headless PASS processes, zero reported validation errors, 422 verified ZIP hashes, and two 32-sample AB/BA repeats per timing workload. Bounded GPU snapshot/lease API prevents tested retained-consumer aliasing; idle p50 GPU 262→263.75 μs, CPU submit 212.5→213.5 μs, two-slot capacity-32 overhead 128 KiB. Actual device loss/viewer lifecycle and formal G6 remain unverified. |
| 2026-10-19 | G6-P2 bounded GPU resource ownership — LOCAL PREPARATION PASS | Reviewed isolated branch `g6-p2-resource-ownership-20261019`, 22/22 recorded headless process passes, 0 reported validation errors and 252 verified ZIP hashes. Shared-read/exclusive-write claims, queue/fence-retained consumers and cancellation/failure cleanup pass; GPU allocations/committed memory unchanged. Break timing mode shift still unexplained; real app/device-loss qualification open. G5 stays deferred; G6 not qualified. |
| 2026-10-19 | G6-P3 real renderer consumer — LOCAL PREPARATION PASS | Audited 14 PASS Windows headless processes and all 877 archive hashes. Actual offscreen viewer `DrawInstanced` consumes accepted immutable snapshots through P2 leases/fences; 32 physics DXIL pairs unchanged. Render p50 18.432 μs, CPU acceptance wait 1,131.8 μs, offscreen committed memory −192 KiB and three allocations fewer. No `Present`, pixel output or physical device loss tested; G5 deferred, G6 not qualified. |
| 2026-10-19 | G6-P1/P2/P3 + playable branch integration — RECONCILED / NOT G6 QUALIFIED | Integrated cumulative tested development ancestry with main documentation-only history. Kept complete living architecture document and current development README/AGENTS rules, corrected stale 3→5 resource-limit comment. No solver algorithm or compiled binary altered. A separate Windows validation is required after integration; G5 deferred, G6 not qualified. |
| 2026-10-19 | G6-P4 nonblocking accepted-state renderer — LOCAL PREPARATION PASS | Audited 149 archive hashes, 11 PASS final records (6 fresh/5 reused) and 14 timing summary rows against 32 raw samples per arm. Native gated producer test completes two real prior-accepted-generation draws; command acknowledgments still wait on their matching tick. CPU acceptance p50 366.5→0 μs; CPU handoff 751.3→347.0 μs; GPU physics tick 602.5→786.5 μs, render 16.384→22.528 μs; age 0→1 tick. P4 source remains on diverged branch, not integrated into main; G5 deferred, G6 not qualified. |

---

**Source map:** [Main engine code](../physics.c) · [Spatial search](../spatial.c) · [Storage](../storage.zig) · [Entity identity](../entity.zig) · [Viewer](../viewer.c) · [Playable branch](https://github.com/Cryosimorgh/GPU-physics-engine/tree/billiards-playable-requalification-20261018) · [Playable headless workflow](https://github.com/Cryosimorgh/GPU-physics-engine/blob/billiards-playable-requalification-20261018/dev_test.py).