# GPU Physics Engine — Technical Architecture and Development Record

**Project:** [Cryosimorgh/GPU-physics-engine](https://github.com/Cryosimorgh/GPU-physics-engine)  
**Record date:** 2026-10-19
**Document type:** Living engineering record  
**Style:** Clear technical English, based on ASD-STE100 principles without strict controlled-language limits  
**Status:** Experimental GPU physics engine. G5 is **DEFERRED / NOT QUALIFIED**. G6-P1/P2/P3/P4 are preparation only; G6 and production release are **not qualified**.

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

**G6-P1 state isolation (local preparation):** `ph_publish` still writes the producer-private G1 source after all existing GPU checks. Consumers that retain a generation now use separately owned immutable publication slots and leases. A completed slot becomes accepted only after its terminal compute fence and the existing completed-frame validation header agree. This closes the retained-consumer aliasing gap for the new lease API without changing the solver or its private trial/source equations. Raw G1 handles remain internal borrowed resources. G6-P3 routes the existing renderer through accepted immutable snapshots and P2 task ownership; the legacy fenced per-frame copy remains only in the matched test control. Formal G6 and device-loss recovery remain unqualified; see the G6-P1 decision below.

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

### G5 per-iteration optimization - baseline recovery blocked (2026-10-18)

The cleanup removed the local-only G5 shader, sweep, profile scripts, and raw evidence. The restored checkout at `3a29fc0ec9ff9ac54c0680e9130405368700074c` contains decision records but not `sweep_g5.py` or `profile_global.py`. Its shader has the earlier fixed large-island relaxation implementation, not the measured policy-4 implementation. The main and physics-correction branch trees also lack the sweep/profile scripts.

**Decision:** Do not substitute the earlier solver for the unchanged 167 ms baseline. No shader change, GPU sweep, or optimization retention decision was made. Complete tick, solver time, iterations, CPU submission, KKT, rollback, and aggregate performance comparisons remain **UNVERIFIED** for this request. G0-G4 statuses are unchanged; G5 remains **NOT QUALIFIED**.

**Required recovery:** Restore `G5-Global-Solver-Cost-Handoff-20261018T090324676154Z.zip` (previous SHA-256 `07dd2be67af66faf089bdc726feb1b0b4d7cdd59a7250a8fcf7d4acb327c0a18`) or an equivalent complete snapshot with the tested policy-4 shader, verified build workflow, sweep, fixtures, and baseline evidence. Then inspect that exact source/DXIL and run one matched serialized quick sweep. Recreating the deleted solver policies or harness is outside this one-correction task.

### G5 tested baseline recovery - source and headless correctness restored (2026-10-18)

The preceding missing-source blocker is resolved in the isolated `g5-baseline-work` checkout. The original `engine-work` checkout and its files were not changed. The recovery kit's read-only verifier passed before restoration and again afterward: **25/25 source hashes** and **6/6 workflow hashes** match, including all four unbundled dependencies. The original evidence ZIP has SHA-256 `07dd2be67af66faf089bdc726feb1b0b4d7cdd59a7250a8fcf7d4acb327c0a18`; the restored solver has SHA-256 `f9b93e98d3fb78944ae6547530d77e94cf29013ca61313af41d3448194bb05f9`. Additional CLI inputs `physics_tests.c`, `spatial.c`, and `spatial-layout.h` match the preserved qualified release manifest. No source dependency mismatch was found.

**Build:** Zig 0.15.2; Windows SDK 10.0.26100.0; DXC 1.8.2502.11. Recovered scripts were used unchanged. All shader hashes in all four rebuilt control configurations match the archived shader hashes. Policy 4 uses `G5_BODY_CACHE=0` through the unchanged compile-time default. The rebuilt CLI hash is `b68e82b173659046a93767444ebaa9a90d6d222d473e34375ecf187a0fa1836e`; the archived fingerprint is `fbc98450e31ffe5eb452a58ab3457aa1f22319d1b1d26d2de65dfcc7a7dd0451`. The kit contains no archived executable bytes. The cause of this executable-byte difference remains **UNVERIFIED**; source/shader recovery and runtime acceptance are separate from binary identity.

**Execution:** 33 workflow/sweep/profile unit tests passed. One serialized `python sweep_g5.py quick` used the existing smallest quick mode, ten deterministic fixtures, four controls, and two cold trials per case. All ten input hashes match the archive. Of 80 trials, **74 converged**, and the same **six PGS chain cases rejected** at the unchanged limit with verified rollback. No timeout, admission rejection, or unexpected error occurred. Policy 4 passed **20/20**, including the 1,024-body chain. All accepted trials passed unchanged independent KKT, momentum, energy, contact/island, impulse, and state checks. The sweep exits 1 because it counts expected PGS rejections; this exit is preserved, not relabeled by changing the harness.

| Policy-4 chain, 1,024 bodies | Archived | Recovered |
|---|---:|---:|
| Complete GPU tick p50 | 170.134 ms | 167.940 ms |
| Complete GPU tick p95 (max of two) | 171.129 ms | 168.213 ms |
| Solver p50 | 167.466 ms | 165.860 ms |
| CPU record + submit p50 | 3.697 ms | 3.762 ms |
| Maximum iterations | 4,026 | 4,026 |
| Contacts / largest island | 1,023 / 1,024 | 1,023 / 1,024 |

**Decision:** The tested source and headless correctness baseline are restored. This is not a new optimization or a G5 qualification. Exact numerical equality is not claimed: color counts differ in 23/80 cases, and iterations differ by up to 444 across controls (up to 227 for policy 4). The existing invariant tolerances were not changed. Color/order variability and two cold samples limit historical timing comparisons; shader identity does not establish identical graph schedules. No cache, solver-policy, arithmetic, or synchronization optimization was made. Future comparisons must retain matched controls and report this variability. G0-G4 statuses remain unchanged; G5 remains **NOT QUALIFIED**. Executable byte equivalence remains **UNVERIFIED**.

**Local evidence:** `dev-test-results/recovery-preflight/provenance.json`, unit/build logs, and `dev-test-results/g5-sweep-20261018T191026867497Z/{results.json,results.csv,recovery-comparison.json}`. `recovery_preflight.py` and `recovery_compare.py` only check restoration/build provenance and compare already completed outputs; they do not replace the recovered solver or physics tests. No GUI, screenshots, full campaign, hardware-counter request, or release package was used.

### G5 per-iteration body-snapshot reuse - RETAIN (2026-10-18)

**Compiler/linker provenance:** Before optimization, a fresh unchanged CLI was built with the same Zig 0.15.2, Windows SDK 10.0.26100.0, ReleaseSafe target/options, and source dependencies as recovery. Its SHA-256 is `237c22371b75c76ffed9cc5c50b4f4fbbe201bd77e7539f49c0466b4d7edddbc`, versus recovered `b68e82b173659046a93767444ebaa9a90d6d222d473e34375ecf187a0fa1836e`. Every PE section except `.buildid` matches, including executable code and data. The logged Zig link uses `lld-link -DEBUG -PDBALTPATH:physics.pdb -BREPRO`; link/debug metadata therefore demonstrates an executable hash-change mechanism without a code change. This does not prove the cause of the older archived `fbc984...` fingerprint: the original executable, compiler/linker invocation, library hashes, and build-cache record are absent. That historical byte-identity question remains **UNVERIFIED**. Current tool hashes, full linker/library arguments, PE section hashes, and Zig environment are saved in `dev-test-results/solver-cost-inspection/`. The historical baseline GPU sweep was not repeated.

**One correction:** `measure()` loaded the same body state for tolerance and then reloaded it through `relative()` for normal and tangent residuals. It writes no body state between these reads. `G5_REUSE_MEASURE_BODIES=1` reuses its original `Body` snapshot through `measureRelative()`, retaining the original float-rounding points, FP64 expressions, KKT normalization, and reduction order. `applyColor()` still reloads after each normal impulse before calculating tangent response; no impulse, contact, rollback, iteration/work-limit, relaxation-policy, or barrier behavior was changed. Production relaxation policy stays 1; body caching stays 0.

**Source/DXIL evidence:** Fresh flag-0 controls for policies 0, 1, 3, and 4 exactly reproduce the archived solver DXIL hashes; their readiness shader also matches. Policy 2 was built as an unchanged control alongside them. Policy-4 DXIL static buffer-load sites decrease **225 to 191**, double-assembly sites **71 to 55**, and FP64 arithmetic sites **157 to 153**. Barrier sites remain **20**. Policies 0-2 retain 17 barrier sites; all five policies lose 34 buffer-load sites. These are static compiler instruction counts, not dynamic physical transactions, cache misses, or hardware stall measurements.

**One automated quick batch:** `python sweep_solver_cost.py quick` delegates fixture construction, subprocess execution, independent physics auditing, and timeout handling to the recovered `sweep_g5.py`. It first runs the 33 existing unit tests, prepares all builds, then executes two cold samples across ten fixtures, five policies, and matched control/candidate arms, sequentially. Both arms use the exact same freshly linked CLI executable and common shader hashes. All **200 trials** completed without timeout or unexpected error. Each arm had **90 accepted solves and 10 expected rejections** (six PGS and four policy-2 chain failures); all accepted invariant checks and all rejected rollback checks passed. Contact coverage, actual island sizes, KKT checks, momentum, energy, and 4,096-iteration limits remain unchanged. No previously accepted configuration lost convergence.

| Policy-4 chain, 1,024 bodies | Fresh control | Snapshot reuse |
|---|---:|---:|
| Complete GPU tick p50 / p95 | 167.33 / 168.11 ms | 162.99 / 163.79 ms |
| Solver p50 | 165.35 ms | 161.12 ms |
| CPU record + submit p50 | 2.928 ms | 2.846 ms |
| Iterations, both samples | 4,026 / 4,025 | 4,026 / 4,027 |
| Contacts / largest island | 1,023 / 1,024 | 1,023 / 1,024 |

**Predeclared decision rule and result:** Keep only if correctness and matched rejection behavior pass, and both geometric-mean and summed complete-tick p50 improve for (a) the ten policy-4 fixtures and (b) every accepted-policy configuration. Policy-4 ratios are **0.962547 / 0.964774**; the 45 accepted-policy configurations yield **0.983971 / 0.953917**. Expected rejected attempts cannot improve those aggregates. **RETAIN snapshot reuse.** Two samples make p95 the maximum of two and do not establish statistical significance or sustained tails. Individual regressions remain visible: policy-4 branching-64 is 3.13 to 3.24 ms, dense-256 is 11.17 to 11.58 ms. Graph coloring and iteration variability can confound fine timing differences; no physical memory-bandwidth or GPU-counter claim is made.

The retained default source SHA-256 is `39d7d5e606dfad1cbd71de04e1de68a3d7d008e35f235bfdc01df8814edc233f`. After changing only the default macro from 0 to 1, the production-policy `ph_ready` and `ph_solve` were recompiled and match the tested candidate binaries exactly; no extra GPU cases ran. The control remains reproducible with `G5_REUSE_MEASURE_BODIES=0`.

**Remaining bottleneck:** The solver still consumes roughly 161 of 163 ms for the connected 1,024-body fixture. Ordered FP64 color sweeps, body/contact accesses, periodic velocity reconstruction, and approximately 4,000 iterations remain. The exact arithmetic/memory/synchronization hardware split is **UNVERIFIED**. Inspect that remaining loop before selecting any next correction; do not infer cache behavior from these timings. G0-G4 statuses are unchanged; G5 remains **NOT QUALIFIED**, and policy 4 remains opt-in. No viewer, screenshot, hardware-counter request, full campaign, or release package was used.

**Local evidence:** `dev-test-results/g5-measure-snapshot-20261018T192452634739Z/` contains the predeclared rule, all source/build hashes, ten control/candidate DXIL dumps, unit/build logs, per-trial raw state/contact exports and independent proofs, `results.json`, `results.csv`, tested/retained source snapshots, and `retained-build.json`. The consolidated console log is in `dev-test-results/solver-cost-inspection/matched-quick-console.log`. This is local evidence, not a GitHub CI or gate-qualification result.

### G5 skip overwritten residual scans - RETAIN under quick rule (2026-10-18)

**Evidence and one correction:** The saved global-memory diagnostic recorded 504 reconstructions in 4,025 iterations. In the real loop, every eighth iteration and the last allowed iteration force reconstruction regardless of the preliminary residual. The reconstructed-state scan then overwrites both residual outputs before convergence or relaxation policy uses them. `G5_SKIP_OVERWRITTEN_RESIDUAL=1` skips only that preliminary scan on these forced iterations. It retains every post-reconstruction KKT check and every preliminary check needed to trigger early convergence reconstruction. Contact equations, FP64 expressions, color passes, all five policies, tolerances, impulse constraints, energy/momentum validation, rollback, and work/iteration limits are unchanged. The device/group barrier before reconstruction remains. Body-snapshot reuse stays enabled; body caching stays disabled; production policy stays 1.

**Compiled proof:** All five fresh flag-0 control solver hashes and their readiness shader match the retained snapshot-reuse baseline. Control and candidate use identical CLI/common shader bytes. Policy-4 static DXIL remains 191 buffer-load sites, 55 double-assembly sites, 153 FP64 arithmetic sites, and 20 barrier sites. The correction guards execution of the first residual-scan block; it does not remove either scan's compiled body. At 4,026 iterations it avoids 503 scans and their 4,024 group-reduction barriers by source accounting, not hardware-counter measurement. Profiling accounting now subtracts skipped scans using the actual command's work/iteration limit. Its focused unit check covers short limits, last-iteration scheduling, early completion, and disabled controls.

**One serialized batch:** `python sweep_solver_cost.py quick --skip-overwritten-residual` runs the existing independent fixture/audit implementation, with ten fixtures, five policies, two cold samples, and matched arms. All **200 timing trials** completed: each arm had **90 accepted solves and the same 10 expected rejections**. Accepted KKT, contact/island coverage, energy/momentum and impulse checks passed; every rejected attempt verified rollback. There were no timeouts or unexpected errors. Six additional trace-instrumented runs, excluded from timing aggregates, covered both arms on 64-, 256-, and 1,024-body chains. The trace decoder checked full expected window coverage; all six converged. The 64-body traces both finished in 367 iterations without restart. The 1,024-body traces both restarted at 512, finished at 4,026 with final relaxation 1.995, and showed similar post-restart contraction (about 0.73 at 1,024 iterations, 0.63 at 2,048, and 0.41 at 3,072). Numerical trace equality is not claimed across variable contact/color ordering. The initial 33 unit tests passed; after the profiling-accounting update, the combined **34 unit tests** passed with no further GPU cases.

| Policy-4 chain, 1,024 bodies | Snapshot-reuse control | Skip overwritten scan |
|---|---:|---:|
| Complete GPU tick p50 / p95 | 165.606 / 167.107 ms | 155.860 / 157.075 ms |
| Solver p50 | 163.332 ms | 153.926 ms |
| CPU record + submit p50 | 3.305 ms | 3.293 ms |
| Iterations, both samples | 4,026 / 4,026 | 4,026 / 4,026 |
| Contacts / largest island | 1,023 / 1,024 | 1,023 / 1,024 |
| Maximum independent KKT ratio | 0.978835 | 0.980634 |

**Decision:** **RETAIN under the unchanged predeclared quick rule.** Both geometric-mean and summed complete-tick p50 must improve for policy 4 and all accepted-policy configurations, with no convergence/correctness regression. Policy-4 ratios are **0.940693 / 0.932529**. Across 45 accepted-policy configurations they are **0.997168 / 0.971424**. The broad geometric-mean gain is only **0.28%** and is weak evidence with two cold samples; it is not a statistically established general speedup. Individual policy-4 regressions remain visible (branching-64: 3.49 to 3.78 ms; dense-64: 1.84 to 1.87 ms). p95 is the maximum of two samples. The clear target improvement reduces redundant work, **not required iterations**. Do not tune policy or tolerance to hide the remaining approximately 4,026-iteration solve.

**Preservation and build:** Work is isolated in `g5-residual-work`, branch `g5-skip-overwritten-residual-20261018`. All 313 tracked-file hashes and the original `g5-baseline-work` uncommitted status remain unchanged; its HEAD remains `d349468`. The retained solver source SHA-256 is `10c5ee6541c7799119a9578b304c51f8d3de3938e2221613894bc7fae75d5c24`. After enabling the default, production-policy readiness/solver shader hashes match the tested candidate exactly. No source outside the isolated copy was changed.

**Remaining limit and gate status:** Long ordered color sweeps and slow residual contraction still dominate the connected island. The measured solver still costs about 154 ms. The arithmetic/memory/synchronization hardware split and historical CLI binary identity remain UNVERIFIED. G0-G4 statuses are unchanged; G5 remains **NOT QUALIFIED**, with policy 4 opt-in. No GUI, screenshot, manual case-by-case GPU run, full campaign, or release package was used.

**Local evidence:** `dev-test-results/g5-skip-residual-20261018T194444930628Z/` contains JSON/CSV results, full per-run exports and proofs, all expected residual windows in `residual-traces.csv`, control/candidate DXIL dumps, build/source hashes, tested/retained shader snapshots, unit logs, default-build equality, and workspace-preservation checks. `dev-test-results/skip-residual-quick-console.log` is the consolidated output. The saved command `G5_SKIP_OVERWRITTEN_RESIDUAL=0` reproduces the retained control.

### G5 early residual-based restart - REJECT (2026-10-19)

**Hypothesis from retained traces:** After relaxation increases at iteration 128, the 64-body chain's next two window contractions are approximately 0.019 and 0.060; the 256-body chain's are 2.99 and 1.18, and the 1,024-body chain's are 3.48 and 27.35. A single candidate allowed policy 4 to restart before the existing budget checkpoint only after two consecutive complete windows with contraction at least 0.8, relaxation already above 1, and the settling period finished. Fast contraction resets the evidence. The original checkpoint fallback remains. There is no topology, fixture-name, or body-count condition; every equation, KKT tolerance, projection, energy/momentum check, rollback path, and 4,096-iteration/work limit is preserved. Policies 0-3 are byte-identical between arms. Production policy remains 1.

**One matched headless batch:** `python sweep_solver_cost.py quick --early-residual-restart` prepares control/candidate builds, then serializes 200 timing trials across all ten fixtures and five policies, plus 40 separate policy-3/policy-4 trace checks across every fixture. All five control solver hashes match the retained skipped-residual baseline. A targeted CPU test first failed on the old trace interface; all **37 unit tests** passed in the batch after adding strict early-restart trace validation. Each timing arm had **90 accepted solves and the same 10 expected rejections**; independent coverage, KKT, momentum/energy, impulse, and rollback checks passed. All 40 traces converged and passed complete-window/restart audits. No timeouts or unexpected failures occurred.

**Restart evidence:** Each arm's twenty traced cases contained four policy-3 restarts and two policy-4 restarts. Policy-3 behavior stayed unchanged. Policy 4 restarted the 256- and 1,024-body chains once at 256 instead of 512; the other eight fixtures had no policy-4 restart in either traced arm. In the 1,024-body trace, iterations changed from 4,025 to 3,769. No fast-converging fixture was incorrectly restarted in these traces. These are separately instrumented trace counts, not claimed per-timing-trial counters; all trace timings are excluded from the performance aggregates. Policies 0-2 have no restart code path.

| Policy-4 chain, 1,024 bodies | Matched retained control | Early-restart candidate |
|---|---:|---:|
| Complete GPU tick p50 / p95 | 150.31 / 155.55 ms | 147.05 / 147.68 ms |
| Solver p50 | 148.82 ms | 145.75 ms |
| CPU record + submit p50 | 2.947 ms | 2.994 ms |
| Timing-trial iterations | 4,025 / 4,024 | 3,768 / 3,770 |
| Restart in separate trace | once at 512 | once at 256 |
| Contacts / largest island | 1,023 / 1,024 | 1,023 / 1,024 |

**Decision: REJECT and restore the retained solver source exactly.** Correctness passes and the chains improve, but the unchanged four-part performance rule fails: policy-4 geometric-mean complete-tick p50 ratio is **1.009750** (0.97% worse), while its summed-p50 ratio is 0.994430. All accepted-policy ratios are 0.992969 / 0.993816; these cannot override the failed policy-4 condition. Examples of policy-4 regressions are dense-64 (1.86 to 2.05 ms), dense-256 (9.70 to 10.15 ms), and oblique-256 (28.79 to 32.65 ms). Two cold samples and contact/color-order variation limit causal attribution; no statistical significance, cache, register-pressure, or hardware-stall claim is made. No second parameter choice or GPU rerun was attempted.

**Preservation and breakpoint:** Original `g5-residual-work` files and uncommitted status remain unchanged; 388 file hashes were checked. Experiment work is isolated on branch `g5-early-residual-restart-20261019` in `g5-restart-work`. Active `projected_solver.hlsl` was restored byte-for-byte to the retained SHA-256 `10c5ee6541c7799119a9578b304c51f8d3de3938e2221613894bc7fae75d5c24`; rebuilt policies 1 and 4 match their control shader hashes. The rejected shader SHA-256 `b57f6011133a647bf4c787913ed70a8be484923d27edd69a6c1e862ec10c449b` is preserved only as experiment evidence. The trace decoder retains all old default checks and additionally verifies both poor settled windows before accepting an early restart; premature and fast-contraction restart fixtures fail its unit tests. The sweep refuses an early-restart comparison when the archived candidate shader is not applied.

**Remaining issue and gate state:** The retained policy 4 still spends roughly 512 iterations before its bounded restart. Earlier restart is promising for the chain but is not retained without a balanced gain across the existing workloads. Resolve color/order and short-run measurement variability before attributing or tuning the small-case losses. G0-G4 statuses are unchanged; G5 remains **NOT QUALIFIED**, with policy 4 opt-in. No GUI, screenshots, per-case manual GPU runs, full campaign, or release package was used.

**Local evidence:** `dev-test-results/g5-early-restart-20261019T032246446898Z/` contains all source/build hashes, unchanged-policy comparisons, JSON/CSV timing and correctness results, raw exports, all 40 full residual traces, unit/build logs, rejected shader snapshot, and `rejection-and-preservation.json`. The consolidated output is `dev-test-results/early-restart-quick-console.log`. The single focused handoff includes the candidate shader as evidence for reproduction; it does not activate the rejected solver.

### G5 measurement repeatability - quantified, no solver change (2026-10-19)

**Method:** `python measure_repeatability.py` uses the recovered `fixture()` / `execute()` / independent audit with the retained policy-4 executable and shaders. There are no builds, shader edits, changed equations, threshold/default changes, or rejected early-restart code. Four paired A/A controls per fixture alternate AB/BA across the ten existing fixtures: **80 serialized cold one-tick GPU cases**, eight per fixture. Both labels execute the same physical executable and shader files, whose hashes are checked before and after the batch. All source and fixture hashes, runtime adapter/driver identity (RTX 4070 Ti SUPER), and retained solver SHA-256 `10c5ee6541c7799119a9578b304c51f8d3de3938e2221613894bc7fae75d5c24` stay fixed. All 80 cases pass existing exhaustive physics checks. The 43 preflight CPU tests pass.

**Signatures and validation:** Exact integer geometry bits and stable entity generations form a canonical contact-set hash. Separate hashes retain contact-record order, root-contact order, color assignment, color-pass order, within-color stream order, local mapping, free-state bits, and final FP64 work state. The parser verifies complete root/colored coverage, prefix bounds, matching color labels, and disjoint bodies within each color. A color-pass hash sorts only within a verified conflict-free color; those operations are independent. Every fixture has one invariant canonical contact/geometry set and one invariant free state across all eight runs. No repeated arithmetic schedule produced different iterations or final FP64 work results. This is observed coverage, not a proof for schedules that never repeated.

| Fixture | N | Distinct color-pass signatures / 8 | Iterations min-max | Complete GPU tick min-max | GPU CV |
|---|---:|---:|---:|---:|---:|
| Chain | 16 | 1 | 452-452 | 2.55-2.57 ms | 0.18% |
| Chain | 64 | 1 | 367-367 | 2.30-2.34 ms | 0.60% |
| Chain | 256 | 5 | 4,035-4,036 | 32.37-37.98 ms | 6.93% |
| Chain | 1,024 | 8 | 4,024-4,026 | 154.64-169.29 ms | 2.95% |
| Branching | 64 | 1 | 321-321 | 2.79-2.80 ms | 0.11% |
| Branching | 256 | 7 | 1,194-1,195 | 13.91-16.64 ms | 5.04% |
| Dense | 64 | 4 | 107-107 | 1.79-2.06 ms | 4.81% |
| Dense | 256 | 8 | 417-418 | 9.49-10.30 ms | 3.08% |
| Oblique/friction | 64 | 3 | 265-309 | 4.71-5.46 ms | 6.39% |
| Oblique/friction | 256 | 8 | 816-1,087 | 24.93-32.47 ms | 8.79% |

**Observed cause and separation:** `physics.hlsl:98` scatters root contacts with atomic ranks; its serial greedy `ph_color()` consumes that order. `ph_members()` similarly assigns local indices with atomic ranks. `ph_color_ranges()` atomically permutes records within each conflict-free color. These are legal scheduling variations, not lost/duplicate contacts. In chain-256, the number of colors/batches varies between two and three despite almost unchanged iterations. Its overall tick CV is 6.93%, but pooled within-equivalent-arithmetic-schedule CV is 0.51% (five samples in two repeated cohorts). Chain-64 changes contact/within-color stream order while retaining its color passes and exactly 367 iterations. Other repeated arithmetic cohorts also retain their numerical results.

**Unchanged restart behavior is independently checked offline:** Existing trace artifacts from the preceding two tasks have identical executable and full shader hashes. Both chain-256 traces restart at 512, but their color counts differ (two versus three) and their iterations differ (4,035 versus 4,036). Both chain-1,024 traces restart at 512 and have three colors, yet different pass assignments and 4,026 versus 4,025 iterations. Chain-64 has no restart, the same color passes, and 367 iterations in both. No additional GPU trace runs were needed. The new uninstrumented timing cases do not measure per-case restart count; that boundary is explicit in JSON.

**Execution-time uncertainty:** Stricter cohorts also match contact-record placement, root indices, colored stream and local map. Their within-cohort tick CV is 0.18% for chain-16 and 0.54% for chain-64; larger exact-dispatch repeats are absent. The chain-1,024 has eight distinct schedules, so its hardware/runtime-only variation is **UNVERIFIED**, not 2.95% and not zero. Holding only iteration count and batch count gives 2.90% solver CV there, but color/order and branch-work differences still confound that number. Total tick measurements can also include upstream spatial/runtime variation. No clock, cache, bandwidth, or hardware-stall attribution is claimed.

**A/A implication:** The identical-code B/A split yields per-fixture median ratios from **0.86647 to 1.12823**, with geometric-mean ratio **0.98884** and summed-p50 ratio **0.99551**. Thus the old numerical performance thresholds alone can show an apparent aggregate gain when no optimization exists. Eight cold samples provide descriptive variation, not confidence limits or a universal noise threshold. Historical gate/retention decisions are preserved, but subpercent margins are not established speedup evidence. Future comparisons need equivalent schedule cohorts or measurement-only deterministic replay plus repeated blocked controls before using those thresholds.

**Analysis-only defect corrected:** The first exact-dispatch hash omitted contact-record placement. A focused regression now distinguishes identical semantic color work with different arena layouts. All seven signature tests pass after the fix; all 80 saved exports were reprocessed with **zero extra GPU runs**. Previous JSON/CSV analysis is preserved under `*-before-dispatch-signature-fix.*`; raw GPU exports were never replaced. This did not change the table or GPU results.

**Decision and next target:** No concrete solver-math, coverage, synchronization, or resource defect was observed; production code and defaults remain unchanged. First make contact/color scheduling reproducible for measurement. Then evaluate general color-pass reduction: chain-256 demonstrates that coloring can change work per iteration without changing contact equations. Include ordering/color construction cost in complete-tick comparisons. Do not retune restart policy against unmatched schedules. G0-G4 statuses are unchanged; G5 remains **NOT QUALIFIED**.

**Preservation/evidence:** Work is isolated in `g5-repeatability-work`, branch `g5-measurement-repeatability-20261019`; the preceding workspace's 388 file hashes and uncommitted state are unchanged. `dev-test-results/g5-repeatability-20261019T033814027715Z/` contains all raw state/contact exports, signatures, cohort statistics, JSON/CSV, asset/source/fixture manifests, device identity, unit logs, analysis-correction history, and archived-restart comparison. `measure_repeatability.py --analyze-only <results.json>` documents the one-time correction path and submits no GPU work. No GUI, screenshots, manual per-case GPU tests, full campaign, or release package was used.

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

## G6-P1 decision: immutable consumer generations (2026-10-19)

**Decision: retain as preparation only.** Isolated branch `g6-p1-state-isolation-20261019`, based on `a147f6bf265bc82060107358cd41157e38d371c2`. The original `g5-anderson-work` tree, including its three dirty binaries, is unchanged. G5 is **DEFERRED / NOT QUALIFIED**. G6 is **NOT QUALIFIED**. No solver experiment or production-policy change was made. All control/candidate DXIL files match; the retained solver source remains `10c5ee6541c7799119a9578b304c51f8d3de3938e2221613894bc7fae75d5c24`.

### Lifecycle audit and ownership contract

1. The G1 source and identity maps are borrowed producer resources. At tick start, source is copied to the existing trial. Preparation, discovery, contacts, coloring, and the unchanged FP64 solver modify trial/scratch, not the leased accepted generation (`physics.c`, `record_frame`).
2. Existing contact/body/pair/guard checks precede `ph_publish`, with UAV barriers. Its common error flag suppresses all source and persistent rolling-state writes on rejection (`physics.hlsl`, `ph_check_bodies`, `ph_publish`). Per-body source writes were safe for the serial producer but were unsuitable for an unfenced consumer retaining a raw source handle.
3. After publication, GPU copies components, the 256-byte acceptance header, identity maps, and pool accepted rolling/material fields into a free owned slot. Trial rolling fields and scratch are not published. The slot ends in COMMON. The existing submit fence owns all copies (`state-publication.inc`, `state_record_copy`). No extra tick readback, CPU wait, allocation, or upload was added.
4. `ph_decode_frame` uses the existing completed-frame header to accept the matching pending slot only after its terminal fence. Tick, epoch, published count, runtime validation, and completion replay are checked. Rejection leaves the accepted slot unchanged. Publication is a CPU-owned pointer to a completed immutable GPU resource, not a new GPU scheduler or shader-side pointer swap.
5. Leases carry runtime identity, Physics context identity, nonwrapping serial, unique acquisition nonce, buffer, ready fence, tick, GPU generation, epoch, and capacity. The fixed 64-entry table rejects stale/forged/double releases. A CPU owner releases only after all access ends. Each GPU reader registers its native-device completion fence **before submission**; release fails until that fence completes. Each independent reader needs its own lease. GPU consumers restore COMMON before completing. Owner-thread API calls are serialized; concurrent CPU calls are outside this contract.
6. Two slots are pre-admitted. Explicit reserve allows at most four. The accepted slot, pending slots, pinned slots, and fence-incomplete slots cannot be reused. Exhaustion returns error 60 before advancing the tick. There is no implicit growth, truncation, or consumer eviction. `ph_try_close` refuses live leases; the device refuses closure while Physics owners exist. Callers must drain/release consumers, close Physics successfully, then destroy storage/device.
7. Dispatch-recording failure discards only the unsubmitted packet and restores resource-state bookkeeping to its last checkpoint. Earlier split packets retain fence ownership. The Physics context becomes fail-closed; its accepted snapshot remains readable. Real submit/device-removal failures retain the runtime's existing process fail-stop boundary. They are not claimed as recoverable.
8. Structural edits require drained producers and no leases, and reseed the snapshot with the actual GPU generation/epoch. Existing CLI mutation paths check this guard. Raw `ph_read`/G1 readbacks are diagnostic borrows valid only through their documented unmap, not persistent generation leases.
9. Existing viewer code remains protected by same-queue ordering when reading source, or a separate queue wait plus per-frame copies. Frame reuse waits both compute and graphics fences (`viewer.c`, `vfinish`, `vbegin_physics`, `viewer_open`). It now reserves depth+1 publication slots and checkpoints recording state. It was compiled only, never launched. No networking implementation exists; no network integration is claimed.

### Exact bounded memory and measured cost

For capacity C, one slot is `76*C + 256 + (pool ? 160 : 0)` logical bytes: 64*C SoA components, 256-byte header, 12*C identity maps, and optionally 32-byte material plus 128-byte accepted rolling state. Each committed size comes from `GetResourceAllocationInfo`, with checked 64-bit arithmetic, UINT32 address bounds, current DXGI admission and configured reserve. `ph_ledger` includes exact publication slots/bytes/committed totals. Two default slots at tested C=32 add **131,072 committed bytes**; four slots add 262,144. Host lease storage is fixed and bounded. GPU-only test helpers additionally own one bounded readback and a secondary queue; their diagnostic copies do not run in normal ticks. Driver/queue allocation residency is not inferred from logical byte counts.

Paired unchanged-source control and candidate, NVIDIA GeForce RTX 4070 Ti SUPER; two AB/BA process pairs per workload, 32 warm samples per process, 64 per arm/workload. Times below are microseconds. CPU combined medians are measured directly, not the sum of independent medians.

| Workload | Build | GPU p50/p95 | CPU record p50 + submit p50 | CPU combined p50 |
|---|---|---:|---:|---:|
| idle | control | 262.00/265.00 | 199.80 + 12.70 | 212.50 |
| idle | candidate | 263.75/267.00 | 201.60 + 11.70 | 213.50 |
| break | control | 856.00/1036.50 | 204.30 + 15.80 | 218.90 |
| break | candidate | 761.00/1043.25 | 204.40 + 13.60 | 218.30 |
| moving | control | 398.00/399.25 | 208.70 + 15.80 | 225.10 |
| moving | candidate | 398.50/399.75 | 211.20 + 13.40 | 224.70 |

These are scoped cost measurements, not an optimization claim or sustained p95 qualification. Break/contact ordering and runtime latency vary. No large-island campaign was run. All matched complete published-state hashes agree. Full per-tick samples and publication-tail timings are retained.

### Verification, evidence boundary, and next action

`python run_g6_p1.py` builds/reuses verified artifacts and runs one serialized bounded batch. `prepare_g6_control.py` verifies the archived control or builds the frozen baseline from isolated Git sources, without editing the working tree. Evidence: `evidence/g6-p1/results.json`, `results.csv`, `comparison.csv`, `gate-G6-P1.json`, source/binary manifest, complete logs, and previous failed harness attempts, all included in the focused handoff rather than a new release package.

The final batch passes **21 process runs**: successful publication; real solver nonconvergence and rollback; validation rejection; existing admission retry; delayed GPU consumer on a second copy queue while the producer advances; unfinished/replayed completion rejection; generation reuse, stale and forged handles; slot/lease exhaustion; partial allocation cleanup and exact retirement; before/after-split recording failures; persistent pool snapshots; epoch reseeding; idle, collision, first-contact/wake, energy, discovery, ownership, generational ID reuse, and deletion/compaction regressions. D3D12 debug validation reports zero errors. Viewer integration compiles headlessly. Earlier test defects (fence test omitted the new slots; result collection key collision; assumed distinct native devices) were corrected and their failed evidence preserved.

**UNVERIFIED:** forced hardware dispatch failure, actual device removal/recovery, physically different native-device fence rejection (the tested runtime instances share Windows' native D3D12 device), sustained many-consumer operation, and new interactive rendering runs. The test proves distinct runtime/context identities across recreation, not device-loss recovery. G0-G4 evidence is unchanged; GPU-02 remains UNVERIFIED. Do not label this formal G6 qualification.

**Next action:** define and implement device-loss consumer cancellation and teardown/recovery boundaries, then qualify broader consumer integration. Keep G5 deferred; do not resume solver optimization as part of this work.

## G6-P2 decision: bounded ownership on the existing queues (2026-10-19)

**Decision: retain for local preparation.** Branch `g6-p2-resource-ownership-20261019`, based on P1 commit `603fd67506ede889bf6c7bc4b9cd034183d97ccb`. G5 is **DEFERRED / NOT QUALIFIED** and the solver, all HLSL/DXIL, production defaults, fixed ticks, tolerances and rollback equations are unchanged. G6 is **NOT QUALIFIED**. The original P1 working tree, including all four dirty binaries, remains byte-identical.

### Audit and minimal integration

The existing runtime already admits checked resource sizes against current DXGI budgets/reserves, tracks every submitted resource through its compute fence, serializes the fixed-pass producer on its direct queue, and retains allocator memory across split packets. P1 supplies bounded immutable generations. A replacement scheduler, new dispatch graph or GPU allocation pool was not needed.

The gap was explicit ownership across external work: a lease held a generation, but did not declare consumer output dependencies or distinguish prepared, submitted, cancelled and failed work. The runtime could also retire a directly held buffer without seeing a lease. The P2 implementation extends these mechanisms rather than changing dispatch scheduling:

- `ph_work_prepare` reserves an existing lease and at most three extra resource claims. Tasks share the fixed 64-entry lease table. Immutable input and publication serial are explicit. Producer-private resources and publication slots cannot be smuggled in as writable extras. Shared reads are permitted; writes are exclusive. Duplicate, stale, exhausted and partially admitted requests fail without evicting consumers. Partial claim acquisition unwinds every earlier claim.
- Runtime read/write claims block conflicting admission, retirement, copy destinations, CPU writes and readback mapping while an external writer owns the resource. This is an owner-thread contract for known engine/native submissions, not a security boundary or a validator for arbitrary user-written shader behavior. Callers remain responsible for legal D3D12 resource kinds/states and declared native accesses.
- `ph_work_submit` retains the actual native queue and completion fence on the same native device before GPU execution. An already completed fence value is rejected. The task records queue kind, ready fence, terminal fence, owner/context, ID, generation serial and dependencies. A lease is acquired only from an already completed accepted state, so no additional producer wait or GPU-to-CPU copy is needed.
- Pre-submit cancellation releases claims immediately because no GPU work exists. After submission, cancellation or failure marks a pending terminal state; it does **not** preempt GPU commands or drop ownership. `ph_work_finish` releases claims only after the registered fence completes. A failed/removed fence cannot masquerade as completion. Failed native submission with no eventual fence remains a fail-stop/recovery boundary, not a reason to discard the consumer.
- Each producer tick builds a checked, deduplicated descriptor of up to 32 dependencies, including spatial buffers, trial/meta/contact/indirect storage, upload, readback, and publication/optional render outputs. `sp_resources` exposes the existing private handle inventory for this audit. Conflicts fail before recording and before tick advancement (error 62); slot backpressure remains error 60. `ph_producer_work` returns the latest descriptor by value: callers that retain a submission audit save it before the next submission. Per-slot pending serials and fences remain owned independently. Pending producer GPU-generation counters are not accepted-state evidence; the unique publication serial is authoritative until validation.
- The producer continues on its original queue, with its existing barriers, indirect dispatches and split submissions. An external GPU reader of the previous immutable generation can overlap it on a copy/compute/graphics queue. CPU API calls remain serialized by the owning thread. There is no general concurrent-CPU or multi-device scheduler.

No additional normal-tick GPU allocation, GPU pass, CPU wait or readback was introduced. Task metadata and buffer claims use fixed host storage. The existing secondary-queue regression helper now allocates its bounded output through `s_new`, so test output admission and committed bytes are accounted too.

### Verification and measured cost

`python prepare_p2.py` verifies or rebuilds the frozen P1 control in isolated Git sources; `python run_g6_p2.py` performs one bounded serialized GPU batch with verified incremental builds. The final batch passes **22 process runs**: task conflicts and immutable writes, shared readers, delayed/concurrent copy-queue tasks, generation reuse, exhausted slots and all 64 task entries, pre/post-submit cancellation, logical failure with fence-safe cleanup, partial-claim rollback, stale handles/context recreation, already-completed fence rejection, and producer recording failure while a consumer survives. P1 publication/device tests and targeted idle/collision/first-contact/wake/energy/discovery/ownership regressions also pass. Native D3D12 debug validation reports zero errors. Viewer integration was compiled only; no GUI was launched. The initial batch's memory probes used `--warm` instead of `--warmup`; the failed harness evidence is retained.

Unchanged P1 control versus candidate, RTX 4070 Ti SUPER, two AB/BA pairs with 32 warm ticks per process (64 samples per arm/workload), microseconds:

| Workload | Arm | GPU p50/p95 | CPU record+submit p50 |
|---|---|---:|---:|
| idle | control | 266.75/269.00 | 217.50 |
| idle | candidate | 266.50/269.50 | 213.60 |
| moving | control | 406.75/408.50 | 240.10 |
| moving | candidate | 406.75/409.75 | 242.70 |

These short measurements show cost, not a claimed speedup or a sustained p95 guarantee. The independent eight-tick N=32 fixture-1 probes match full state, KKT/physics verification, **23 GPU allocations** and **1,507,328 committed bytes** in both arms. Extra GPU allocations and committed bytes from P2 are zero. The task-exhaustion check also verifies zero allocation growth across all 64 prepared tasks. Queue/driver residency is reported through DXGI where available and is not inferred from the host claim table.

### P1 break timestamp reconciliation and evidence limits

The archived P1 printed medians and p95 values reproduce their exact raw sample order statistics. The apparent 856 versus 761 microsecond difference was not a summary arithmetic mismatch. The benchmark query array is intentionally **not in chronological index order**: contact-admission markers use slots 30–38 between ordinary stage markers. The P2 batch verifies every sample using the actual chronological query sequence, telescopes all intervals to the complete-tick timestamp, and compares printed quantiles against raw samples. All checks pass; per-frame contact/iteration sequences and complete final states match across arms.

The earlier approximately 95 microsecond break execution-time mode shift is still unexplained. Clock/runtime variance is a hypothesis, not proven attribution. **Break is excluded from performance claims**, including any speedup claim based on P1. New break measurements remain in JSON/CSV with `performance_eligible: false` solely for correctness/timestamp audit. This does not resolve physical clock attribution or establish a performance gain.

Evidence: `evidence/g6-p2/results.json`, `results.csv`, `gate-G6-P2.json`, `p1-break-audit.json`, source/binary hashes, complete logs and initial failed harness attempt in the focused handoff. No full qualification campaign was run. Actual physical device-loss recovery, real hardware submission faults and sustained broad consumer integration remain **UNVERIFIED**. No networking subsystem or solver optimization was added.

**Next action:** establish device-loss consumer teardown/recovery and qualify actual application consumers through this ownership API. Keep G5 deferred and do not treat this preparation breakpoint as formal G6 approval.

## G6-P3 decision: actual GPU render consumer (2026-10-19)

**LOCAL PREPARATION PASS. G5 remains DEFERRED / NOT QUALIFIED. Formal G6 remains NOT QUALIFIED.** This integrates the existing application renderer, PSOs, D3D12 queues and P2 ownership API. It does not introduce a scheduler or change contact equations, global ticks, solver policies, KKT criteria or rollback.

### Accepted generations, bindings and ownership

`vaccept_physics()` in `render-consumer.inc` observes the existing producer fence and completed-frame validation header before rendering a new physics generation. It reuses that header/result in `vfinish()` rather than decoding twice. Rejected ticks are withheld before draw submission and retain the normal interactive `TICK_REJECTED` event. The renderer can still consume the last accepted generation after failure. This adds an explicit pre-submit CPU acceptance boundary; it does not add a full-state readback or physics readback allocation.

`vrender()` in `viewer.c` prepares a P2 task, binds only its immutable snapshot dependency for body, header and entity-map access, registers the native consuming queue and reserved graphics completion fence with `ph_work_submit()` **before** `ExecuteCommandLists()`, and issues an explicit graphics-queue `Wait()` on the producer readiness fence. The header starts at byte `64*C`; maps start at `64*C+256`. Producer-private G1 handles are not render bindings. Snapshot compatibility flags remain accepted, but the normal rendering path now always uses immutable generations.

Task claims cover the snapshot, diagnostics, diagnostic/timestamp readbacks and HUD, plus optional capture or headless statistics output. `PH_WORK_EXTRA` rises from three to five, a bounded host-only metadata increase. Native targets retain the existing frame owner: target index, resize epoch and `back_fence` are reserved before execution; allocator, query and PSO reuse stays protected by the existing frame fences. This is explicit frame ownership, not a claim that native targets are runtime buffer handles. `vconsumer_release()` finishes only after GPU completion, before CPU maps write-claimed readbacks. Close drains both existing queues, then cancels prepared tasks or finishes failed submitted tasks before resource destruction. Healthy-device cancellation remains non-preemptive. Producer queue-kind metadata now comes from the actual native queue descriptor instead of assuming a direct queue.

The old renderer verified pool command status through an offset outside the compact publication header. The versioned pool export now contains 160 persistent bytes plus four command-status bytes (`POOL_SNAPSHOT_BYTES=164`); seed status is explicitly zero. The generated viewer constant ABI is version 3 and exports the command offset. All 32 physics DXIL binaries match the frozen control exactly. Default per-frame SoA copies and the separate render map allocation are removed. Solver shaders and physics equations remain unchanged.

### Actual headless proof and matched cost

Run `python run_g6_p3.py` from this working tree. It builds or reuses verified source/tool/options/output caches, then serializes one bounded CLI batch. Fourteen process runs pass: actual renderer consumer, publication, ownership, five targeted pool regressions, four matched render timings, and two independent physics/memory checks. Full evidence is in `evidence/g6-p3/results.json`, `results.csv`, `gate-G6-P3.json` and process logs, included in the focused ZIP. Earlier build/cache adapter failures and superseded comparisons are retained separately; root results are authoritative.

The real consumer uses the application's `vrender()`, shaders and `DrawInstanced()` into an offscreen native target. It creates no window, calls no Present, and reads no pixels. Pipeline statistics verify 99 vertex invocations per draw and actual fragment execution; the functional test verifies 495 vertex invocations across five validated draws and all 16 body identities. GPU-based validation reports no errors. A delayed render holds generation 1 while the producer completes generation 2; a further producer is backpressured. Poisoning private body, map and metadata buffers does not affect the immutable draw. The batch also verifies initial/updated pool status, prepared cancellation, queued cancellation/failure with deferred release, stale ownership, rejected-tick withholding and continued access to the accepted generation. Injected failures are not physical driver faults.

The control uses frozen P2 physics/runtime sources and original asynchronous render-submit ordering, with a common offscreen/query adapter and shader ABI. It is not a byte-identical interactive P2 executable. Both arms use the same offscreen instrumentation, fixture and device (RTX 4070 Ti SUPER), two AB/BA repeats, 16 timed frames each plus warmup: 32 samples per arm.

| Metric | P2 control p50 / p95 | P3 p50 / p95 |
|---|---:|---:|
| Complete physics GPU tick, us | 1259 / 1690 | 1174 / 1870.25 |
| GPU render, us | 18.432 / 18.848 | 18.432 / 19.456 |
| CPU record + submit, us | 434.5 / 471.3 | 450.9 / 799.6 |
| Pre-submit acceptance wait, us | 0 / 0.10 | 1131.8 / 2026.2 |
| Render-test committed bytes | 2,883,584 | 2,686,976 |
| Render-test committed-resource allocations | 42 | 39 |

The change saves 196,608 committed bytes (192 KiB) and three allocations in this fixture. GPU render p50 is unchanged. CPU record/submit p50 rises 16.4 us; acceptance blocking moves before draw submission and is reported separately, included in total stall accounting. These short local samples do not establish a speedup or sustained latency guarantee. Render allocations distinguish runtime buffers from native targets in raw JSON. Independent 32-body physics probes match exact final state and remain at 1,507,328 committed bytes and 23 runtime allocations. Original P2 dirty files and all recorded tracked hashes remain unchanged. P1/P2 break timestamp mode attribution is still unresolved; no break performance claim is made here.

### Device-loss and qualification boundary

Physical removal/recreation is **UNVERIFIED**. On device loss, stop new submissions. A fence completion value of `UINT64_MAX` must not count as success. Cancel unsubmitted tasks; keep submitted leases pinned until healthy completion or explicit removed-device teardown establishes that GPU use is impossible. Do not fake-signal completion to recycle generations. The current runtime is fail-stop and does not implement that forced-loss ownership teardown. A complete recovery must retire frame/UI/native targets and queues/PSOs/resources safely, recreate devices/queues/fences/resources and generation namespaces, and restore an authoritative checkpoint or new scene; retained GPU data is not promised across removal. This batch tests logical cancellation/failure on a healthy device only.

Normal renderer code is integrated, but interactive presentation, networking consumers, sustained broad workloads and actual device-loss recovery remain unqualified. Next: test the explicit removed-device teardown boundary before formal G6; keep G5 deferred.

## G6-P4 decision: deferred consumption on existing frame ownership (2026-10-19)

**LOCAL PREPARATION PASS; performance tradeoff recorded. G5 remains DEFERRED / NOT QUALIFIED. G6 remains NOT QUALIFIED.** This removes ordinary render submission's current-tick acceptance wait. No physics source, shader output, equations, solver policy, KKT criterion, timestep or rollback rule changed.

### Dependency audit and minimal change

The P1 accepted slot already remains valid while another slot is pending. `ph_state_acquire()` only leases an accepted slot whose readiness fence completed; `state_complete()` alone advances that pointer after completed-header validation. P2 `ph_work_prepare()` already acquires this accepted generation even while a producer is pending. Therefore the current-tick `vaccept_physics()` call at the start of P3 `vrender()` is not a dependency of an ordinary draw. It was a dependency only if the draw had to show that exact tick.

`vrender()` now leases the last accepted generation and uses that lease's generation, tick, maps and immutable buffers throughout recording. Required producer-readiness queue waits, dependency registration before execution and completion-bound leases are unchanged. Validation/promotion of the pending tick is deferred to existing `vfinish()` retirement. A rejected tick may complete while an older accepted image is displayed; its own state is never rendered or promoted. Rejection still stops simulation and preserves the accepted snapshot. `vconsumer_prepare()` records snapshot age as `ph_next_tick() - leased_generation` and fails closed on a future generation.

`vbegin_physics()` opportunistically retires older frame slots only when both existing queue fences are ready, in submission order. `vrecord_physics()` handles publication-slot exhaustion through at most the existing frame depth's retirements/retries, then fails explicitly. It does not create a queue, task allocator or scheduler. Delayed GPU consumers retain ownership; no consumer is discarded to make space. Normal renderer and interactive submission sites use this same helper.

Command-bearing frames deliberately retain the P3 matching-tick acceptance path: `p_complete()` currently uses that draw's exported command-status word for shot acknowledgement. Using an older word could mislabel a committed or blocked shot. Removing this remaining command-frame wait requires separating that acknowledgement dependency and is outside this minimal change. Render-only and ordinary physics frames do not need it. Physics impact events now identify the validated simulation generation, rather than labeling them with the older rendered generation. The stale `work-ownership.h` comment now states the implemented limit of five extra resources.

### Bounded actual-GPU verification

Reproduce with `python run_g6_p4.py`. The script builds/reuses verified artifacts, runs GPU cases sequentially with 60-second process timeouts, and saves complete logs/JSON/CSV. Final evidence has eleven passing test records: six final process runs and five passing tests reused only after exact executable hash and invocation checks. The first attempt's failed P3 harness assumption is archived under `harness-contract-failure`: that case did not identify itself as command-bearing while expecting synchronous rejection. It now explicitly tests command acknowledgement; the separate P4 test covers deferred rejection. No physics correctness criteria were changed.

The real renderer completes two actual offscreen GPU draws while the physics queue is held behind an unsignaled native fence. Both read the accepted generation, with ages one and two ticks; neither needs the pending tick's readiness fence. The same test verifies full 16-body coverage, stale task/lease rejection, generation reuse, all 64 leases exhausted without allocation growth, capacity rejection without tick advancement, rejected-state withholding, continued rendering of the accepted state, delayed cancellation and complete cleanup. It records 495 vertex invocations and zero debug errors. The retained P3 consumer test adds 495 actual vertex invocations, poisoned private-buffer isolation, prepared cancellation and submitted failure cleanup. Publication/ownership plus pool idle, collision and energy regressions pass on unchanged binaries. No window, Present, pixel readback or screenshot is used.

`evidence/g6-p4/results.json`, `results.csv`, `nonblocking.json`, `consumer-lifecycle.json`, `gate-G6-P4.json` and full logs are the evidence. All recorded original P3 file hashes and dirty status remain unchanged. Every DXIL output and physics source matches that original working tree.

### Matched measurements and limitations

Both arms use the same fixture, shaders, existing D3D12 renderer and common headless telemetry. `G6_P3_BLOCKING_CONTROL=1` selects the P3 current-tick wait and disables the new retirement/retry policy; it is a matched blocking-policy control, not the archived byte-identical P3 executable. Two AB/BA process pairs provide 32 timed frames per arm after warmup, with a real draw and full identity verification each frame.

| Metric | Matched P3 p50 / p95 | P4 p50 / p95 |
|---|---:|---:|
| CPU pre-submit acceptance wait, us | 366.5 / 583.7 | 0 / 0 |
| CPU record + submit, us | 363.5 / 628.1 | 341.1 / 560.4 |
| CPU complete handoff call, us | 751.3 / 1028.1 | 347.0 / 565.2 |
| Complete physics GPU tick interval, us | 602.5 / 801.75 | 786.5 / 873.75 |
| GPU render interval, us | 16.384 / 16.448 | 22.528 / 25.6 |
| Snapshot age at submission, ticks | 0 / 0 | 1 / 1 |
| Inclusive CPU frame blocking, us | 366.6 / 584.0 | 431.7 / 658.6 |
| Committed bytes | 2,686,976 | 2,686,976 |
| Runtime buffers + native target allocations | 37 + 2 | 37 + 2 |

The existing raw field named `retirement_blocking_us` is the inclusive frame backpressure quantity, including any earlier acceptance wait. The table labels its actual meaning; do not treat it as a measurement of pure late-retirement wait. Complete handoff wall time includes validation/recording/submission work; record-plus-submit excludes acceptance blocking. Completion waits still occur at frame reuse, drain and bounded resource pressure. Removing submission blocking does not remove GPU completion cost.

P4 improves CPU handoff latency in these samples but has larger measured GPU intervals and an older image. Concurrent queue activity can extend timestamp intervals; this batch does not prove that as the cause or establish a total-throughput improvement. Do not replace the matched 366.5-us control with P3's historical 1.13-ms sample: these are separate local runs with different timing distributions. The earlier P1/P2 break attribution discrepancy remains unresolved and is not used for performance claims.

The change adds bounded host metadata only, no GPU buffers or copies. One tick of normal measured snapshot age is 7.8125 ms of simulation time at the unchanged 128-Hz tick, not measured display latency. The gated test demonstrates two ticks; this is not a universal presentation-latency bound. Interactive display, broad sustained workloads, hardware submission faults and physical device removal/recreation remain UNVERIFIED. P3's fail-stop teardown requirements remain in force. Next: the separately scoped removed-device ownership teardown/recovery qualification, without resuming G5.

## 13. Verification and low-cost test workflow

**Code:** `physics_verify.c`, `physics_tests.c`, `tests.zig`; on the playable branch `dev_test.py`, `test_dev_workflow.py`, and the billiards test scripts.

Validation has several levels:

1. **Unit contracts:** Checked arithmetic, entity identity, mappings, generation reuse, and transaction rollback.
2. **Small analytical physics tests:** Head-on and oblique impacts, friction, rails, energy and momentum checks.
3. **GPU correctness runs:** Contact count, island size, residuals, guard regions, rejected-state behavior, and resource ownership.
4. **Comparative performance:** Identical fixtures and hardware; separate CPU, GPU, renderer, and presentation costs.
5. **Full gate qualification:** Broader workload coverage and a recorded report. It is not part of every code edit.

For routine physics work, use the **headless CLI**. The playable branch's `python dev_test.py` supports quick, affected-file, and full levels. Its build cache hashes the source dependency graph, compiler, options, and output artifacts; it must not trust timestamps alone.

**Bounded deterministic measurement mode (2026-10-19):** `measurement-schedule.hlsl`, enabled only by `G5_DETERMINISTIC_MEASURE=1`, canonicalizes complete contact records and their FP64 impulse arrays by stable entity identity before rebuilding the graph. Serial member ranks, root-contact placement, and within-color ranges remove atomic placement variability. Existing greedy coloring and the solver shader remain unchanged. This mode admits fixture 0, flags 0/2, at most 1,024 bodies and 2,048 contacts, and one connected collision island. Additional newly discovered contacts after the first graph round and unsupported inputs fail explicitly before publication. It is a bounded measurement aid, not a new production scheduler. It uses existing buffers; linked lists are rebuilt immediately after sorting before their next use.

`G5_MEASURE_TIMESTAMPS=1` brackets admission, member construction, contact scatter, and color ranges with eight extra timestamp queries inside the existing 64-query allocation. The normal build remains at 40 queries. The bracket sum includes original dispatch, UAV barriers, and bookkeeping; comparison with identically instrumented native scheduling estimates additional scheduling cost. Complete tick time includes this cost. No GPU-to-CPU synchronization was added between stages. Default-off C preprocessor tokens and all four affected default-off DXIL outputs match the retained control. The solver source hash remains `10c5ee6541c7799119a9578b304c51f8d3de3938e2221613894bc7fae75d5c24`.

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
| **G5** | Large islands, convergence, robust solver performance | **DEFERRED / NOT QUALIFIED** | Bounded Anderson acceleration reduced work on several fixtures but lost convergence in eight previously converging configurations. Rejected; exact retained solver and all production defaults preserved. |
| **G6** | Reproduce all gates, approve an engine foundation | **NOT QUALIFIED; G6-P1/P2/P3/P4 preparation only** | G5 deferred. Local publication tests do not qualify G6 or approve an engine foundation. |

### Current G5 decision (2026-10-18)

**Finding:** The residual-gated policy 4 remains an opt-in, locally tested convergence candidate. The latest experiment targeted memory cost in its 1,024-body one-workgroup solver. Group-shared body caching improved the large chain from 170.13 ms to 152.69 ms per attempted complete tick, without changing the 4,025–4,026 required iterations. However, it was slower on several other networks and **failed the predeclared equal-fixture aggregate criterion** (geometric mean +4.25%, despite sum of p50 times −4.82%). The experiment does not prove a particular DRAM bottleneck because GPU hardware counters were unavailable.

**Decision: REJECT GENERAL BODY CACHE; G5 STILL OPEN.** Keep `G5_BODY_CACHE=0`, production policy 1, and all previously qualified solver limits and rollback. Do not infer a sustained 1,024-body performance improvement or label the reported logical load counts as measured physical GPU bandwidth.

**Next action:** Characterize the remaining per-iteration solver cost with headless CLI and available static shader analysis; if permitted GPU counters can be obtained later, use them only to validate a concrete hypothesis. Avoid GUI work, repetitive runs, and large campaigns. Implement a single small change only when the evidence identifies an avoidable cost and complete-tick correctness can be retained.

**Evidence reference:** `G5-Global-Solver-Cost-Handoff-20261018T090324676154Z.zip`, 2026-10-18. Submitted local evidence: 100 timing trials, 22 diagnostic probes, 22 unit tests, 50 verified summary rows. Source and test evidence were reviewed; Windows D3D12 execution was not independently rerun here.

### G5 deterministic measurement decision (2026-10-19)

**Decision: RETAIN MEASUREMENT MODE ONLY; G5 STILL OPEN.** Branch `g5-deterministic-measurement-20261019` preserves the retained snapshot-reuse/skipped-residual baseline. No solver equations, policies, thresholds, KKT criteria, iteration limits, or production defaults changed. The rejected early-restart patch was not reapplied. Original workspace status and 390 snapshotted file hashes remain identical.

**Local evidence:** `dev-test-results/g5-deterministic-20261019T035548203177Z/results.json` and `summary.csv`, RTX 4070 Ti SUPER. One serialized headless batch executed 180 trials: eight deterministic policy-4 repeats per fixture, two native policy-4 references, and two deterministic repeats for each policy 0–3. The same CLI and fixed per-policy shader bytes were checked before and after execution. Independent audits verified complete fixture contacts, actual single-island size, conflict-free coloring, KKT, energy/momentum, impulse reconstruction, and rejection rollback. All deterministic schedule and FP64 work/published-result signatures were identical within each fixture/policy; iteration counts were constant. Of 160 deterministic trials, 150 converged. Ten expected nonconvergent attempts retained explicit failure and exact rollback: policy 0 chains 64/256/1,024 and policy 2 chains 256/1,024, two each. All 20 native references converged. Two additional unsupported-envelope trials (1,025 bodies and two islands) returned error 64, no publication, and byte-identical rollback. The initial 48 unit tests and five focused post-setup-fix tests passed.

Policy-4 timings below are milliseconds, eight cold one-tick repeats. Schedule/native columns are separately bracketed stage medians (native has two samples). Total tick includes scheduling; different native arithmetic orders prevent treating its timing difference as an optimization result.

| Fixture / bodies | Contacts | Iterations | Tick p50 | Schedule / native | Tick CV | Solver CV |
|---|---:|---:|---:|---:|---:|---:|
| Chain / 16 | 15 | 452 | 3.144 | 0.018 / 0.009 | 7.52% | 8.71% |
| Chain / 64 | 63 | 367 | 2.855 | 0.049 / 0.009 | 12.78% | 9.46% |
| Chain / 256 | 255 | 4,035 | 36.246 | 2.985 / 0.011 | 1.74% | 0.39% |
| Chain / 1,024 | 1,023 | 4,024 | 194.935 | 46.954 / 0.017 | 2.11% | 1.79% |
| Branching / 64 | 63 | 321 | 3.772 | 0.048 / 0.009 | 6.42% | 12.84% |
| Branching / 256 | 255 | 1,194 | 19.115 | 3.764 / 0.011 | 4.30% | 2.22% |
| Dense / 64 | 112 | 107 | 3.388 | 0.535 / 0.009 | 15.26% | 7.78% |
| Dense / 256 | 480 | 417 | 19.715 | 9.182 / 0.011 | 18.57% | 4.32% |
| Oblique / 64 | 112 | 287 | 5.809 | 0.077 / 0.011 | 9.23% | 8.74% |
| Oblique / 256 | 480 | 1,016 | 37.972 | 10.282 / 0.013 | 10.57% | 2.11% |

**Remaining uncertainty:** Canonical arithmetic is repeatable on this device/toolchain, not proven across hardware or compilers. GPU execution time remains variable; the 1,024-body solver spans 139.626–147.381 ms with identical 4,024 iterations. CPU record+submit medians span 3.279–3.443 ms across fixtures. Serial insertion-sort work depends on incoming atomic order even though its output is canonical; its cost is O(C²), measured separately, and unsuitable for production. Cold samples do not establish sustained timing, p99, or a thermal/clock cause. No cache/counter attribution is claimed. The next justified optimization target remains the unchanged FP64 color-pass solver; compare fixed arithmetic schedules and solver brackets, not schedule-construction time or random-order complete ticks. Multi-island and later-discovery replay remain outside this bounded tool's verified scope.

**Reproduce:** `python measure_deterministic.py` uses the verified `dev_test.py` build cache and retained control-policy artifacts from `dev-test-results/g5-early-restart-*/results.json`. It builds one instrumented CLI and only four affected shaders for each scheduling arm, reuses other artifacts, serializes cases with timeouts, and writes raw exports plus JSON/CSV. The successful run reused its CLI after two setup-only failures (log-header comparison and pre-existing setup directory); no GPU cases were repeated. Preserved setup failure files, including the stale `failure.json`, are superseded by the successful `results.json`. This is not a standalone release/recovery package.

**Previous handoff hash erratum:** The delivered `source/measure_repeatability.py` in `G5-Measurement-Repeatability-20261019.zip` hashes to `c4fb504149ef21d585e320da79cc5a7664462ebab3d76e8b8aa3b8917ef17643`, matching its `final-source-hashes.json`. Supplemental `preservation-and-aa-summary.json` incorrectly recorded `52c21a5af359967e4276a7a848282418bdd9c7deead3efba476035edbbf6dbed`. The old archive is preserved. Its initial execution-time helper hash remains **UNVERIFIED** because it was not recorded then. This batch records and verifies source/helper hashes before and after GPU execution; the machine-readable erratum is `dev-test-results/previous-handoff-hash-reconciliation.json`.

G0–G4 statuses remain frozen; GPU-02 remains unverified, G5 unqualified, and G6 unauthorized.

### G5 post-color synchronization experiment (2026-10-19)

**Decision: REJECT; exact retained solver restored.** Branch `g5-color-boundary-measurement-20261019` tested one narrow correction. On the global-memory path, `applyColor()` ends each nonempty color batch with `DeviceMemoryBarrierWithGroupSync()`. The outer iteration and reconstruction then repeat that barrier before residual reads. Greedy coloring guarantees a populated final color. The candidate skipped only these two duplicate boundaries when `localMode!=1 && colors>0`; local-cache and zero-color boundaries stayed unchanged. All equations, policies, projection, KKT limits, residual scans, and work limits stayed unchanged. Schedule construction remained test-only and unchanged. The candidate is preserved as `experiments/g5-color-boundary-20261019.patch`, not active solver code.

**Source/DXIL evidence:** The 1,024-body fixture has color sizes 512/511: eight color-batch barriers per sweep, followed by the redundant boundary. Its 4,024 iterations and 503 scheduled reconstructions expose 4,527 removable dynamic boundaries. This is a source-derived count, not measured stall time. Policy-4 DXIL retains 20 static barrier call sites but adds conditional branches around the two outer sites; fewer static calls were not claimed. All five macro-disabled controls reproduced the previous DXIL hashes exactly. The same cached instrumented CLI and scheduling shaders served both arms; only solver shaders were compiled. No new allocation, CPU synchronization, or production scheduling change was introduced.

**Local batch:** `dev-test-results/g5-color-boundary-20261019T041659906648Z/results.json`, `summary.csv`, and raw exports, RTX 4070 Ti SUPER. One serialized 240-trial batch used eight paired policy-4 samples on all ten existing fixtures and one paired sample for each policy 0–3. Each pair matched complete contact/color/local/arithmetic schedules, iterations, FP64 work state, accumulated normal/tangent impulses, and published state exactly. Existing independent coverage, coloring, KKT, energy/momentum, and impulse-reconstruction checks passed. Each arm had 115 converged attempts and five expected rejected attempts with exact rollback (PGS chains 64/256/1,024; policy 2 chains 256/1,024). There were no errors/timeouts. A targeted source contract failed before editing as expected; 46 preflight unit checks and 49 restored-baseline checks passed.

Policy-4 chain 1,024, medians of eight samples per arm:

| Metric | Control | Candidate |
|---|---:|---:|
| Actual contacts / iterations | 1,023 / 4,024 | 1,023 / 4,024 |
| Schedule construction brackets | 44.872 ms | 44.949 ms |
| Solver execution | 147.503 ms | 143.696 ms |
| Complete GPU tick | 193.720 ms | 191.815 ms |
| CPU record + submission | 3.348 ms | 3.394 ms |

**Uncertainty and rejection:** The median solver difference is −2.58%, but the paired geometric ratio is 0.98847 with exploratory paired-bootstrap 95% interval [0.97077, 1.00718]. The predeclared rule required a gain greater than max(3.6%, same-batch control A/A deviation), plus an interval below 1 and aggregate complete-tick improvement. The observed control A/A floor was 4.36% (four adjacent pairs; its nearest-rank p95 is the maximum, not a stable tail estimate). Equal-fixture complete-tick ratio was 0.99812 [0.97173, 1.02548]. Neither test passed. The 256-body chain's solver increased slightly, 32.021→32.117 ms; other local-cache fixtures showed timing shifts despite unchanged synchronization behavior. Schedule sorting still depends on incoming atomic placement, so its runtime varies despite identical canonical output. Cold samples and bootstrap intervals do not prove thermal stability, sustained latency, or a hardware cause. Do not call this a retained speedup.

The active shader again hashes to `10c5ee6541c7799119a9578b304c51f8d3de3938e2221613894bc7fae75d5c24`. Original workspace status and all 393 snapshotted file hashes remain unchanged. The executed candidate scripts, source, tool/binary hashes, predeclared rule, disassembly, and restoration proof are archived with the batch. To reproduce, apply the rejected patch only in a separate copy of the deterministic baseline, initialize `dev-test-results/color-boundary-current.txt` to a new batch directory, copy the retained shader there as `control-projected_solver.hlsl`, then run `python measure_color_boundary.py`; the prior deterministic control artifacts are required. Do not apply this patch to production.

**Next target, not implemented:** The unchanged 4,024-iteration FP64 contact/color loop still dominates. Inspect contact-local body reloads between relative-velocity evaluation and impulse application, preserving the updated normal-before-tangent state. Redundant barrier removal alone did not demonstrate a reliable end-to-end gain. G0–G4 remain frozen, G5 unqualified, and G6 unauthorized.

### G5 contact-local FP64 body-load reuse (2026-10-19)

**Decision: REJECT INCONCLUSIVE LARGE-ISLAND GAIN; retained shader restored.** Branch `g5-contact-snapshot-20261019` tested one narrowly scoped candidate. Normal relative-velocity evaluation, normal impulse application, tangent evaluation, and tangent impulse application repeatedly load the same two bodies. Conflict-free coloring guarantees no competing body writer within a color. The candidate loaded two contact-local `Body` snapshots, mutated them with the normal impulse, then used those updated FP64 velocities for tangent evaluation and application. It preserved both ordered stores, wake operations, all color and outer barriers, impulse projection, KKT checks, policies, work limits, and rollback. Reconstruction and residual measurement were unchanged. There was no cross-contact cache, allocation, CPU synchronization, or production scheduling change. Rejected barrier and early-restart changes were not reapplied.

**Static evidence:** Policy-4 compiled DXIL has 191→160 static buffer-load call sites, 153→153 FP64 add/subtract/multiply/divide instructions, and 20→20 barrier sites. This is static evidence for removed repeated loads, not a dynamic transaction, bandwidth, or stall measurement. The compiler uses legacy `bufferLoad`; the zero `rawBufferLoad` counts in `prepared.json` do not mean zero GPU loads. `static-load-analysis.json` records the correct lowering. Macro-disabled controls for all five policies reproduced the retained DXIL hashes exactly. Both arms reused the same fixed instrumented CLI and canonical scheduling shaders. Only ten small solver shader variants were compiled.

**One bounded headless batch:** `dev-test-results/g5-contact-snapshot-20261019T043158954533Z/results.json`, `summary.csv`, raw exports, and disassembly; RTX 4070 Ti SUPER. Eight paired policy-4 trials per existing fixture plus one paired trial for each policy 0–3 produced 240 attempts. All chain (16/64/256/1,024), branching (64/256), dense (64/256), and oblique/frictional (64/256) fixtures retained exact contact/color/local/arithmetic schedules, iterations, FP64 work-state and normal/tangent impulse hashes, and published-state hashes. Existing independent KKT, energy/momentum, contact coverage, conflict-free coloring, and impulse reconstruction checks passed. Each arm had 115 converged attempts and five expected rejections with exact rollback: PGS chains 64/256/1,024 and policy 2 chains 256/1,024. No errors or timeouts occurred. The focused source contract failed before editing as expected; 46 preflight checks and 49 restored-baseline unit checks passed.

Policy-4 1,024-body chain, eight cold samples per arm:

| Metric | Control | Candidate |
|---|---:|---:|
| Actual contacts / iterations | 1,023 / 4,024 | 1,023 / 4,024 |
| Schedule construction brackets | 45.850 ms | 46.994 ms |
| Solver execution | 142.926 ms | 138.685 ms |
| Complete GPU tick | 192.734 ms | 189.745 ms |
| CPU record + submission | 3.505 ms | 3.516 ms |

**Acceptance and uncertainty:** The median solver difference is −2.97%, but the paired geometric ratio is 0.97491 with exploratory paired-bootstrap 95% interval [0.94898, 1.00296]. The predeclared primary criterion required a gain above max(previous 4.3576% A/A floor, current A/A deviation), and an upper interval bound below 1. Current adjacent control A/A pairs gave a 5.3183% floor; the candidate failed both primary conditions. Equal-fixture complete-tick ratio was 0.96623 [0.93714, 0.99502], passing the separate aggregate condition. Aggregate improvement does not override an inconclusive primary large-island result. Some workloads improved (oblique 256 solver 25.352→24.354 ms), but that does not establish the requested large-island gain. The four-pair nearest-rank A/A p95 is the maximum of four observations, not a stable tail estimate. Cold samples and bootstrap bounds do not prove sustained performance or hardware causes. Schedule construction remains test-only, variable in cost, and included in complete ticks.

**Preservation and reproducibility:** The exact active shader hash is again `10c5ee6541c7799119a9578b304c51f8d3de3938e2221613894bc7fae75d5c24`. Original workspace status and all 394 snapshotted file hashes remain unchanged. `experiments/g5-contact-snapshot-20261019.patch` archives the rejected candidate and reused paired driver. The batch archives exact executed source/helper hashes, fixed binaries/tool provenance, predeclared rule, disassembly, raw numerical exports, and restoration proof. To reproduce only in another isolated deterministic-baseline copy, initialize a new directory and `dev-test-results/contact-snapshot-current.txt`, copy the retained shader into that directory as `control-projected_solver.hlsl`, apply the archived patch, and run `python measure_contact_snapshot.py`. Existing deterministic artifacts from `g5-deterministic-20261019T035548203177Z` are required. Do not apply the rejected patch to production. This complete architecture record is carried on the GitHub working branch at this breakpoint; no merge into `main` or gate approval is implied.

**Remaining bottleneck:** The 4,024-iteration FP64 contact/color loop still dominates solver cost. Repeated loads exist, but their removal did not establish a gain beyond the measured large-island timing uncertainty. No further solver optimization or campaign was attempted. G0–G4 remain frozen, GPU-02 unverified, G5 unqualified, and G6 unauthorized.

### G5 algorithmic convergence / bounded Anderson experiment (2026-10-19)

**Decision: REJECT CONVERGENCE REGRESSIONS; retained shader restored exactly.** Branch `g5-convergence-anderson-20261019` analyzed the residual histories, contact equations, color dependencies, and one concrete algorithmic candidate. Production policy 1, accepted body-snapshot reuse and skipped overwritten residual scans remain unchanged. Rejected load, barrier, and early-restart changes were not reapplied.

**Why about 4,000 iterations:** Exported 1,024-body fixture data proves unit inverse masses, 1,023 adjacent collinear contacts, and normal diagonal 2. In its settled, positive-impulse/zero-tangent active set the normal operator is `tridiag(-1,2,-1)`. Its smallest eigenvalue is 0.00000941238 and condition number about 424,971. The red/black PGS spectral radius is about 0.99999059: local color updates propagate long-range error slowly. This model is specific to the verified linear chain regime, not an assumption for general frictional networks. Policy 4 then spends 512 adaptive iterations before its unchanged restart and about 3,512 fixed-SOR iterations. The matched deterministic residual fit is 0.99500435 per step, close to the 0.995 SOR damping envelope; 64 steps retain about 72.6% of the error. Reducing the remaining error to the unchanged roughly 3.8e-9 low-speed KKT tolerance therefore takes thousands of sweeps. There is no evidence here of FP64 cancellation or an incorrect impulse equation. Shorter branching/dense networks contract much faster. Raw traces and both historical and matched fits are archived. See the linear-method assumptions in [Netlib Templates](https://www.netlib.org/templates/templates.html); this does not prove those assumptions for changing frictional active sets.

**One proposed correction:** Opt-in `G5_ANDERSON=1` tested depth-one Anderson mixing of the existing eight-sweep projected-impulse map `F`, using `r=F(x)-x` and `gamma=((r-r_prev) dot r)/||r-r_prev||²`. The trial is `project(F-gamma*(F-F_prev))`; gamma is finite and bounded to ±32. Projection preserves nonnegative normal impulses and existing tangent bounds. Each trial reconstructs velocities with the original color order and equations. It is accepted only if absolute projected residual strictly improves and normalized KKT does not worsen; rejection restores the unaccelerated checkpoint and reconstructs it. History resets on relaxation changes/restart. This is a safeguarded experiment inspired by [Walker and Ni](https://epubs.siam.org/doi/10.1137/10078356X), not a claim that their linear/full-history results guarantee convergence for this projected depth-one friction map.

**Expected cost and safeguards:** Three FP64 impulse vectors use 48 bytes per actual contact in checked unused contact-record bytes, plus 2,048 group-shared bytes. Uint64 arithmetic reserves all trace and diagnostic records before reuse; no resource allocation or production layout/scheduling change was introduced. At most 64 trials are allowed. Input/history scans cost three contact-pass credits per eight-sweep block; each trial reserves six further credits covering trial and rejection restoration. PGS sweeps plus charged work never exceed the original limit. Sleeping islands or insufficient scratch select the unchanged path. These fallback branches were source-checked but not separately device-qualified in this rejected experiment. Changing active sets, nearly dependent histories, multiple slow modes, conservative max-residual rejection, and trial cost were identified before execution as failure modes. A failed overall solve still rejects and rolls back; fallback is not permission to extend work limits.

**One local headless comparison:** `dev-test-results/g5-anderson-20261019T045105679543Z/results.json`, `summary.csv`, `residual-traces.json`, and `decision-review.json`, RTX 4070 Ti SUPER. There were 240 timing attempts (eight matched policy-4 pairs per fixture; one pair for each policy 0–3) plus 20 matched residual probes in the same serialized batch. The CLI and canonical scheduling shaders were reused. All five disabled controls reproduced the retained solver DXIL hashes exactly. Preflight first caught an equivalent-condition rewrite that changed control DXIL; the original expression was restored before any GPU cases. The stale zero-case setup failure is preserved and superseded by the completed results. All measured contact/color/free-state schedules matched; each arm's iterations and FP64 results were repeatable. Independent coverage, coloring, projection, KKT, energy/momentum, and impulse reconstruction checks passed for accepted attempts; all rejected attempts preserved rollback. Trace and timing probes agreed on iteration counts/statuses. There were no process errors/timeouts. Preflight unit checks: 46 passed; restored-baseline checks: 49 passed.

Policy-4 results below distinguish successful solves from rejected attempts:

| Fixture / bodies | PGS sweeps control → candidate | Candidate charged work | Candidate result | Solver ms control → candidate |
|---|---:|---:|---|---:|
| Chain / 16 | 452 → 65 | 67 | Converged | 2.626 → 1.271 |
| Chain / 64 | 367 → 664 | 597 | Converged, slower | 2.431 → 4.542 |
| Chain / 256 | 4,035 → 3,397 | 699 | **Rejected** | 32.053 → 28.479 attempted |
| Chain / 1,024 | 4,024 → 3,445 | 651 | **Rejected** | 143.393 → 130.096 attempted |
| Branching / 256 | 1,194 → 357 | 313 | Converged | 12.168 → 4.701 |
| Dense / 256 | 417 → 64 | 66 | Converged | 6.812 → 1.492 |
| Oblique / 256 | 1,016 → 235 | 220 | Converged | 25.335 → 6.888 |

The 1,024-body attempted complete tick was 193.555→178.800 ms, schedule brackets 46.518→47.905 ms, and CPU record+submit 3.468→3.341 ms. Its candidate final KKT ratio was **107.98**, versus control **0.9830**; 3,445 sweeps + 651 credits exhausted the unchanged 4,096 budget. The 256-body candidate likewise exhausted 3,397 + 699 with ratio **185.66**. Both retained the 512-sweep restart; candidate post-restart fitted decay remained about 0.99515. Local residual improvement did not remove the slow global mode fast enough to pay for trials. A one-vector history is inadequate evidence for a reliable global correction; the unchanged restart also discards pre-restart impulse progress. No restart rule was changed to hide this result.

**Acceptance failure:** Eight unique formerly converging configurations failed: chain 64 policies 1/3, and chains 256/1,024 policies 1/3/4. Timing arms had control 115 converged/5 rejected versus candidate 93 converged/27 rejected. The established minimum 5.3183% A/A floor and paired intervals were recorded before execution. The large-chain attempted solver ratio was about 0.9036 [0.8918, 0.9139], but an unsolved attempt cannot pass performance acceptance. The raw aggregate attempted-tick ratio 0.7472 [0.7202, 0.7763] includes failures and is **not a valid simulation speedup**. `decision-review.json` explicitly marks that boundary. Correctness/convergence rejection overrides timing. No parameters were tuned or second candidate tested.

**Preservation and next boundary:** The active solver again hashes to `10c5ee6541c7799119a9578b304c51f8d3de3938e2221613894bc7fae75d5c24`; original status and 395 snapshotted files are unchanged. `experiments/g5-anderson-20261019.patch` preserves the rejected helper/solver/driver/tests; exact executed hashes, capacity/work telemetry, raw traces, compiler/binary provenance, and restoration proof accompany the focused handoff. To reproduce only in a separate deterministic-baseline copy, initialize a new batch directory and `dev-test-results/anderson-current.txt`, copy the retained shader there as `control-projected_solver.hlsl`, apply the rejected patch, then run `python sweep_anderson.py`. Prior deterministic artifact directories are required. This complete record is carried on the GitHub working branch, without merging `main` or approving a gate. The next mathematical target is a constraint-aware global/low-mode correction with a proven cost/fallback budget; it is not implemented or qualified here. G0–G4 remain frozen, GPU-02 unverified, G5 unqualified, and G6 unauthorized.

## 16. Risks and work still required

1. **State isolation follow-up:** The existing renderer uses the G6-P3 task/lease integration and G6-P4 deferred consumption. Qualify device-loss teardown/recovery and sustained ownership under broader workloads before formal G6.
2. **General island convergence:** Residual-gated policy 4 passes the limited quick sweep and avoids unnecessary restarts in branching/oblique cases. It remains opt-in and unqualified for sustained/general workloads; preserve KKT limits and rollback.
3. **Large-island parallelism:** The 1,024-body global-memory solver takes roughly 167.5 ms on the present policy-4 sample. A cache variant reduced this but hurt aggregate throughput; real DRAM stalls and FP64 utilization remain unverified. Profile per-iteration cost before any multi-workgroup rewrite.
4. **Scheduler scope:** A reusable resource monitor and dependency scheduler are design goals, not completed general-purpose services.
5. **Display verification:** Collect real local display evidence for GPU-02 when required. Do not confuse Present calls with scanout.
6. **Evidence discipline:** Keep the exact source revision, shader hashes, fixtures, and GPU/driver context with measurements. Do not combine numbers from different scenarios into one speed claim.
7. **Production integration:** G6 must define API stability, error handling, host integration, and long-running device-loss recovery before an engine rewrite is authorized.
8. **Measurement scheduling:** Canonical schedules now separate arithmetic variability from runtime variability only inside the bounded measurement envelope. Sorting overhead and cold-run timing noise must not be reported as production solver cost or speedup.
9. **Small optimization claims:** Barrier coalescing passed exact numerical comparison but failed the predeclared uncertainty and aggregate gates. Its shader is rejected; future changes need matched schedules and same-batch noise controls.
10. **Contact-local load reuse:** Exact arithmetic/result matching passed, but the 1,024-body paired interval included no improvement and the apparent gain fell below the same-batch 5.32% noise floor. The candidate is archived and inactive; aggregate gains must not be presented as a retained optimization.
11. **Algorithmic acceleration:** Bounded depth-one mixing can accelerate several fixtures yet lose convergence on large chains under the original work cap. Residual-monotone trials alone do not guarantee a useful global convergence/cost bound. The candidate is rejected; failed-attempt timings are not simulation performance evidence.

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
| 2026-10-19 | G6-P4 deferred GPU consumption - LOCAL PREPARATION PASS | Accepted snapshots render while a newer producer is pending; command acknowledgements retain matching-tick acceptance. Eleven final test records pass (five reused unchanged binaries). CPU handoff improves; GPU intervals increase; no allocation growth or throughput claim. G5 deferred, G6 unqualified, physical device loss separate. |
| 2026-10-19 | G6-P3 actual GPU render consumer - LOCAL PREPARATION PASS | Existing renderer reads accepted immutable generations through P2 tasks and native queue/fence ownership. Fourteen serialized headless process runs pass; 192 KiB and three allocations saved. Pre-submit acceptance wait is explicit; no performance gain claimed. G5 deferred; G6 and physical device-loss recovery unqualified. |
| 2026-10-19 | G6-P2 resource/task ownership — LOCAL PREPARATION PASS | Reused fixed-pass queues and lease storage; added explicit dependencies, resource conflicts and non-preemptive fence-safe cancellation. Twenty-two headless process runs pass; zero extra GPU allocations/committed bytes. Break excluded from performance claims; G5 deferred and G6 not qualified. |
| 2026-10-19 | G6-P1 consumer generation isolation — LOCAL PREPARATION PASS | Added bounded immutable GPU snapshots, completion-bound leases, explicit backpressure and failure ownership. Twenty-one headless process runs pass; paired costs recorded. G5 DEFERRED / NOT QUALIFIED; G6 NOT QUALIFIED; device loss remains unverified. |
| 2026-10-18 | Baseline document | Established the technical inventory, G0–G5 history, evidence labels, known risks, and mandatory breakpoint update process. No new gate was approved by this documentation commit. |
| 2026-10-18 | G5 adaptive-solver decision — FAIL | Reviewed 60 CLI runs and matching JSON/CSV summary. The adaptive policy converged in 16/20 runs but failed the 256- and 1,024-body chains. It was rejected; the previous policy remains the local baseline, and G5 stays open. |
| 2026-10-18 | G5 bounded-restart candidate — CONDITIONAL | Reviewed 60 headless GPU runs and six diagnostics. Policy 3 converged in 20/20 local attempts, but 256/1,024-body chains and several branching/oblique networks suffered performance penalties. Production remains unchanged; G5 remains unqualified. |
| 2026-10-18 | G5 residual-gated restart — OPT-IN RETAIN | Audited 80 short GPU timing runs, 10 trace checks and 17 reported sweep unit tests. Policy 4 converged in 20/20 and lowered aggregate GPU p50 sum by 13.5% relative to policy 3, but remained slow on large chains. Production policy 1 unchanged; G5 unqualified. |
| 2026-10-18 | G5 shared-body-cache experiment — REJECT | Audited 100 CLI timing trials, 22 probes, 22 unit tests and the HLSL source. 1,024-body GPU p50 improved 170.13→152.69 ms, but aggregate geometric mean worsened 4.25%. Hardware counter attribution is unverified. Default remains cache-off; G5 open. |
| 2026-10-19 | G5 deterministic measurement — BOUNDED PASS | One 180-trial headless batch plus two safe-envelope rejections: repeatable contact/color schedules, iterations and FP64 results for policies 0–4. Scheduling overhead measured separately; runtime variance remains. Production/solver unchanged; previous handoff hash reconciled with execution-time provenance still unverified. G5 remains open. |
| 2026-10-19 | G5 post-color barrier coalescing — REJECT | One 240-trial deterministic comparison: exact arithmetic/results, rollback preserved; apparent 1,024-body solver gain failed the 4.36% noise floor and uncertainty/aggregate gates. Exact retained solver restored; rejected patch archived. G5 remains open. |
| 2026-10-19 | G5 contact-local FP64 loads — REJECT | One 240-trial deterministic paired sweep: exact schedules, impulses, work state, iterations, and rollback. Aggregate tick ratio 0.9662 passed, but 1,024-body solver ratio 0.9749 [0.9490, 1.0030] failed the 5.32% A/A floor and primary confidence gate. Retained shader restored; complete architecture record updated on the GitHub working branch. G5 remains open. |
| 2026-10-19 | G5 bounded Anderson convergence — REJECT | Verified long-chain conditioning and 0.995 decay; 240 timing attempts plus 20 residual probes tested one projected depth-one accelerator. Several fixtures improved, but eight previously converging configurations exhausted the unchanged work budget. Rollback remained safe; exact retained solver restored. Failed-attempt timing is not a speedup. G5 remains open. |

---

**Source map:** [Main engine code](../physics.c) · [Spatial search](../spatial.c) · [Storage](../storage.zig) · [Entity identity](../entity.zig) · [Viewer](../viewer.c) · [Playable branch](https://github.com/Cryosimorgh/GPU-physics-engine/tree/billiards-playable-requalification-20261018) · [Playable headless workflow](https://github.com/Cryosimorgh/GPU-physics-engine/blob/billiards-playable-requalification-20261018/dev_test.py).
