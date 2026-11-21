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

__version__ = "0.2.0"

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
TOOLCHAIN_ROOT = pathlib.Path(__file__).parent / "_toolchain"
ARCHIVE = TOOLCHAIN_ROOT / f"{TRIPLET}.tar.xz"
TOOLCHAIN = TOOLCHAIN_ROOT / TRIPLET


def archive_for(triplet):
    """
    Return the path to the toolchain archive for ``triplet``.

    Wheels can carry more than one toolchain: the x86_64 wheel ships
    both ``x86_64-linux-gnu.tar.xz`` (native) and
    ``aarch64-linux-gnu.tar.xz`` (cross), and vice versa for the aarch64
    wheel.  Pass the target triplet (e.g. ``aarch64-linux-gnu``) to pick
    the matching tarball.  The result's existence is caller's
    responsibility to check via :func:`available_triplets` -- the return
    value is just a path, whether or not the archive is present.

    :param triplet: Target triplet, as produced by :func:`get_triplet`.
    :type triplet: str

    :return: Path to ``<triplet>.tar.xz`` inside the package.
    :rtype: pathlib.Path
    """
    return TOOLCHAIN_ROOT / f"{triplet}.tar.xz"


def toolchain_for(triplet):
    """
    Return the path where the toolchain for ``triplet`` extracts to.

    :param triplet: Target triplet, as produced by :func:`get_triplet`.
    :type triplet: str

    :return: Path to the extracted toolchain directory.
    :rtype: pathlib.Path
    """
    return TOOLCHAIN_ROOT / triplet


def available_triplets():
    """
    Return the triplets this installed wheel can provide a toolchain for.

    Inspects ``_toolchain/`` for ``*.tar.xz`` archives and returns the
    corresponding triplets.  Order is alphabetical.

    :return: Triplets with an archive present in the package.
    :rtype: list[str]
    """
    return sorted(p.name[: -len(".tar.xz")] for p in TOOLCHAIN_ROOT.glob("*.tar.xz"))


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


def extract(overwrite=False, triplet=None):
    """
    Extract the toolchain tarball for ``triplet`` (default: the host's).

    When ``triplet`` is None the host's native toolchain is extracted,
    matching the pre-cross-support behaviour.  Pass another triplet
    (e.g. ``aarch64-linux-gnu`` on an x86_64 host) to extract a cross
    toolchain shipped alongside the native one.

    :param overwrite: Re-extract even if the toolchain directory
        already exists.
    :type overwrite: bool
    :param triplet: Target triplet to extract.  Defaults to the host
        triplet (:data:`TRIPLET`).
    :type triplet: str or None
    """
    if triplet is None:
        triplet = TRIPLET
    toolchain_dir = toolchain_for(triplet)
    archive = archive_for(triplet)
    if toolchain_dir.exists() and not overwrite:
        log.debug("Toolchain directory exists")
        return
    log.info("Extract archive %s", archive)
    extract_archive(TOOLCHAIN_ROOT, str(archive))
    record = DISTINFO / "RECORD"
    if record.exists():
        records = []
        log.info("Update pkg metadata")
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


def environ(auto_extract=False, triplet=None):
    """
    Toolchain build environment for ``triplet`` (default: the host's).

    :param auto_extract: If True and the toolchain is not yet extracted,
        extract it.  If False and it's not extracted, raise.
    :type auto_extract: bool
    :param triplet: Target triplet to return env for.  Defaults to the
        host triplet (:data:`TRIPLET`).
    :type triplet: str or None
    """
    if triplet is None:
        triplet = TRIPLET
    toolchain_dir = toolchain_for(triplet)
    if not toolchain_dir.exists():
        if auto_extract:
            extract(triplet=triplet)
        else:
            raise RuntimeError("Toolchain not extracted")
    basebin = toolchain_dir / "bin" / triplet
    return {
        "TOOLCHAIN_PATH": f"{toolchain_dir}",
        "CC": f"{basebin}-gcc",
        "CXX": f"{basebin}-g++",
        "CFLAGS": f"-I{toolchain_dir}/{triplet}/sysroot/usr/include",
        "CPPFLAGS": f"-I{toolchain_dir}/{triplet}/sysroot/usr/include",
        "CMAKE_FLAGS": f"-I{toolchain_dir}/{triplet}/sysroot/usr/include",
        "LDFLAGS": f"-L{toolchain_dir}/{triplet}/sysroot/lib",
    }
