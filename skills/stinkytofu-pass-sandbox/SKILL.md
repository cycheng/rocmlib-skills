---
name: stinkytofu-pass-sandbox
description: >-
  Add a FileCheck regression test for a StinkyTofu pass by hand-writing a
  minimal `.stir` example, running it through `stinkytofu-opt`, and dropping
  the file directly into `shared/stinkytofu/tests/filecheck/`. Use when the
  user wants to "try", "experiment with", "demo", "see the output of", or
  "add a test for" a stinkytofu pass (e.g. BuildUseDefChainPass,
  StinkyWaitCntInsertionPass, CFGBuilderPass, PeepholeOptimizationPass), or
  when adding/fixing a pass and a regression test is needed.
---

# StinkyTofu Pass FileCheck Test

Workflow for adding a permanent FileCheck regression test for a stinkytofu
pass — typically alongside a pass change or fix. The flow goes straight
into the test directory; no scratch-dir step.

## Binary & invocation

- Binary: `/home/cycheng2/tickets/build-opt/tools/stinkytofu-opt/stinkytofu-opt`
- Architecture flag (required for most passes): `--arch gfx1250`
- Output flag: `--print-output` (emits the post-pass IR in `.stir` format)
- List available passes: `--list-passes` or `--help`

Common invocation (used both for ad-hoc inspection and inside the test's
`# RUN:` line):

```bash
/home/cycheng2/tickets/build-opt/tools/stinkytofu-opt/stinkytofu-opt \
    --arch gfx1250 <file>.stir \
    --<PassName> --print-output
```

Multiple passes can be chained; they run in the order given.

### Pass arguments

Some passes accept comma-separated arguments via
`--<PassName>=arg1,arg2`. Each pass parses its own argument tokens; check
the registration entry in
`shared/stinkytofu/tools/stinkytofu-opt/stinkytofu-opt.hpp` for the
supported flag names. A pass with no `=` suffix uses defaults.

Currently recognized:

- `--BuildUseDefChainPass=includePseudo` — also build PHIs / def-use
  chains for pseudo registers (e.g. `LDS<token>` memtoken regs that
  `StinkyBuildImplicitDependencyPass` materializes). Default skips them.
- `--BuildUseDefChainPass=noClearExisting` — do not clear existing PHIs
  / chains before rebuilding. Default clears.
- Tokens combine: `--BuildUseDefChainPass=includePseudo,noClearExisting`.

## Authoring the .stir file

Write directly to `shared/stinkytofu/tests/filecheck/<name>.stir`. Use a
descriptive `<name>` keyed to the pass + scenario (e.g.
`builddefuse_pseudo_reg_chain.stir`,
`waitcnt_insertion_wmma_dsread.stir`). Existing tests in that directory
are the syntax reference — particularly:

- `waitcnt_insertion_wmma_dsread.stir` (single block, ds_load + wmma)
- `waitcnt_insertion_lds_war_cross_block.stir` (two blocks, fallthrough)
- `waitcnt_insertion_tensor_per_path_self_loop_anchor.stir` (loop with
  `s_cbranch_scc1` and multi-successor `Successors:` line)
- `builddefuse_pseudo_reg_chain.stir` (diamond CFG, pseudo-reg PHI)

### Required structure of a FileCheck test

1. **`# RUN:` line** as the very first line:
   ```
   # RUN: %stinkytofu-opt --arch gfx1250 %s --PassName --print-output
   ```
   `%s` expands to the test path; `%stinkytofu-opt` to the binary.
   Pass arguments work the same as on the CLI, e.g.
   `--StinkyBuildImplicitDependencyPass --BuildUseDefChainPass=includePseudo`.
2. **Header comment block** (`# ...`) describing the CFG, the intent of
   the test, and the expected pass behavior. Future readers rely on this
   to understand why the CHECKs are shaped the way they are.
3. **`CHECK` directives** matching the post-pass IR (see the directives
   reference below).
4. **The `st.func` body** — the actual IR.

### IR skeleton

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

### IR syntax rules

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

### CHECK directives

