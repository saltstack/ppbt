# Copyright 2023-2024 VMware, Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""
Build our python wheel.
"""
import contextlib
import http.client
import os
import pathlib
import platform
import subprocess
import shutil
import sys
import tarfile
import tempfile
import textwrap
import time

from setuptools.build_meta import *

# relenv package version
__version__ = "0.14.2"

MODULE_DIR = pathlib.Path(__file__).resolve().parent

LINUX = "linux"
WIN32 = "win32"
DARWIN = "darwin"

CT_NG_VER = "1.25.0"
CT_URL = "http://crosstool-ng.org/download/crosstool-ng/crosstool-ng-{version}.tar.bz2"
TC_URL = "https://{hostname}/relenv/{version}/toolchain/{host}/{triplet}.tar.xz"
CICD = "CI" in os.environ

CHECK_HOSTS = ("repo.saltproject.io", "woz.io")

arches = {
    LINUX: (
        "x86_64",
        "aarch64",
    ),
    DARWIN: ("x86_64", "arm64"),
    WIN32: (
        "amd64",
        "x86",
        #    "arm64", # Python 11 should support arm.
    ),
}


if sys.platform == "win32":
    DEFAULT_DATA_DIR = pathlib.Path.home() / "AppData" / "Local" / "ppt"
else:
    DEFAULT_DATA_DIR = pathlib.Path.home() / ".local" / "ppt"

DATA_DIR = pathlib.Path(os.environ.get("PPT_DATA", DEFAULT_DATA_DIR)).resolve()


class PPTException(Exception):
    """
    Base class for exeptions generated from ppt.
    """


def build_arch():
    """
    Return the current machine.
    """
    machine = platform.machine()
    return machine.lower()


def work_root(root=None):
    """
    Get the root directory that all other relenv working directories should be based on.

    :param root: An explicitly requested root directory
    :type root: str

    :return: An absolute path to the relenv root working directory
    :rtype: ``pathlib.Path``
    """
    if root is not None:
        base = pathlib.Path(root).resolve()
    else:
        base = MODULE_DIR
    return base


def work_dir(name, root=None):
    """
    Get the absolute path to the relenv working directory of the given name.

    :param name: The name of the directory
    :type name: str
    :param root: The root directory that this working directory will be relative to
    :type root: str

    :return: An absolute path to the requested relenv working directory
    :rtype: ``pathlib.Path``
    """
    root = work_root(root)
    if root == MODULE_DIR:
        base = root / "_{}".format(name)
    else:
        base = root / name
    return base


class WorkDirs:
    """
    Simple class used to hold references to working directories relenv uses relative to a given root.

    :param root: The root of the working directories tree
    :type root: str
    """

    def __init__(self, root):
        self.root = root
        self.toolchain_config = work_dir("toolchain", self.root)
        self.toolchain = work_dir("toolchain", DATA_DIR)
        self.build = work_dir("build", DATA_DIR)
        self.src = work_dir("src", DATA_DIR)
        self.logs = work_dir("logs", DATA_DIR)
        self.download = work_dir("download", DATA_DIR)

    def __getstate__(self):
        """
        Return an object used for pickling.

        :return: The picklable state
        """
        return {
            "root": self.root,
            "toolchain_config": self.toolchain_config,
            "toolchain": self.toolchain,
            "build": self.build,
            "src": self.src,
            "logs": self.logs,
            "download": self.download,
        }

    def __setstate__(self, state):
        """
        Unwrap the object returned from unpickling.

        :param state: The state to unpickle
        :type state: dict
        """
        self.root = state["root"]
        self.toolchain_config = state["toolchain_config"]
        self.toolchain = state["toolchain"]
        self.build = state["build"]
        self.src = state["src"]
        self.logs = state["logs"]
        self.download = state["download"]


def work_dirs(root=None):
    """
    Returns a WorkDirs instance based on the given root.

    :param root: The desired root of relenv's working directories
    :type root: str

    :return: A WorkDirs instance based on the given root
    :rtype: ``relenv.common.WorkDirs``
    """
    return WorkDirs(work_root(root))


def get_toolchain(arch=None, root=None):
    """
    Get a the toolchain directory, specific to the arch if supplied.

    :param arch: The architecture to get the toolchain for
    :type arch: str
    :param root: The root of the relenv working directories to search in
    :type root: str

    :return: The directory holding the toolchain
    :rtype: ``pathlib.Path``
    """
    dirs = work_dirs(root)
    if arch:
        return dirs.toolchain / "{}-linux-gnu".format(arch)
    return dirs.toolchain


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


def plat_from_triplet(plat):
    """
    Convert platform from build to the value of sys.platform.
    """
    if plat == "linux-gnu":
        return "linux"
    elif plat == "macos":
        return "darwin"
    elif plat == "win":
        return "win32"
    raise RelenvException(f"Unkown platform {plat}")


def list_archived_builds():
    """
    Return a list of version, architecture and platforms for builds.
    """
    builds = []
    dirs = work_dirs(DATA_DIR)
    for root, dirs, files in os.walk(dirs.build):
        for file in files:
            if file.endswith(".tar.xz"):
                file = file[:-7]
                version, triplet = file.split("-", 1)
                arch, plat = triplet.split("-", 1)
                builds.append((version, arch, plat))
    return builds


def archived_build(triplet=None):
    """
    Finds a the location of an archived build.

    :param triplet: The build triplet to find
    :type triplet: str

    :return: The location of the archived build
    :rtype: ``pathlib.Path``
    """
    if not triplet:
        triplet = get_triplet()
    dirs = work_dirs(DATA_DIR)
    archive = f"{triplet}.tar.xz"
    return dirs.build / archive


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


def check_url(url, timeout=30):
    """
    Check that the url returns a 200.
    """
    # Late import so we do not import hashlib before runtime.bootstrap is called.
    import urllib.request

    fin = None
    try:
        fin = urllib.request.urlopen(url, timeout=timeout)
    except Exception:
        return False
    finally:
        if fin:
            fin.close()
    return True


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


_build_wheel = build_wheel


@contextlib.contextmanager
def pushd(path):
    """
    A pushd context manager.
    """
    orig = os.getcwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(orig)


def _configure_ctng(ctngdir, dirs):
    """
    Configure crosstool-ng.

    :param ctngdir: The directory holding crosstool-ng
    :type ctngdir: str
    :param dirs: The working directories
    :type dirs: ``relenv.common.WorkDirs``
    """
    if not ctngdir.exists():
        url = CT_URL.format(version=CT_NG_VER)
        archive = download_url(url, dirs.toolchain)
        extract_archive(dirs.toolchain, archive)
    os.chdir(ctngdir)
    ctng = ctngdir / "ct-ng"
    if not ctng.exists():
        runcmd(["./configure", "--enable-local"])
        runcmd(["make"])


def build_ppt(static=False):
    """Compile and install gdb to the prefix."""
    cwd = os.getcwd()
    try:
        dirs = work_dirs()
        if not dirs.toolchain.exists():
            os.makedirs(dirs.toolchain)

        ctngdir = dirs.toolchain / "crosstool-ng-{}".format(CT_NG_VER)
        if not ctngdir.exists():
            url = CT_URL.format(version=CT_NG_VER)
            archive = download_url(url, dirs.toolchain)
            extract_archive(dirs.toolchain, archive)

        os.chdir(ctngdir)

        ctng = ctngdir / "ct-ng"

        if ctng.exists():
            print(f"Using existing ct-ng: {ctng}")
        else:
            print(f"Compiling ct-ng: {ctng}")
            runcmd(["./configure", "--enable-local"])
            runcmd(["make"])
        print(f"ct-ng compiled: {ctng}")

        os.chdir(dirs.toolchain)

        arch = build_arch()
        machine = platform.machine()

        if static:
            toolchain = dirs.toolchain
        else:
            toolchain = pathlib.Path(__file__).parent / "_toolchain"
        print(f"toolchain: {toolchain}")
        os.chdir(toolchain)
        triplet = get_triplet(arch)
        archdir = toolchain / triplet
        if archdir.exists():
            print("Toolchain directory exists: {}".format(archdir))
        else:
            config = dirs.toolchain_config / machine / "{}-ct-ng.config".format(triplet)
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

        archive = f"{ triplet }.tar.xz"
        print(f"Archive is {archive}")
        with tarfile.open(archive, mode="w:xz") as fp:
            for root, _dirs, files in os.walk(archdir):
                relroot = pathlib.Path(root).relative_to(toolchain)
                for f in files:
                    relpath = relroot / f
                    print(f"Adding {relpath}")
                    fp.add(relpath, relpath, recursive=False)
        shutil.move(archive, dirs.toolchain_config)
    finally:
        os.chdir(cwd)


def build_wheel(wheel_directory, metadata_directory=None, config_settings=None):
    """PEP 517 wheel creation hook."""
    static_build_dir = os.environ.get("PY_STATIC_BUILD_DIR", "")
    if static_build_dir:
        build_ppt(static_build_dir)
        return _build_wheel(wheel_directory, metadata_directory, config_settings)
    else:
        with tempfile.TemporaryDirectory() as tmp_dist_dir:
            build_ppt(tmp_dist_dir)
            return _build_wheel(
                wheel_directory, metadata_directory, config_settings
            )
