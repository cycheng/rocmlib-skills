#!/usr/bin/env python3
# Copyright Advanced Micro Devices, Inc., or its affiliates.
# SPDX-License-Identifier: MIT
"""Decode a TensileLite kernel/solution name into parameter/value pairs.

Token prefixes are the uppercase letters of the parameter name
(Naming.py::getParameterNameAbbreviation), so the mapping is reconstructed by
scanning the parameter registries textually -- no Tensile/rocisa import needed.
"""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

# Runtime dispatch parameters (Naming.py::_INTERNAL_ARGS plus GlobalSplitU).
# Present in SolutionNameMin, absent from KernelNameMin; kernels differing only
# in these compile to identical code objects.
INTERNAL_ARGS = (
    "WorkGroupMapping",
    "WorkGroupMappingXCCGroup",
    "StaggerU",
    "StaggerUStride",
    "StaggerUMapping",
    "GlobalSplitU",
    "GlobalSplitUCoalesced",
    "GlobalSplitUWorkGroupMappingRoundRobin",
    "SFCWGM",
)

# Dict keys ("Param": ...) and bare list/set entries ('Param',).
KEY_RE = re.compile(r"""^\s{2,}['"]([A-Za-z0-9]+)['"]\s*(?::|,?$)""")
TOKEN_RE = re.compile(r"^([A-Z][A-Za-z]*?)((?:n?\d.*)?)$")


def abbrev(name):
    return "".join(c for c in name if c.isupper())


def load_params(tensilelite):
    """abbreviation -> sorted list of parameter names, from the registries."""
    sources = [
        # Authoritative list of parameters that appear in generated names.
        tensilelite / "Tensile" / "Common" / "RequiredParameters.py",
        tensilelite / "Tensile" / "Common" / "ValidParameters.py",
        tensilelite / "Tensile" / "SolutionStructs" / "Problem.py",
    ]
    names = set()
    for src in sources:
        if not src.is_file():
            sys.exit(f"error: cannot read {src} -- is --tensilelite correct?")
        for line in src.read_text().splitlines():
            m = KEY_RE.match(line)
            if m:
                names.add(m.group(1))
    table = defaultdict(list)
    for n in names:
        a = abbrev(n)
        if a:
            table[a].append(n)
    return {a: sorted(v) for a, v in table.items()}


def split_name(name):
    """(problem_type_prefix, [solution tokens]).

    The solution-parameter tail starts at the MT<m>x<n>x<k> macro-tile token.
    """
    parts = name.split("_")
    for i, p in enumerate(parts):
        if re.fullmatch(r"MT\d+x\d+x\d+", p):
            return "_".join(parts[:i]), parts[i:]
    return "", parts


def group_tokens(tokens):
    """Rejoin numeric continuation tokens, e.g. MIWT1 + 1 -> MIWT1_1."""
    out = []
    for t in tokens:
        if out and re.fullmatch(r"n?\d+", t) and not re.match(r"^[A-Z]", t):
            out[-1] += "_" + t
        elif out and re.fullmatch(r"\d+", t):
            out[-1] += "_" + t
        else:
            out.append(t)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("name", help="kernel or solution name")
    ap.add_argument(
        "--tensilelite",
        type=Path,
        default=Path("projects/hipblaslt/tensilelite"),
        help="path to the tensilelite directory (default: %(default)s)",
    )
    args = ap.parse_args()

    table = load_params(args.tensilelite.resolve())
    internal = {abbrev(n) for n in INTERNAL_ARGS}

    prefix, tokens = split_name(args.name.strip())
    print(f"ProblemType prefix : {prefix}")
    print("  (decode via ProblemType.__str__ in SolutionStructs/Problem.py)\n")

    rows, unknown = [], []
    for tok in group_tokens(tokens):
        m = TOKEN_RE.match(tok)
        if not m:
            unknown.append(tok)
            continue
        key, val = m.group(1), m.group(2)
        while key and key not in table:  # trailing caps may belong to the value
            key, val = key[:-1], key[-1] + val
        if not key:
            unknown.append(tok)
            continue
        val = val.replace("n", "-") if val.startswith("n") else val
        flag = "internal" if key in internal else ""
        rows.append((tok, key, val or "(flag)", ", ".join(table[key]), flag))

    w = max((len(r[0]) for r in rows), default=5)
    print(f"{'TOKEN'.ljust(w)}  {'VALUE'.ljust(10)}  PARAMETER")
    print("-" * (w + 60))
    for tok, key, val, params, flag in rows:
        mark = "  [internal arg]" if flag else ""
        print(f"{tok.ljust(w)}  {val.ljust(10)}  {params}{mark}")

    if unknown:
        print(f"\nUndecoded tokens: {unknown}")
    print(f"\n{len(rows)} tokens decoded, {len(unknown)} undecoded")


if __name__ == "__main__":
    main()
