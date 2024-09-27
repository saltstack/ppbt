# Copyright 2024 Broadcom Corporation
# SPDX-License-Identifier: Apache-2.0
#
"""
Build a ppbt wheel which includes a toolchain archive.
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
import time
import urllib.error
import urllib.request

from setuptools.build_meta import build_sdist, build_wheel

import ppbt.common

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


class BuildError(ppbt.common.PPBTException, RuntimeError):
    """Generic build error."""


def get_download_location(url, dest):
    """
    Get the full path to where the url will be downloaded to.

    :param url: The url to donwload
    :type url: str
    :param dest: Where to download the url to
    :type dest: str

    :return: The path to where the url will be downloaded to
    :rtype: str
    """
    return os.path.join(dest, os.path.basename(url))


def fetch_url(url, fp, backoff=3, timeout=30):
    """
    Fetch the contents of a url.

    This method will store the contents in the given file like object.
    """
    if backoff < 1:
        backoff = 1
    n = 0
    while n < backoff:
        n += 1
        try:
            fin = urllib.request.urlopen(url, timeout=timeout)
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            http.client.RemoteDisconnected,
        ):
            if n >= backoff:
                raise
            time.sleep(n * 10)
    try:
        size = 1024 * 300
        block = fin.read(size)
        while block:
            fp.write(block)
            block = fin.read(10240)
    finally:
        fin.close()


def download_url(url, dest, verbose=True, backoff=3, timeout=60):
    """
    Download the url to the provided destination.

    This method assumes the last part of the url is a filename. (https://foo.com/bar/myfile.tar.xz)

    :param url: The url to download
    :type url: str
    :param dest: Where to download the url to
    :type dest: str
    :param verbose: Print download url and destination to stdout
    :type verbose: bool

    :raises urllib.error.HTTPError: If the url was unable to be downloaded

    :return: The path to the downloaded content
    :rtype: str
    """
    local = get_download_location(url, dest)
    if verbose:
        print(f"Downloading {url} -> {local}")
    fout = open(local, "wb")
    try:
        fetch_url(url, fout, backoff, timeout)
    except Exception as exc:
        if verbose:
            print(f"Unable to download: {url} {exc}", file=sys.stderr, flush=True)
        try:
            os.unlink(local)
        except OSError:
            pass
        raise
    return local


def runcmd(*args, **kwargs):
    """
    Run a command.

    Run the provided command, raising an Exception when the command finishes
    with a non zero exit code.  Arguments are passed through to ``subprocess.run``

    :return: The process result
    :rtype: ``subprocess.CompletedProcess``

    :raises BuildError: If the command finishes with a non zero exit code
    """
    proc = subprocess.run(*args, **kwargs)
    if proc.returncode != 0:
        raise BuildError("Build cmd '{}' failed".format(" ".join(args[0])))
    return proc


def build_ppbt(branch=None, use_tempdir=True):
    """Build a toolchain and include it in the wheel.

    - Downloads and installs crosstool-ng for building a toolchain.
    - Compile a toolchain
    - Add patchelf to the toolchain's binaries
    - Create a tarball to be included in the wheel
    """
    cwd = pathlib.Path(os.getcwd())
    root = pathlib.Path(os.environ.get("PWD", os.getcwd()))
    build = root / "build"
    archdir = None
    try:
        # root = pathlib.Path(__file__).resolve().parent.parent.parent
        # build = root / "build"
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
                ppbt.common.extract_archive(build, archive)

        os.chdir(ctngdir)
        ctng = ctngdir / "ct-ng"

        if ctng.exists():
            print(f"Using existing ct-ng: {ctng}")
        else:
            print("Compiling ct-ng")
            runcmd(["./configure", "--enable-local"])
            runcmd(["make"])
            print(f"Using compiled ct-ng: {ctng}")

        arch = ppbt.common.build_arch()
        machine = platform.machine()
        toolchain = cwd / "src" / "ppbt" / "_toolchain"

        print(f"toolchain: {toolchain}")

        toolchain.mkdir(exist_ok=True)

        triplet = ppbt.common.get_triplet(arch)
        archdir = build / triplet
        print(f"Arch dir is {archdir}")
        if archdir.exists():
            print("Toolchain directory exists: {}".format(archdir))
        else:
            config = (
                root
                / "src"
                / "ppbt"
                / "_config"
                / machine
                / "{}-ct-ng.config".format(triplet)
            )
            if not config.exists():
                print("Toolchain config missing: {}".format(config))
                sys.exit(1)
            with open(config, "r") as rfp:
                print("Writing crosstool-ng .config")
                with open(ctngdir / ".config", "w") as wfp:
                    wfp.write(rfp.read())
            os.chdir(ctngdir)
            env = os.environ.copy()
            env["CT_PREFIX"] = build
            if os.getuid() == 0:
                env["CT_ALLOW_BUILD_AS_ROOT"] = "y"
                env["CT_ALLOW_BUILD_AS_ROOT_SURE"] = "y"
            if CICD:
                env["CT_LOG_PROGRESS"] = "n"
            runcmd(
                [
                    str(ctng),
                    "source",
                ],
                env=env,
            )
            runcmd(
                [
                    str(ctng),
                    "build",
                ],
                env=env,
            )

        source = build / f"patchelf-{PATCHELF_VERSION}"
        patchelf = source / "src" / "patchelf"
        if source.exists():
            print(f"Using existing patchelf source: {source}")
        else:
            print(f"Fetchin patchelf source: {PATCHELF_SOURCE}")
            archive = download_url(PATCHELF_SOURCE, build)
            ppbt.common.extract_archive(build, archive)
            os.chdir(source)

        if patchelf.exists():
            print(f"Using existing patchelf binary: {source}")
        else:
            print("Build patchelf")
            subprocess.run(["./configure"])
            subprocess.run(["make"])

        shutil.copy(source / "src" / "patchelf", build / triplet / "bin" / "patchelf")
        os.chdir(build)
        archive = f"{ triplet }.tar.xz"
        record = f"{ triplet }.tar.xz.record"
        cmd = ["tar", "-C", f"{ build }", "-cJf", f"{ archive }", f"{ triplet }"]
        subprocess.run(cmd)

        # XXX: Figure out why things break when using the tarfile module.
        with open(record, "w") as rfp:
            rwriter = csv.writer(rfp)
            for root, _dirs, files in os.walk(archdir):
                relroot = pathlib.Path(root).relative_to(build)
                for f in files:
                    print(f"Archive {relroot} / {f}")
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
        print(f"Copying {archive} to {toolchain}")
        shutil.copy(archive, toolchain)
        print(f"Copying {record} to {toolchain}")
        shutil.copy(record, toolchain)
    finally:
        # if archdir and archdir.exists():
        #    shutil.rmtree(archdir)
        os.chdir(cwd)


def build_wheel(wheel_directory, metadata_directory=None, config_settings=None):
    """PEP 517 wheel creation hook."""
    build_ppbt()
    return _build_wheel(wheel_directory, metadata_directory, config_settings)
