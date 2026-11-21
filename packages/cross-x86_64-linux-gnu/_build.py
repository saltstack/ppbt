# Copyright 2024-2026 Broadcom Corporation
# SPDX-License-Identifier: Apache-2.0
#
"""
Build a ``ppbt-cross-x86_64-linux-gnu`` wheel.

Produces a crosstool-ng toolchain that runs on the wheel's host arch
(aarch64) and targets ``x86_64-linux-gnu``.  The tarball is stashed
inside this package's ``_toolchain/`` dir so the base ``ppbt`` package
can discover it via the ``ppbt.toolchains`` entry point.
"""
import base64
import csv
import hashlib
import http.client
import os
import pathlib
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


def build_editable(wheel_directory, config_settings=None, metadata_directory=None):
    """PEP 660 editable hook: skip the toolchain build."""
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

TRIPLET = "x86_64-linux-gnu"
PKG_MODULE = "ppbt_cross_x86_64_linux_gnu"
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


def runcmd(cmd, **kwargs):
    """Run ``cmd``, raising :class:`BuildError` on non-zero exit."""
    proc = subprocess.run(cmd, **kwargs)
    if proc.returncode != 0:
        raise BuildError(f"Build cmd '{' '.join(str(c) for c in cmd)}' failed")
    return proc


def _prepare_crosstool_ng(build):
    ctngdir = build / f"crosstool-ng-{CT_NG_VER}"
    if not ctngdir.exists():
        archive = download_url(CT_URL.format(version=CT_NG_VER), build)
        extract_archive(build, archive)
    ctng = ctngdir / "ct-ng"
    if not ctng.exists():
        print("Compiling ct-ng")
        os.chdir(ctngdir)
        runcmd(["./configure", "--enable-local"])
        runcmd(["make"])
    return ctngdir, ctng


def _prepare_patchelf(build):
    source = build / f"patchelf-{PATCHELF_VERSION}"
    patchelf = source / "src" / "patchelf"
    if not source.exists():
        archive = download_url(PATCHELF_SOURCE, build)
        extract_archive(build, archive)
    if not patchelf.exists():
        os.chdir(source)
        runcmd(["./configure"])
        runcmd(["make"])
    return patchelf


def build_toolchain():
    """Build the cross toolchain and stage it inside this package."""
    cwd = pathlib.Path(os.getcwd())
    root = pathlib.Path(os.environ.get("PWD", os.getcwd()))
    build = root / "build"
    build.mkdir(exist_ok=True)
    pkg_src = cwd / "src" / PKG_MODULE
    toolchain_dir = pkg_src / "_toolchain"
    toolchain_dir.mkdir(exist_ok=True)
    config = pkg_src / "_config" / f"{TRIPLET}-ct-ng.config"
    if not config.exists():
        print(f"Cross config missing: {config}", file=sys.stderr)
        sys.exit(1)
    try:
        ctngdir, ctng = _prepare_crosstool_ng(build)
        patchelf = _prepare_patchelf(build)

        archdir = build / TRIPLET
        if not archdir.exists():
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

        shutil.copy(patchelf, archdir / "bin" / "patchelf")
        os.chdir(build)
        archive = f"{TRIPLET}.tar.xz"
        record = f"{TRIPLET}.tar.xz.record"
        subprocess.run(["tar", "-C", str(build), "-cJf", archive, TRIPLET], check=True)
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
                    hashpath = str(pathlib.Path(PKG_MODULE) / "_toolchain" / relpath)
                    rwriter.writerow([hashpath, f"sha256={hsh}", len(data)])
        print(f"Copying {archive} to {toolchain_dir}")
        shutil.copy(archive, toolchain_dir)
        print(f"Copying {record} to {toolchain_dir}")
        shutil.copy(record, toolchain_dir)
    finally:
        os.chdir(cwd)


def build_wheel(wheel_directory, metadata_directory=None, config_settings=None):
    """PEP 517 wheel creation hook."""
    build_toolchain()
    return _build_wheel(wheel_directory, metadata_directory, config_settings)
