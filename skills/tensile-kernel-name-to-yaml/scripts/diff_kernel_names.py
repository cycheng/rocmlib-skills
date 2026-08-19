#!/usr/bin/env python3
# Copyright Advanced Micro Devices, Inc., or its affiliates.
# SPDX-License-Identifier: MIT
"""Diff two TensileLite kernel/solution names token by token.

Differences in runtime dispatch parameters (GlobalSplitU, StaggerU,
WorkGroupMapping, ...) are reported separately: a KernelNameMin omits them
while a SolutionNameMin includes them, so they are expected when comparing a
`TENSILE_DB` kernel name against a benchmark-client solution name.
"""

import argparse
import difflib
import re
import sys

INTERNAL_ABBREVS = {
    "WGM", "WGMXCCG", "SU", "SUS", "SUM", "GSU", "GSUC", "GSUWGMRR", "SFCWGM",
}


def is_internal(token):
    m = re.match(r"^([A-Z]+?)(n?\d|$)", token)
    return bool(m) and m.group(1) in INTERNAL_ABBREVS


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("expected", help="reference name (e.g. from TENSILE_DB)")
    ap.add_argument("actual", help="name to check (e.g. from the client CSV)")
    args = ap.parse_args()

    a = args.expected.strip().split("_")
    b = args.actual.strip().split("_")
    print(f"expected: {len(a)} tokens\nactual:   {len(b)} tokens\n")

    real, dispatch = [], []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if tag == "equal":
            continue
        left, right = a[i1:i2], b[j1:j2]
        bucket = dispatch if all(is_internal(t) for t in left + right) else real
        bucket.append((tag, left, right))

    if dispatch:
        print("Runtime-dispatch differences (expected for kernel vs solution name):")
        for tag, left, right in dispatch:
            print(f"  {tag:8} expected={left or '-'}  actual={right or '-'}")
        print()

    if real:
        print("REAL differences (these change the generated kernel):")
        for tag, left, right in real:
            print(f"  {tag:8} expected={left or '-'}  actual={right or '-'}")
        sys.exit(1)

    print("MATCH: no differences outside runtime dispatch parameters.")


if __name__ == "__main__":
    main()
