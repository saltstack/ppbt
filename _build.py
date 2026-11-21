# Copyright 2024-2026 Broadcom Corporation
# SPDX-License-Identifier: Apache-2.0
#
"""
Build backend for the base ``ppbt`` wheel.

Lives at the repo root (outside ``src/``) so it is NOT shipped in the
installed wheel.  That keeps the runtime ``ppbt`` package free of
build-time machinery (setuptools, tarfile boilerplate, subprocess
helpers) which ``relenv`` otherwise ends up importing when it only
wants ``ppbt.common``.

Helpers it needs from ``ppbt.common`` (``build_arch``, ``get_triplet``,
``extract_archive``, ``PPBTException``) are inlined so this file does
not depend on the package it is building.
"""
import base64
import csv
import hashlib
import http.client
import os
import pathlib
import platform
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request

from setuptools import build_meta as _st_build_meta

build_sdist = _st_build_meta.build_sdist
build_wheel = _st_build_meta.build_wheel
get_requires_for_build_sdist = _st_build_meta.get_requires_for_build_sdist
get_requires_for_build_wheel = _st_build_meta.get_requires_for_build_wheel
prepare_metadata_for_build_wheel = _st_build_meta.prepare_metadata_for_build_wheel

CT_NG_VER = "1.26.0"
CT_URL = "http://crosstool-ng.org/download/crosstool-ng/crosstool-ng-{version}.tar.bz2"
CT_GIT_REPO = "https://github.com/crosstool-ng/crosstool-ng.git"
CICD = "CI" in os.environ
PATCHELF_VERSION = "0.18.0"
PATCHELF_SOURCE = (
    f"https://github.com/NixOS/patchelf/releases/download/"
    f"{PATCHELF_VERSION}/patchelf-{PATCHELF_VERSION}.tar.gz"
)

_build_wheel = build_wheel
_build_sdist = build_sdist


class BuildError(RuntimeError):
    """Generic build error."""


def build_arch():
    """Return the lowercased host machine name."""
    return platform.machine().lower()


def get_triplet(machine=None, plat=None):
    """Build a GNU triplet for ``machine`` + ``plat`` (host defaults)."""
    if not plat:
        plat = sys.platform
    if not machine:
        machine = build_arch()
    if plat == "darwin":
        return f"{machine}-macos"
    if plat == "win32":
        return f"{machine}-win"
    if plat == "linux":
        return f"{machine}-linux-gnu"
    raise BuildError(f"Unknown platform {plat}")


def extract_archive(to_dir, archive):
    """Extract ``archive`` (tar.gz / tar.xz / tar.bz2) into ``to_dir``."""
    if archive.endswith("tgz") or archive.endswith("gz"):
        mode = "r:gz"
    elif archive.endswith("xz"):
        mode = "r:xz"
    elif archive.endswith("bz2"):
        mode = "r:bz2"
    else:
        mode = "r"
    with tarfile.open(archive, mode) as t:
        t.extractall(to_dir)


def _fetch(url, fp, backoff=3, timeout=30):
    if backoff < 1:
        backoff = 1
    n = 0
    while n < backoff:
        n += 1
        try:
            fin = urllib.request.urlopen(url, timeout=timeout)
            break
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            http.client.RemoteDisconnected,
        ):
            if n >= backoff:
                raise
            time.sleep(n * 10)
    try:
        block = fin.read(1024 * 300)
        while block:
            fp.write(block)
            block = fin.read(10240)
    finally:
        fin.close()


def download_url(url, dest):
    """Download ``url`` to ``dest`` dir."""
    local = os.path.join(dest, os.path.basename(url))
    print(f"Downloading {url} -> {local}")
    with open(local, "wb") as fout:
        try:
            _fetch(url, fout)
        except Exception as exc:
            print(f"Unable to download: {url} {exc}", file=sys.stderr, flush=True)
            try:
                os.unlink(local)
            except OSError:
                pass
            raise
    return local


def runcmd(cmd, **kwargs):
    """Run ``cmd``, raising :class:`BuildError` on non-zero exit."""
    proc = subprocess.run(cmd, **kwargs)
    if proc.returncode != 0:
        raise BuildError(f"Build cmd '{' '.join(str(c) for c in cmd)}' failed")
    return proc


