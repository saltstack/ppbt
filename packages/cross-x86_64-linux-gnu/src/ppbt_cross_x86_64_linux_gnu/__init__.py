# Copyright 2024-2026 Broadcom Corporation
# SPDX-License-Identifier: Apache-2.0
"""
Cross toolchain plugin: x86_64-linux-gnu target.

This package ships a crosstool-ng-built GCC targeting
``x86_64-linux-gnu`` whose driver binaries run on the wheel's host arch
(aarch64).  Discovered by the base ``ppbt`` package at runtime via the
``ppbt.toolchains`` entry point.
"""
import pathlib

__version__ = "0.2.0"

TRIPLET = "x86_64-linux-gnu"
TOOLCHAIN_ROOT = pathlib.Path(__file__).parent / "_toolchain"
ARCHIVE = TOOLCHAIN_ROOT / f"{TRIPLET}.tar.xz"
TOOLCHAIN = TOOLCHAIN_ROOT / TRIPLET

DISTINFO = (
    pathlib.Path(__file__).resolve().parent.parent
    / f"ppbt_cross_x86_64_linux_gnu-{__version__}.dist-info"
)
