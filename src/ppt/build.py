# Copyright 2024 Broadcom Corporation.
# SPDX-License-Identifier: Apache-2.0
#
"""
Build a ppt wheel which includes a toolchain archive.
"""
import contextlib
import http.client
import os
import pathlib
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

from setuptools.build_meta import build_wheel

MODULE_DIR = pathlib.Path(__file__).resolve().parent


CT_NG_VER = "1.26.0"
CT_URL = "http://crosstool-ng.org/download/crosstool-ng/crosstool-ng-{version}.tar.bz2"
CT_GIT_REPO = "https://github.com/crosstool-ng/crosstool-ng.git"
TC_URL = "https://{hostname}/relenv/{version}/toolchain/{host}/{triplet}.tar.xz"
CICD = "CI" in os.environ

if sys.platform == "win32":
    DEFAULT_DATA_DIR = pathlib.Path.home() / "AppData" / "Local" / "ppt"
else:
    DEFAULT_DATA_DIR = pathlib.Path.home() / ".local" / "ppt"

DATA_DIR = pathlib.Path(os.environ.get("PPT_DATA", DEFAULT_DATA_DIR)).resolve()

_build_wheel = build_wheel

def build_arch():
    """
    Return the current machine.
    """
    machine = platform.machine()
    return machine.lower()


def get_triplet(machine=None, plat=None):
    """
    Get the target triplet for the specified machine and platform.

    If any of the args are None, it will try to deduce what they should be.

    :param machine: The machine for the triplet
    :type machine: str
    :param plat: The platform for the triplet
    :type plat: str

    :raises RelenvException: If the platform is unknown

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
        raise RelenvException(f"Unknown platform {plat}")


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
    # Late import so we do not import hashlib before runtime.bootstrap is called.
    import urllib.error
    import urllib.request

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
        # fp.close()


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

    :raises RelenvException: If the command finishes with a non zero exit code
    """
    proc = subprocess.run(*args, **kwargs)
    if proc.returncode != 0:
        raise BaseException("Build cmd '{}' failed".format(" ".join(args[0])))
    return proc




def build_ppt(static=False, branch=None):
    """Compile and install gdb to the prefix."""
    cwd = os.getcwd()
    try:

        DATA_DIR.parent.mkdir(exist_ok=True)
        DATA_DIR.mkdir(exist_ok=True)

        if branch:
            ctngdir = DATA_DIR / "crosstool-ng"
            if not ctngdir.exists():
                os.chdir(DATA_DIR)
                subprocess.run(["git", "clone", "-b", barnch, CT_GIT_REPO])
        else:
            ctngdir = DATA_DIR / f"crosstool-ng-{CT_NG_VER}"
            if not ctngdir.exists():
                url = CT_URL.format(version=CT_NG_VER)
                archive = download_url(url, DATA_DIR)
                extract_archive(DATA_DIR, archive)

        os.chdir(ctngdir)

        ctng = ctngdir / "ct-ng"

        if ctng.exists():
            print(f"Using existing ct-ng: {ctng}")
        else:
            print(f"Compiling ct-ng: {ctng}")
            runcmd(["./configure", "--enable-local"])
            runcmd(["make"])

        print(f"ct-ng compiled: {ctng}")

        arch = build_arch()
        machine = platform.machine()
        toolchain = MODULE_DIR / "_toolchain"

        print(f"toolchain: {toolchain}")

        toolchain.mkdir(exist_ok=True)
        os.chdir(toolchain)

        triplet = get_triplet(arch)
        archdir = toolchain / triplet
        print(f"Arch dir is {archdir}")

        if archdir.exists():
            print("Toolchain directory exists: {}".format(archdir))
        else:
            config = (
                MODULE_DIR / "_config" / machine / "{}-ct-ng.config".format(triplet)
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
            env["CT_PREFIX"] = toolchain
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

        os.chdir(toolchain)

        archive = f"{ triplet }.tar.xz"
        print(f"Archive is {archive}")
        with tarfile.open(archive, mode="w:xz") as fp:
            for root, _dirs, files in os.walk(archdir):
                relroot = pathlib.Path(root).relative_to(toolchain)
                for f in files:
                    relpath = relroot / f
                    print(f"Adding {relpath}")
                    try:
                        fp.add(relpath, relpath, recursive=False)
                    except FileNotFoundError:
                        print(f"File not found while archiving: {relpath}")

        shutil.rmtree(archdir)
    finally:
        os.chdir(cwd)


def build_wheel(wheel_directory, metadata_directory=None, config_settings=None):
    """PEP 517 wheel creation hook."""
    print("*" * 80)
    print(config_settings)
    print("*" * 80)
    static_build_dir = os.environ.get("PY_STATIC_BUILD_DIR", "")
    if static_build_dir:
        print("BUILD STATIC")
        build_ppt(static_build_dir)
        return _build_wheel(wheel_directory, metadata_directory, config_settings)
    else:
        with tempfile.TemporaryDirectory() as tmp_dist_dir:
            build_ppt(tmp_dist_dir)
            return _build_wheel(wheel_directory, metadata_directory, config_settings)