def build_ppbt(branch=None):
    """Build the host native toolchain and stage it inside the package.

    Downloads+compiles crosstool-ng, runs the host native config, adds
    patchelf, tars up the result, and drops the archive + record file
    into ``src/ppbt/_toolchain/``.
    """
    cwd = pathlib.Path(os.getcwd())
    root = pathlib.Path(os.environ.get("PWD", os.getcwd()))
    build = root / "build"
    archdir = None
    try:
        print(f"  ** Build dir is: {build}")
        build.mkdir(exist_ok=True)
        if branch:
            ctngdir = build / "crosstool-ng"
            if not ctngdir.exists():
                os.chdir(build)
                subprocess.run(["git", "clone", "-b", branch, CT_GIT_REPO])
        else:
            ctngdir = build / f"crosstool-ng-{CT_NG_VER}"
            if not ctngdir.exists():
                url = CT_URL.format(version=CT_NG_VER)
                archive = download_url(url, build)
                extract_archive(build, archive)

        os.chdir(ctngdir)
        ctng = ctngdir / "ct-ng"
        if ctng.exists():
            print(f"Using existing ct-ng: {ctng}")
        else:
            print("Compiling ct-ng")
            runcmd(["./configure", "--enable-local"])
            runcmd(["make"])

        machine = platform.machine()
        toolchain = cwd / "src" / "ppbt" / "_toolchain"
        toolchain.mkdir(exist_ok=True)

        triplet = get_triplet(build_arch())
        archdir = build / triplet
        if archdir.exists():
            print(f"Toolchain directory exists: {archdir}")
        else:
            config = (
                root / "src" / "ppbt" / "_config" / machine / f"{triplet}-ct-ng.config"
            )
            if not config.exists():
                print(f"Toolchain config missing: {config}", file=sys.stderr)
                sys.exit(1)
            with open(config, "r") as rfp, open(ctngdir / ".config", "w") as wfp:
                wfp.write(rfp.read())
            os.chdir(ctngdir)
            env = os.environ.copy()
            env["CT_PREFIX"] = str(build)
            if os.getuid() == 0:
                env["CT_ALLOW_BUILD_AS_ROOT"] = "y"
                env["CT_ALLOW_BUILD_AS_ROOT_SURE"] = "y"
            if CICD:
                env["CT_LOG_PROGRESS"] = "n"
            runcmd([str(ctng), "source"], env=env)
            runcmd([str(ctng), "build"], env=env)

        source = build / f"patchelf-{PATCHELF_VERSION}"
        patchelf = source / "src" / "patchelf"
        if not source.exists():
            archive = download_url(PATCHELF_SOURCE, build)
            extract_archive(build, archive)
        if not patchelf.exists():
            os.chdir(source)
            subprocess.run(["./configure"])
            subprocess.run(["make"])

        shutil.copy(source / "src" / "patchelf", build / triplet / "bin" / "patchelf")
        os.chdir(build)
        archive = f"{triplet}.tar.xz"
        record = f"{triplet}.tar.xz.record"
        subprocess.run(["tar", "-C", str(build), "-cJf", archive, triplet], check=True)

        with open(record, "w") as rfp:
            rwriter = csv.writer(rfp)
            for walk_root, _dirs, files in os.walk(archdir):
                relroot = pathlib.Path(walk_root).relative_to(build)
                for f in files:
                    relpath = relroot / f
                    with open(relpath, "rb") as fp:
                        data = fp.read()
                    hsh = (
                        base64.urlsafe_b64encode(hashlib.sha256(data).digest())
                        .rstrip(b"=")
                        .decode()
                    )
                    hashpath = str(pathlib.Path("ppbt") / "_toolchain" / relpath)
                    rwriter.writerow([hashpath, f"sha256={hsh}", len(data)])
        shutil.copy(archive, toolchain)
        shutil.copy(record, toolchain)
    finally:
        os.chdir(cwd)


def build_wheel(wheel_directory, metadata_directory=None, config_settings=None):
    """PEP 517 wheel creation hook."""
    build_ppbt()
    return _build_wheel(wheel_directory, metadata_directory, config_settings)


def build_editable(wheel_directory, config_settings=None, metadata_directory=None):
    """PEP 660 editable hook: skip the toolchain build for dev installs."""
    return _st_build_meta.build_editable(
        wheel_directory, config_settings, metadata_directory
    )


__all__ = (
    "build_sdist",
    "build_wheel",
    "build_editable",
    "get_requires_for_build_sdist",
    "get_requires_for_build_wheel",
    "prepare_metadata_for_build_wheel",
)