- `CHECK-LABEL: @<func_name>` — anchors to the start of the function;
  acts as a sync point for following CHECKs.
- `CHECK: <text>` — match a substring anywhere on a later line.
- `CHECK-NEXT: <text>` — must match the **immediately** following line.
- `CHECK-SAME: <text>` — match additional substring on the previously
  matched line (use after `CHECK:` / `CHECK-NEXT:` to assert multiple
  substrings on the same line, e.g. operand lists).
- `CHECK-NOT: <text>` — must not appear before the next CHECK.

Common gotcha: `CHECK: ^merge` matches the predecessor's
`Successors: ^merge` line first. Anchor with the colon
(`CHECK: ^merge:`) so it only matches the block header.

## Workflow

1. Read the user's CFG/instruction description and the pass behavior
   under test.
2. Pick a test name and write directly to
   `shared/stinkytofu/tests/filecheck/<name>.stir`. Map the description
   to the IR skeleton; add a synthesized `^entry` with `s_cbranch_scc1`
   if multiple "entry-like" blocks were requested.
3. Run `stinkytofu-opt` once on the file to capture the actual
   `--print-output` text:
   ```bash
   /home/cycheng2/tickets/build-opt/tools/stinkytofu-opt/stinkytofu-opt \
       --arch gfx1250 shared/stinkytofu/tests/filecheck/<name>.stir \
       --<Pass1> --<Pass2> --print-output
   ```
4. Author the `# RUN:` line, header comment, and `CHECK` directives so
   they match what the pass actually produced (formatting matters: the
   leading two-space indent on instructions, the explicit `Successors:`
   lines, and pseudo regs printed as `LDS<token>`).
5. Refresh CMake (FileCheck tests are auto-globbed in
   `shared/stinkytofu/tests/CMakeLists.txt` — no CMake edits needed,
   but cmake must re-run to register new files):
   ```bash
   cd /home/cycheng2/tickets/build-opt && cmake .
   ```
   Expect `Registered N FileCheck tests` to increase by one.
6. Run the test:
   ```bash
   cd /home/cycheng2/tickets/build-opt && \
       ctest -R 'FileCheck\.<name>' --output-on-failure
   ```
   The test name is the file stem (no `.stir`). On failure, ctest prints
   `expected: ...` / `got: ...` showing the actual output line — adjust
   CHECKs to match `--print-output` verbatim.
7. Show the user: (a) the input IR, (b) the exact command, (c) the
   post-pass IR from stdout, (d) the passing ctest line, and (e) a
   short explanation of what changed (PHIs inserted, waitcnts inserted,
   peepholes applied, etc.).

## Pass-specific notes

- **BuildUseDefChainPass**: prints inserted `st.PHI` instructions at join
  blocks (one PHI per scalar register lane). The def-use chain links
  themselves (`getSources()`/`getUsers()`) are not serialized by
  `--print-output`; describe them in prose when relevant. Pass
  `=includePseudo` to also place PHIs / build chains for pseudo regs
  (LDS memtokens); chain it after `--StinkyBuildImplicitDependencyPass`
  so the LDS<n> operands actually exist on the instructions. See
  `tests/filecheck/builddefuse_pseudo_reg_chain.stir` for a worked
  example.
- **StinkyWaitCntInsertionPass**: inserts `s_wait_dscnt` /
  `s_wait_loadcnt` / `s_wait_tensorcnt` before consumers. Requires
  `mod.memtoken = { tokens = [...] }` on memory ops.
- **PeepholeOptimizationPass**, **DeadCodeEliminationPass**: usually
  benefit from running `--BuildUseDefChainPass` first so chains exist.

## Reference files

- Existing filecheck tests: `shared/stinkytofu/tests/filecheck/*.stir`
- FileCheck registration (auto-glob): `shared/stinkytofu/tests/CMakeLists.txt`
- Pass registry / flag names: `shared/stinkytofu/tools/stinkytofu-opt/stinkytofu-opt.hpp`
- Pass list at runtime: `stinkytofu-opt --list-passes`
