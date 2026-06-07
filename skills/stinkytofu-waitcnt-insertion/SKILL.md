---
name: stinkytofu-waitcnt-insertion
description: >-
  Read, debug, or extend the StinkyTofu wait-count insertion pass
  (`StinkyWaitCntInsertionPass` / `WaitDataflow`) which emits
  `s_wait_dscnt` / `s_wait_loadcnt` / `s_wait_tensorcnt` instructions for
  async memory ops on GFX1250. Use when modifying or debugging waitcnt
  insertion, investigating incorrect / over-deep / cap-hit wait values,
  tracing dataflow convergence, or extending per-counter policy. Triggers
  include: "waitcnt", "wait count", "s_wait_dscnt", "WaitDataflow",
  "loop-carried PHI", "iteration cap", "RAW dependency", "memtoken",
  "phiSummary", "per-pred queue".
---

# StinkyTofu WaitCnt Insertion

A forward dataflow over the CFG that decides where to insert
`s_wait_dscnt` / `s_wait_loadcnt` / `s_wait_tensorcnt` so async memory
ops have completed by the time their result is read.

## Files to know

- `shared/stinkytofu/include/stinkytofu/transforms/asm/waitcnt/WaitDataflow.hpp` —
  lattice (`PerPredQueue`, `PhiSummary`, `DataflowState`) and the
  `WaitDataflow` solver API. Read the header comment first; it's the
  spec.
- `shared/stinkytofu/src/transforms/asm/waitcnt/WaitDataflow.cpp` — the
  forward solver: `mergeFromPredecessors`, `transferBlock`, `solve`.
- `shared/stinkytofu/src/transforms/asm/StinkyWaitCntInsertionPass.cpp` —
  the wrapper pass that runs `buildUseDefChain(includePseudo=true)`,
  builds the dataflow, runs `ShallowPredPromotion`, and emits the
  `s_wait_*` IR.
- `shared/stinkytofu/src/transforms/asm/waitcnt/ShallowPredPromotion.cpp` —
  optimizer that may relax an anchor wait by recording a predecessor
  tail drain instead.
- `shared/stinkytofu/src/transforms/asm/StinkyBuildImplicitDependencyPass.cpp` —
  materialises `LDS<token>` memtoken pseudo-regs that this pass relies
  on. Must run first.
- `shared/stinkytofu/tests/filecheck/waitcnt_insertion_*.stir` — the
  regression test suite. New tests go here.

## Mental model

For each hardware counter (`CK_DS`, `CK_Buffer`, `CK_Tensor`) we keep,
at every block entry, **one in-flight FIFO per CFG predecessor**
(`PerPredQueue`). The dataflow value at a block is therefore
`array<vector<PerPredQueue>, CK_Count>` plus a map of per-PHI summaries.

Per-pred queues exist because a single union queue at a merge would
either drop a dep still in flight on one path or over-drain every
path. Keeping queues per pred lets a consumer at a join compute the
strictest required wait as `max` over preds, which is the only sound
choice.

### How a wait value comes out of a queue

For an op `OP` at index `i` in a queue of size `n`, the required wait
is `n - i - 1` (so the oldest op is at index 0 and waiting "0" leaves
nothing pending; the tail op needs wait `n - 1`). The helper is
`PerPredQueue::countFrom(op)`.

### Block transfer

`transferBlock` walks the block in program order. For each consumer
instruction it:

1. For each counter `c` where `rawNeedsWait[c](inst)` is true, walks the
   instruction's def-use sources. For a leaf memop source the wait is
   `countFrom(src) - 1` over every per-pred queue, tightened with
   `min`.
2. For a PHI source the consumer uses `phiCurrentQueueWait` (recursive)
   to walk the PHI tree down to leaf memops and look them up in **the
   consumer's live queues**. Do not use a frozen `PhiSummary` at the
   PHI's defining block: on a loop back-edge the carried producer's
   next-iter reload sits at the queue tail at the header merge
   (`countFrom == 1` → wait 0), and a downstream consumer that
   inherited that scalar would emit `s_wait_dscnt 0` regardless of how
   many DS ops were issued in between.
3. After visiting every consumer, appends the instruction's own memop
   (if it produces one for counter `c`) to all per-pred queues.

At block exit the per-pred queues are collapsed to a single union queue
per counter so successors treat us as one predecessor; per-pred path
lengths can still be reconstructed by the optimizer layer reading
`DataflowResult::exitState`.

### Solver

`solve()` is a textbook RPO fixed-point iteration: re-merge entry from
preds, transfer, compare exit. Iterates until exit states stop
changing or the iteration cap is hit. On cap-hit it sets `capHit =
true`, logs

```text
[WaitDataflow] iteration cap N hit; falling back to s_wait_* 0 at every anchor.
```

and `materializePlan()` rewrites every wait in the recorded plan to
`0` on the counters that actually had any pending op. The fallback is
correct (drains everything) but pessimistic.

### Per-counter policy

`WaitDataflow::setRawNeedsWait(CounterKind, predicate)` overrides
"does this consumer require a drain on this counter?" Defaults:

- `CK_DS` / `CK_Buffer`: drain at every direct consumer (the hazard is
  realised at the read).
- `CK_Tensor`: drain only at a barrier. A `tensor_load_to_lds` writes
  LDS asynchronously and the hazard only becomes observable past a
  barrier.

The pass wrapper additionally forces `CK_Tensor` to drain when
`NumWaves == 1`.

## Running the pass

```bash
/home/cycheng2/tickets/build-opt/tools/stinkytofu-opt/stinkytofu-opt \
    --arch gfx1250 <file>.stir \
    --StinkyBuildImplicitDependencyPass \
    --StinkyWaitCntInsertionPass \
    --print-output
```

