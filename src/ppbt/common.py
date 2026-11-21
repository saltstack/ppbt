# Copyright 2024 Broadcom Corporation
# SPDX-License-Identifier: Apache-2.0
#
"""
Toolchain build environment.

The base ``ppbt`` wheel ships only the host native toolchain.  Cross
toolchains live in sibling packages (``ppbt-cross-<triplet>``) and are
discovered at runtime via the ``ppbt.toolchains`` entry point so the
base wheel stays small.
"""

import csv
import logging
import pathlib
import platform
import sys
import tarfile
from importlib import metadata

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

    :raises PPBTException: If the platform is unknown

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

# This is not reliable, the version can be modified by setuptools at build time.
DISTINFO = (
    pathlib.Path(__file__).resolve().parent.parent / f"ppbt-{__version__}.dist-info"
)

TOOLCHAINS_ENTRY_POINT = "ppbt.toolchains"


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


def _toolchain_module(triplet):
    """
    Return the Python module that ships the toolchain for ``triplet``.

    The base ``ppbt`` package supplies the host native triplet.  Sibling
    cross packages register additional triplets via the
    ``ppbt.toolchains`` entry point whose name is the triplet string and
    whose target is a module exposing ``TRIPLET``, ``TOOLCHAIN_ROOT``,
    ``ARCHIVE``, ``TOOLCHAIN`` and ``DISTINFO`` at module scope.

    :param triplet: Target triplet.
    :type triplet: str
    :return: The module providing the toolchain, or ``None`` if the
        triplet is not registered.
    """
    if triplet == TRIPLET:
        return sys.modules[__name__]
    try:
        eps = metadata.entry_points(group=TOOLCHAINS_ENTRY_POINT)
    except TypeError:
        # importlib.metadata < 3.10 doesn't take the group kwarg.
        eps = metadata.entry_points().get(TOOLCHAINS_ENTRY_POINT, [])
    for ep in eps:
        if ep.name != triplet:
            continue
        try:
            return ep.load()
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "Failed to load %s entry point %r: %r",
                TOOLCHAINS_ENTRY_POINT,
                triplet,
                exc,
            )
            return None
    return None


def archive_for(triplet):
    """
    Return the path to the toolchain archive for ``triplet``.

    Base ``ppbt`` supplies the host archive; sibling ``ppbt-cross-*``
    packages supply cross archives.  The return value is just a path --
    callers should check existence or use :func:`available_triplets`.

    :param triplet: Target triplet, as produced by :func:`get_triplet`.
    :type triplet: str
    :return: Path to ``<triplet>.tar.xz`` inside the providing package.
    :rtype: pathlib.Path
    """
    mod = _toolchain_module(triplet)
    if mod is None:
        return TOOLCHAIN_ROOT / f"{triplet}.tar.xz"
    return pathlib.Path(mod.ARCHIVE)


def toolchain_for(triplet):
    """
    Return the path where the toolchain for ``triplet`` extracts to.

    :param triplet: Target triplet.
    :type triplet: str
    :return: Path to the extracted toolchain directory inside the
        providing package.
    :rtype: pathlib.Path
    """
    mod = _toolchain_module(triplet)
    if mod is None:
        return TOOLCHAIN_ROOT / triplet
    return pathlib.Path(mod.TOOLCHAIN)


def available_triplets():
    """
    Return the triplets reachable from this Python install.

    Includes the host triplet (when the base wheel's archive is
    present) and every triplet registered via a ``ppbt.toolchains``
    entry point whose provider package has its archive present.

    :return: Triplets with an archive available.
    :rtype: list[str]
    """
    triplets = set()
    if ARCHIVE.exists():
        triplets.add(TRIPLET)
    try:
        eps = metadata.entry_points(group=TOOLCHAINS_ENTRY_POINT)
    except TypeError:
        eps = metadata.entry_points().get(TOOLCHAINS_ENTRY_POINT, [])
    for ep in eps:
        if ep.name in triplets:
            continue
        try:
            mod = ep.load()
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "Failed to load %s entry point %r: %r",
                TOOLCHAINS_ENTRY_POINT,
                ep.name,
                exc,
            )
            continue
        if pathlib.Path(mod.ARCHIVE).exists():
            triplets.add(ep.name)
    return sorted(triplets)


def _extract_toolchain(toolchain_dir, archive, distinfo, overwrite=False):
    """
    Extract ``archive`` into ``toolchain_dir`` and merge its RECORD.

    Shared between the base host toolchain and sibling cross packages
    so RECORD-merging behaviour is defined in one place.

    :param toolchain_dir: Final extracted toolchain directory.
    :type toolchain_dir: pathlib.Path
    :param archive: Path to the ``<triplet>.tar.xz`` archive.
    :type archive: pathlib.Path
    :param distinfo: Path to the providing wheel's ``*.dist-info``
        directory (which contains ``RECORD``).
    :type distinfo: pathlib.Path
    :param overwrite: Re-extract even if ``toolchain_dir`` exists.
    :type overwrite: bool
    """
    toolchain_dir = pathlib.Path(toolchain_dir)
    archive = pathlib.Path(archive)
    distinfo = pathlib.Path(distinfo)
    if toolchain_dir.exists() and not overwrite:
        log.debug("Toolchain directory exists")
        return
    log.info("Extract archive %s", archive)
    extract_archive(toolchain_dir.parent, str(archive))
    record = distinfo / "RECORD"
    archive_record = pathlib.Path(str(archive) + ".record")
    if record.exists() and archive_record.exists():
        log.info("Update pkg metadata")
        records = []
        with open(record, "r") as fp:
            records.extend(list(csv.reader(fp)))
        with open(archive_record, "r") as fp:
            records.extend(list(csv.reader(fp)))
        records = sorted(records, key=lambda row: row[0])
        with open(record, "w") as fp:
            writer = csv.writer(fp)
            for row in records:
                writer.writerow(row)


def extract(overwrite=False, triplet=None):
    """
    Extract the toolchain tarball for ``triplet`` (default: host).

    :param overwrite: Re-extract even if the toolchain directory
        already exists.
    :type overwrite: bool
    :param triplet: Target triplet.  Defaults to the host triplet.
    :type triplet: str or None
    :raises PPBTException: If no provider is registered for ``triplet``.
    """
    if triplet is None:
        triplet = TRIPLET
    mod = _toolchain_module(triplet)
    if mod is None:
        raise PPBTException(
            f"No toolchain registered for {triplet}; " f"install ppbt-cross-{triplet}?"
        )
    _extract_toolchain(
        pathlib.Path(mod.TOOLCHAIN),
        pathlib.Path(mod.ARCHIVE),
        pathlib.Path(mod.DISTINFO),
        overwrite=overwrite,
    )


def environ(auto_extract=False, triplet=None):
    """
    Toolchain build environment for ``triplet`` (default: host).

    :param auto_extract: If True and the toolchain is not yet
        extracted, extract it.  Otherwise raise.
    :type auto_extract: bool
    :param triplet: Target triplet.  Defaults to the host triplet.
    :type triplet: str or None
    :raises PPBTException: If no provider is registered for ``triplet``.
    :raises RuntimeError: If the toolchain is not extracted and
        ``auto_extract`` is False.
    """
    if triplet is None:
        triplet = TRIPLET
    mod = _toolchain_module(triplet)
    if mod is None:
        raise PPBTException(
            f"No toolchain registered for {triplet}; " f"install ppbt-cross-{triplet}?"
        )
    toolchain_dir = pathlib.Path(mod.TOOLCHAIN)
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
