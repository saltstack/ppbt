# Copyright 2024 Broadcom Corporation
# SPDX-License-Identifier: Apache-2.0
#
"""
Toolchain build environment.
"""

import csv
import pathlib

from .build import build_arch, extract_archive, get_triplet

triplet = get_triplet(build_arch())

archive = pathlib.Path(__file__).parent / "_toolchain" / f"{triplet}.tar.xz"
toolchain = pathlib.Path(__file__).parent / "_toolchain" / triplet
toolchain_root = pathlib.Path(__file__).parent / "_toolchain"


distinfo = pathlib.Path(__file__).resolve().parent.parent / "ppt-0.1.0.dist-info"


def environ():
    """
    Toolchain build environment.
    """
    if toolchain.exists():
        print("Toolchain directory exists")
    else:
        print("extract archive")
        extract_archive(toolchain_root, str(archive))
        record = distinfo / "RECORD"
        if record.exists():
            records = []
            with open(record, "r") as fp:
                for row in csv.reader(fp):
                    records.append(row)
            with open(str(archive) + ".record", "r") as fp:
                for row in csv.reader(fp):
                    records.append(row)
            records = sorted(records, key=lambda _: _[0])
            with open(record, "w") as fp:
                writer = csv.writer(fp)
                for row in records:
                    writer.writerow(row)
    basebin = toolchain / "bin" / triplet
    return {
        "TOOLCHAIN_PATH": f"{toolchain}",
        "CC": f"{basebin}-gcc",
        "CXX": f"{basebin}-g++",
        "CFLAGS": f"-I{toolchain}/{triplet}/sysroot/usr/include",
        "CPPFLAGS": f"-I{toolchain}/{triplet}/sysroot/usr/include",
        "CMAKE_FLAGS": f"-I{toolchain}/{triplet}/sysroot/usr/include",
        "LDFLAGS": f"-L{toolchain}/{triplet}/sysroot/lib",
    }
