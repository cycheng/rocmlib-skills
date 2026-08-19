---
name: tensile-kernel-name-to-yaml
description: >-
  Reverse-engineer a standalone TensileLite benchmark YAML from a hipBLASLt
  kernel name or solution name, so one failing kernel can be regenerated and
  debugged on its own. Use when the user has a kernel/solution name (e.g.
  Cijk_Ailk_Bljk_HHS_BH_Bias_HA_S_SAV_UserArgs_MT32x16x32_MI16x16x1_...) and
  wants the YAML that produces it, wants name tokens decoded into tuning
  parameters, wants to reproduce a hipblaslt-test failure with Tensile alone, or
  when a locally generated kernel name does not match the runtime one. Triggers
  include "reverse engineer the yaml", "which yaml produces this kernel",
  "decode the kernel name", "kernel name mismatch", "TensileLibLogicToYaml",
  "KernelNameMin", "SolutionNameMin".
---

# Kernel Name to Tensile YAML

Goal: given a kernel or solution name, produce a Tensile input YAML that
regenerates exactly that kernel, then prove the match by diffing names.

All paths are relative to the repo root. TensileLite lives in
`projects/hipblaslt/tensilelite`.

## Workflow

```
- [ ] 1. Get the exact runtime kernel name and its logic file
- [ ] 2. Find the logic YAML entry for that name
- [ ] 3. Convert that one solution to a Tensile input YAML
- [ ] 4. Repair ProblemType keys the converter drops
- [ ] 5. Match the problem size and data init to the failing case
- [ ] 6. Regenerate and diff the names
```

### 1. Get the exact name

If the user already pasted a name, use it verbatim and skip to step 2. To
capture one from a failing test, set `TENSILE_DB` bits:

```bash
TENSILE_DB=0x28060 ./build/release/clients/hipblaslt-test --gtest_filter='*<case>*'
```

| Bit | Prints |
|---|---|
| `0x8000` | winning kernel name |
| `0x20000` | library logic index (identifies the logic file) |
| `0x20` | code object file paths |
| `0x40` | kernel arguments |

Add `TENSILE_DB2=0x1` to select the kernel but skip the launch, which avoids
re-triggering a fault while you collect names.

### 2. Find the logic YAML entry

Logic files live under
`projects/hipblaslt/library/src/amd_detail/rocblaslt/src/Tensile/Logic/asm_full/<arch>/{Equality,GridBased}/`.

Grep the file **contents**, not filenames: the filename type prefix is spelled
differently from the runtime name (`..._H_HS_BH_...` in the filename vs
`...HHS_BH...` in the kernel name). Search a distinctive middle chunk:

```bash
grep -rln 'MT32x16x32_MI16x16x1' \
  projects/hipblaslt/library/src/amd_detail/rocblaslt/src/Tensile/Logic/asm_full/gfx1250/
```

In the matching file, note the `SolutionIndex` of the entry whose
`KernelNameMin`/`SolutionNameMin` matches. A logic file often contains exactly
one solution (index 0), and its size table may be synthetic — real problem sizes
fall through to the only solution, so do not expect your size to be listed.

### 3. Convert one solution to a Tensile input YAML

```bash
cd projects/hipblaslt/tensilelite
./.tox/py3/bin/python ./Tensile/bin/TensileLibLogicToYaml \
  -i <logic yaml> -d <SolutionIndex> -o /tmp/repro.yaml
```

Use a Python that has `rocisa` installed — the tox env at `.tox/py3/` if it
exists. Running the wrapper with a bare `python3` fails with
`ImportError: cannot import name 'rocIsa' from 'rocisa' (unknown location)`,
because `tensilelite/rocisa/` has no `__init__.py` and is picked up as an empty
namespace package that shadows the real one.

### 4. Repair dropped ProblemType keys

**This is the step that is easy to miss and it silently produces the wrong
kernel.** `formProblemTypeYamlData` in
`projects/hipblaslt/tensilelite/Tensile/TensileLibLogicToYaml.py` emits a
ProblemType key only if it exists in `_defaultProblemType`
(`Tensile/SolutionStructs/Problem.py`) *and* differs from that default. Keys
absent from that registry are dropped without warning.

So diff the logic file's `ProblemType` block against the generated YAML's
`ProblemType` and re-add every missing key by hand. The common casualty is
activation:

```yaml
      Activation: true
      ActivationType: hipblaslt_all
      ActivationComputeDataType: 0
```

Without `ActivationType`, `ProblemType.__init__` defaults it to `'none'`, which
drops the `HA_S` tokens from the name and forces `ActivationFuncCall` off
(`AFC1` becomes `AFC0`, see `Solution.py::ActivationFuncCall`).

