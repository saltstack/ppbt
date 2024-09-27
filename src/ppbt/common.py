# Copyright 2024 Broadcom Corporation
# SPDX-License-Identifier: Apache-2.0
#
"""
Toolchain build environment.
"""

import csv
import logging
import pathlib
import platform
import sys
import tarfile

__version__ = "0.1.8"

log = logging.getLogger(__name__)


class PPBTException(Exception):
    """
    Base class for all ppbt exceptions.

    """


def get_triplet(machine=None, plat=None):
    """
    Get the target triplet for the specified machine and platform.

    If any of the args are None, it will try to deduce what they should be.

    :param machine: The machine for the triplet
    :type machine: str
    :param plat: The platform for the triplet
    :type plat: str

    :raises BuildError: If the platform is unknown

    :return: The target triplet
    :rtype: str
    """
    if not plat:
        plat = sys.platform
    if not machine:
        machine = build_arch()
    if plat == "darwin":
        return f"{machine}-macos"
    elif plat == "win32":
        return f"{machine}-win"
    elif plat == "linux":
        return f"{machine}-linux-gnu"
    else:
        raise PPBTException(f"Unknown platform {plat}")


def build_arch():
    """
    Return the current machine.
    """
    machine = platform.machine()
    return machine.lower()


TRIPLET = get_triplet(build_arch())
ARCHIVE = pathlib.Path(__file__).parent / "_toolchain" / f"{TRIPLET}.tar.xz"
TOOLCHAIN_ROOT = pathlib.Path(__file__).parent / "_toolchain"
TOOLCHAIN = TOOLCHAIN_ROOT / TRIPLET

# This is not reliable, the version can be modified by setuptools at build time.
DISTINFO = (
    pathlib.Path(__file__).resolve().parent.parent / f"ppbt-{__version__}.dist-info"
)


def extract_archive(to_dir, archive):
    """
    Extract an archive to a specific location.

    :param to_dir: The directory to extract to
    :type to_dir: str
    :param archive: The archive to extract
    :type archive: str
    """
    if archive.endswith("tgz"):
        read_type = "r:gz"
    elif archive.endswith("xz"):
        read_type = "r:xz"
    elif archive.endswith("bz2"):
        read_type = "r:bz2"
    else:
        read_type = "r"
    with tarfile.open(archive, read_type) as t:
        t.extractall(to_dir)


def extract(overwrite=False):
    """
    Extract the toolchain tarball.
    """
    if TOOLCHAIN.exists() and not overwrite:
        log.debug("Toolchain directory exists")
    else:
        log.info("Extract archive")
        extract_archive(TOOLCHAIN_ROOT, str(ARCHIVE))
        record = DISTINFO / "RECORD"
        if record.exists():
            records = []
            log.info("Update pkg metadata")
            with open(record, "r") as fp:
                for row in csv.reader(fp):
                    records.append(row)
            with open(str(ARCHIVE) + ".record", "r") as fp:
                for row in csv.reader(fp):
                    records.append(row)
            records = sorted(records, key=lambda _: _[0])
            with open(record, "w") as fp:
                writer = csv.writer(fp)
                for row in records:
                    writer.writerow(row)


def environ(auto_extract=False):
    """
    Toolchain build environment.
    """
    if not TOOLCHAIN.exists():
        if auto_extract:
            extract()
        else:
            raise RuntimeError("Toolchain not extracted")
    basebin = TOOLCHAIN / "bin" / TRIPLET
    return {
        "TOOLCHAIN_PATH": f"{TOOLCHAIN}",
        "CC": f"{basebin}-gcc",
        "CXX": f"{basebin}-g++",
        "CFLAGS": f"-I{TOOLCHAIN}/{TRIPLET}/sysroot/usr/include",
        "CPPFLAGS": f"-I{TOOLCHAIN}/{TRIPLET}/sysroot/usr/include",
        "CMAKE_FLAGS": f"-I{TOOLCHAIN}/{TRIPLET}/sysroot/usr/include",
        "LDFLAGS": f"-L{TOOLCHAIN}/{TRIPLET}/sysroot/lib",
    }
