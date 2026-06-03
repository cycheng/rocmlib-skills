---
name: stinkytofu-pass-sandbox
description: >-
  Construct a small, hand-written StinkyTofu IR (.stir) example and run one or
  more stinkytofu-opt passes on it to inspect the resulting IR. Use when the
  user wants to "try", "experiment with", "demo", or "see the output of" a
  stinkytofu pass (e.g. BuildUseDefChainPass, StinkyWaitCntInsertionPass,
  CFGBuilderPass, PeepholeOptimizationPass) on a minimal CFG or instruction
  sequence, especially when the request describes blocks/edges like
  "bb0 -> bb2, bb1 -> bb2" and a few instructions per block.
---

# StinkyTofu Pass Sandbox

Workflow for building a tiny `.stir` test case from a user description and
running it through `stinkytofu-opt` to show pass output.

## Binary & invocation

- Binary: `/home/cycheng2/tickets/build-opt/tools/stinkytofu-opt/stinkytofu-opt`
- Architecture flag (required for most passes): `--arch gfx1250`
- Output flag: `--print-output` (emits the post-pass IR in `.stir` format)
- List available passes: `--list-passes` or `--help`

Common invocation:

```bash
/home/cycheng2/tickets/build-opt/tools/stinkytofu-opt/stinkytofu-opt \
    --arch gfx1250 /tmp/sandbox/example.stir \
    --<PassName> --print-output
```

Pass flags are passed as `--<PassName>` (e.g. `--BuildUseDefChainPass`,
`--StinkyWaitCntInsertionPass`). Multiple passes can be chained; they run
in the order given on the command line.

## Authoring the .stir file

Write the example under a scratch dir (e.g. `/tmp/sandbox/example.stir`).
Use existing tests in `shared/stinkytofu/tests/filecheck/*.stir` as the
syntax reference - in particular:

- `waitcnt_insertion_wmma_dsread.stir` (single block, ds_load + wmma)
- `waitcnt_insertion_lds_war_cross_block.stir` (two blocks, fallthrough)
- `waitcnt_insertion_tensor_per_path_self_loop_anchor.stir` (loop with
  `s_cbranch_scc1` and multi-successor `Successors:` line)

### Skeleton

```text
st.func @example() {
^entry:
  "st.s_cbranch_scc1"("bb1", SCC0)
  Successors: ^bb0, ^bb1
^bb0:
  v[0:1] = "st.ds_load_b64"(v10) { mod.ds = { na = 1, offset = 0, gds = false }, mod.memtoken = { tokens = [0] } }
  "st.s_branch"("bb2")
  Successors: ^bb2
^bb1:
  v[0:1] = "st.ds_load_b64"(v10) { mod.ds = { na = 1, offset = 16, gds = false }, mod.memtoken = { tokens = [0] } }
  "st.s_branch"("bb2")
  Successors: ^bb2
^bb2:
  a[10:17] = "st.v_wmma_f32_16x16x32_bf16"(v[0:7], v[30:37], a[10:17]) { mod.mfma = { reuseA = false, reuseB = false } }
}
```

### Syntax rules to follow

- Each basic block starts with `^label:` and ends with a terminator
  (`st.s_branch`, `st.s_cbranch_scc0/1`, or fallthrough) followed by an
  explicit `Successors: ^a, ^b` line listing CFG successors in branch
  order (taken target first for `s_cbranch_*`).
- Branch targets inside the operand list are bare label names in quotes,
  e.g. `"st.s_branch"("bb2")`. The `Successors:` line uses the `^` prefix.
- Destination registers go on the LHS; sources go in the parenthesised
  operand list. Wide regs use `v[lo:hi]` (inclusive), single regs use `v0`.
- Modifiers go in `{ ... }` and are comma-separated `key = value` pairs.
  `mod.ds`, `mod.mfma`, `mod.memtoken` are common. `issueCycles` and
  `latencyCycles` are optional - the parser fills defaults.
- Pseudo opcode `st.PHI` is inserted by `BuildUseDefChainPass`; do **not**
  hand-author it.

### CFG gotchas

- The first block in the function is the entry. Every other block must be
  reachable from the entry via `Successors:` edges, otherwise dominance
  analysis ignores it and joins won't see merge points.
- If the user describes "bb0 -> bb2, bb1 -> bb2" with no shared predecessor,
  add an `^entry` block with `s_cbranch_scc1` that targets both `^bb0` and
  `^bb1` so the merge at `^bb2` is real.

## Workflow

1. Read the user's CFG/instruction description.
2. Map it to the skeleton above; add a synthesized `^entry` with
   `s_cbranch_scc1` if multiple "entry-like" blocks were requested.
3. Write the `.stir` to a scratch path (e.g. `/tmp/sandbox/<name>.stir`).
4. Run `stinkytofu-opt` with `--arch gfx1250`, the requested pass(es),
   and `--print-output`.
5. Show the user: (a) the input IR, (b) the exact command, (c) the
   post-pass IR from stdout, and (d) a short explanation of what changed
   (PHIs inserted, waitcnts inserted, peepholes applied, etc.).

## Pass-specific notes

- **BuildUseDefChainPass**: prints inserted `st.PHI` instructions at join
  blocks (one PHI per scalar register lane). The def-use chain links
  themselves (`getSources()`/`getUsers()`) are not serialized by
  `--print-output`; describe them in prose when relevant.
- **StinkyWaitCntInsertionPass**: inserts `s_wait_dscnt` /
  `s_wait_loadcnt` / `s_wait_tensorcnt` before consumers. Requires
  `mod.memtoken = { tokens = [...] }` on memory ops.
- **PeepholeOptimizationPass**, **DeadCodeEliminationPass**: usually
  benefit from running `--BuildUseDefChainPass` first so chains exist.

## Reference files

- Existing filecheck tests: `shared/stinkytofu/tests/filecheck/*.stir`
- Pass registry / flag names: `shared/stinkytofu/tools/stinkytofu-opt/stinkytofu-opt.hpp`
- Pass list at runtime: `stinkytofu-opt --list-passes`