### 5. Match problem size and data init

For a GEMM, a four-element `Exact` is enough — `ExactList.convertLeadingDims`
derives packed leading dimensions from it:

```yaml
    BenchmarkFinalParameters:
      - ProblemSizes:
        - Exact: [ M, N, batch, K ]
```

`[392, 2048, 1, 1024]` expands to `[392, 2048, 1, 1024, 392, 392, 392, 1024]`.

Read the sizes off the gtest name, which `matmul_gtest.cpp` builds as
`<transA><transB>_M_N_K_alpha_lda_ldb_beta_ldc_ldd[_lde]_batch`:

```
..._NN_392_2048_1024_1_392_1024_0_392_392_1
     M=392 N=2048 K=1024 alpha=1 lda=392 ldb=1024 beta=0 ldc=392 ldd=392 batch=1
```

Then align `GlobalParameters` data init with the test, since these change which
code path runs. Notably `beta=0` in the gtest means `DataInitTypeBeta: 0`; the
converter defaults it to `1`, and beta=0 skips the C load in the store path.
Init enums: `0=Zero, 1=One, 2=Two, 3=Random, 12=TrigCos, 13=TrigSin`.

### 6. Regenerate and diff

Build the kernel from the YAML, then compare the generated name against the
runtime one:

```bash
python3 .cursor/skills/tensile-kernel-name-to-yaml/scripts/diff_kernel_names.py \
  '<runtime name>' '<generated name>'
```

The script exits non-zero only on differences that change the generated kernel.
Iterate on steps 4-5 until it reports `MATCH`.

## Kernel name vs solution name

`KernelNameMin` omits the runtime dispatch parameters that `SolutionNameMin`
includes, so a raw string comparison between the two always "fails". Per
`Naming.py::_INTERNAL_ARGS`, kernels differing only in these compile to
identical code objects:

`GlobalSplitU` (GSU), `GlobalSplitUCoalesced` (GSUC),
`GlobalSplitUWorkGroupMappingRoundRobin` (GSUWGMRR), `StaggerU` (SU),
`StaggerUStride` (SUS), `StaggerUMapping` (SUM), `WorkGroupMapping` (WGM),
`WorkGroupMappingXCCGroup` (WGMXCCG), `SFCWGM`.

`WorkGroupMappingXCC` (WGMXCC) is **not** in that set — it does affect codegen.
`diff_kernel_names.py` already classifies these correctly.

## Decoding tokens without a logic file

When no logic file matches, decode the name directly:

```bash
python3 .cursor/skills/tensile-kernel-name-to-yaml/scripts/decode_kernel_name.py '<name>' \
  --tensilelite projects/hipblaslt/tensilelite
```

It prints one row per token with the parameter it maps to, flags runtime
dispatch parameters, and lists any token it could not resolve. Feed the
non-default values into `ForkParameters` of a hand-written config, using an
existing test config such as
`projects/hipblaslt/tensilelite/Tensile/Tests/common/gemm/gfx12/` as the
skeleton.

The naming rule the script implements (`Naming.py`): a token prefix is the
uppercase letters of the parameter name, and the suffix is the value —
booleans as `0`/`1`, negatives as `n1`, lists joined by `_`. So `LBSPPA512` is
`LdsBlockSizePerPadA: 512` and `WGMXCCGn1` is `WorkGroupMappingXCCGroup: -1`.
An abbreviation can be ambiguous (`AFEM` is both
`AssertFree0ElementMultiple` and `AssertFree1ElementMultiple`, emitted in that
order); the script lists all candidates.

The leading `Cijk_Ailk_Bljk_HHS_BH_...` prefix is not parameter-encoded — it
comes from `ProblemType.__str__` in `SolutionStructs/Problem.py`. Read that
function to decode index assignments, data types, and feature tokens
(`Bias`, `HA_S`, `SAV`, `UserArgs`).

## Reference paths

| What | Where |
|---|---|
| Name construction | `projects/hipblaslt/tensilelite/Tensile/SolutionStructs/Naming.py` |
| ProblemType prefix, defaults | `projects/hipblaslt/tensilelite/Tensile/SolutionStructs/Problem.py` |
| Parameters in names | `projects/hipblaslt/tensilelite/Tensile/Common/RequiredParameters.py` |
| Legal values | `projects/hipblaslt/tensilelite/Tensile/Common/ValidParameters.py` |
| Derived-parameter rules | `projects/hipblaslt/tensilelite/Tensile/SolutionStructs/Solution.py` |
| Converter | `projects/hipblaslt/tensilelite/Tensile/TensileLibLogicToYaml.py` |
| gtest case names | `projects/hipblaslt/clients/tests/src/matmul_gtest.cpp` |