`StinkyBuildImplicitDependencyPass` must come first so memtoken
pseudo-regs exist before the wait pass calls
`buildUseDefChain(includePseudo=true)` internally.

## Debugging

### Enable `PASS_DEBUG` output

Both the wrapper and the solver use the standard `PASS_DEBUG` macro.
Add the relevant `DEBUG_TYPE` name to the debug allow-list — either
the `StinkyTofuDebugPass` global parameter or
`PassManagerDebugConfig::addDebugOnly` — to enable:

| `DEBUG_TYPE`                  | What you get                                                   |
| ----------------------------- | -------------------------------------------------------------- |
| `WaitDataflow`                | Per-iteration, per-block, per-counter queue stats (`iter`, `bb`, `counter`, `nQueues`, `totOps`, `maxLen`). Use to diagnose non-convergence. |
| `StinkyWaitCntInsertionPass`  | (Add new traces here when needed; macro is wired up already.)  |

The cap-hit warning is unconditional (printed on `std::cerr`), so you
do not need to enable debug to see it.

### Dump IR before / after the pass

`Gfx1250Backend.cpp` already wires `DumpStinkyFunctionPass` around
`StinkyWaitCntInsertionPass` (gated by `EnableWaitCntInsertion`),
writing `before_waitcnt_insertion.stir` and `after_waitcnt_insertion.stir`
next to the build output. Diff these to localise an unexpected wait.

### Symptom → likely cause

| Symptom                                                                                              | Likely cause                                                                                                 |
| ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `s_wait_dscnt 0` everywhere, cap-hit message on stderr                                               | Solver did not converge. Run with `WaitDataflow` debug on; look for `nQueues` or `maxLen` growing per iter.  |
| Loop-carried consumer emits `s_wait_dscnt 0` but should be positive (no cap-hit)                     | Static-`PhiSummary` regression: the consumer must use `phiCurrentQueueWait` to scan its live queue.          |
| `nQueues` grows monotonically across iterations on a block with a back-edge predecessor              | Per-pred queue dedup regression in `mergeFromPredecessors`. Identical `(pred, ops)` queues must collapse.    |
| `maxLen` grows monotonically on a self-loop block under sustained tail-only producers                | Known open issue: queue length is unbounded. Will need a hardware-max cap or restoring exit-block collapse.  |
| Tensor wait emitted at a non-barrier consumer when `NumWaves > 1`                                    | `setRawNeedsWait(CK_Tensor, …)` predicate is wrong. Default is barrier-or-single-wave.                       |
| Wait emitted before an instruction with no `mod.memtoken`                                            | Implicit-dep pass missed it. Check `StinkyBuildImplicitDependencyPass` ran and tagged the producer.          |

## Tests

FileCheck regression tests live next to all other passes in
`shared/stinkytofu/tests/filecheck/`, named
`waitcnt_insertion_<scenario>.stir`. Auto-globbed by cmake — no
`CMakeLists.txt` edit, just re-run `cmake .` to register a new file.
To author one, follow the `stinkytofu-pass-sandbox` skill in this
repo. Representative existing tests to read first:

- `waitcnt_insertion_wmma_dsread.stir` — minimal single-block ds_load +
  wmma RAW.
- `waitcnt_insertion_loop_carried_local_prefix.stir` — self-loop with
  loop-carried PHI and in-block local prefix. Pins the live-queue PHI
  scan.
- `waitcnt_insertion_cross_block_phi_consumer.stir` — diamond, post-
  merge consumer reading a PHI. Pins one merge level.
- `waitcnt_insertion_cross_block_phi_chain.stir` — two stacked merges.
  Pins the recursive `phiCurrentQueueWait` walk.
- `waitcnt_insertion_phi_summary_two_level_merge.stir` — two-level
  merge with token-1 / token-2 separation.

When asserting a wait value, prefer a **positive** `dlcnt = N` (not
`dlcnt = 0`): the cap-hit fallback also emits `0`, so a `0` assertion
cannot distinguish a correct result from a non-convergent one.

### Running the suite

```bash
cd /home/cycheng2/tickets/build-opt
ctest -R 'FileCheck\.waitcnt_insertion' --output-on-failure
```

## Extending the pass

| Goal                                          | Where to change                                                                       |
| --------------------------------------------- | ------------------------------------------------------------------------------------- |
| New per-counter drain policy                  | `WaitDataflow::setRawNeedsWait` from the caller, *or* default in the constructor.     |
| Recognise a new async memop class             | `classifyMemOp` in `WaitDataflow.cpp`.                                                |
| New optimizer over the conservative plan      | Implement `WaitPlanOptimizer::rewrite` and append to the optimizer list in the pass.  |
| Add a per-pred path-length-aware shallow opt  | Extend `ShallowPredPromotion`; it already reads `DataflowResult::exitState`.          |
| Add an unconditional drain at a new IR site   | Add an entry to `emitWaits` in `StinkyWaitCntInsertionPass.cpp`.                      |

After changing any of these, rebuild `stinkytofu-opt` and run the
`waitcnt_insertion_*` FileCheck suite. Add at least one new test that
fails before the change and passes after.

## Things not to do

- Do not collapse per-pred queues mid-block. Block exit collapsing is
  intentional and the only safe collapse point.
- Do not read `PhiSummary` for a PHI consumer's wait. Summaries are
  fine as a representative-wait hint for *non-counter-emitting*
  consumers; for any wait that lands in `WaitInsertionPlan`, use the
  live queue.
- Do not silently bump the iteration cap to mask non-convergence — fix
  the lattice (e.g. dedup, length cap) instead.
- Do not insert waits before `StinkyBuildImplicitDependencyPass`; the
  memtoken pseudo-regs the dataflow walks would not exist yet.
