# Repository working rules

Use clear ASD-STE100-inspired technical English. Keep sentences short, but do not apply controlled-language rules rigidly.

1. Use the local working tree as the implementation baseline. Preserve uncommitted changes and any branch-specific work.
2. For physics, performance, and resource tests, run the existing **headless CLI** first. Do not open a viewer or make screenshots unless the task is explicitly about visuals or input behavior.
3. Make the smallest correct change. Use targeted tests; reserve the full benchmark campaign for gate qualification.
4. Save detailed logs and JSON/CSV evidence to files. Return a short summary with the first failure and relevant metrics.
5. Keep the fixed global timestep, ordered GPU passes, safety checks, generation identity, and resource lifetime contracts.
6. Do not mark a task as PASS by removing verification or by changing the tested workload.

## Mandatory breakpoint documentation

`docs/ENGINE_ARCHITECTURE.md` is the project's **persistent technical record**.

A breakpoint means: G0–G6 gate decision, gate reopen, release candidate, material architecture change, or validated performance-policy change. At **every breakpoint**, update the same document **before** declaring the breakpoint complete:

- Update affected design and innovation sections, evidence, limits, and status.
- Update the breakpoint/qualification table and its next decision.
- Add a dated entry in the document's change log.
- Name the code revision, exact fixture, hardware and sample count where applicable.
- Distinguish local handoff evidence from committed and released code.
- Keep past failures; do not silently rewrite history or inflate qualification.
- Commit the document with the breakpoint changes. Do not leave the update in chat only.

For routine code edits, do **not** rewrite the whole document. Update only the affected contract if it materially changed. Keep normal Codex responses short.
The working branch must carry its architecture changes into `main` when integrated.
