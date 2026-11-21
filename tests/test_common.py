# Copyright 2024 Broadcom Corporation
# SPDX-License-Identifier: Apache-2.0
#
"""
Tests for the public ``ppbt.common`` helpers.

Cover the three things downstream tools (relenv) rely on:

* native host toolchain lookup via :data:`ppbt.common.ARCHIVE` / :data:`TOOLCHAIN`.
* cross toolchain discovery via the ``ppbt.toolchains`` entry point.
* clear errors when a triplet has no provider installed.

No actual toolchain archive is extracted; the fixtures stand in fake
provider modules via ``monkeypatch``.
"""
import pathlib
import sys
import types

import pytest

import ppbt
import ppbt.common


def test_archive_for_host_matches_module_constant():
    """The archive for the host triplet is :data:`ARCHIVE`."""
    assert ppbt.common.archive_for(ppbt.common.TRIPLET) == ppbt.common.ARCHIVE


def test_toolchain_for_host_matches_module_constant():
    """The toolchain dir for the host triplet is :data:`TOOLCHAIN`."""
    assert ppbt.common.toolchain_for(ppbt.common.TRIPLET) == ppbt.common.TOOLCHAIN


def test_public_api_reexports():
    """New helpers are reachable via the top-level ``ppbt`` namespace."""
    assert ppbt.archive_for is ppbt.common.archive_for
    assert ppbt.toolchain_for is ppbt.common.toolchain_for
    assert ppbt.available_triplets is ppbt.common.available_triplets


def _make_fake_provider(tmp_path, triplet, module_name):
    """Build a fake sibling-package module with ARCHIVE etc."""
    root = tmp_path / module_name / "_toolchain"
    root.mkdir(parents=True)
    archive = root / f"{triplet}.tar.xz"
    toolchain = root / triplet
    distinfo = tmp_path / f"{module_name}-0.2.0.dist-info"
    distinfo.mkdir()

    mod = types.ModuleType(module_name)
    mod.TRIPLET = triplet
    mod.TOOLCHAIN_ROOT = root
    mod.ARCHIVE = archive
    mod.TOOLCHAIN = toolchain
    mod.DISTINFO = distinfo
    sys.modules[module_name] = mod
    return mod


class _FakeEntryPoint:
    def __init__(self, name, module):
        self.name = name
        self._module = module

    def load(self):
        return self._module


@pytest.fixture
def fake_cross(tmp_path, monkeypatch):
    """Register a fake cross provider via the entry-point group."""
    triplet = "cross-test-linux-gnu"
    module_name = "_ppbt_fake_cross_provider"
    mod = _make_fake_provider(tmp_path, triplet, module_name)
    eps = [_FakeEntryPoint(triplet, mod)]
    monkeypatch.setattr(ppbt.common.metadata, "entry_points", lambda group=None: eps)
    yield triplet, mod
    sys.modules.pop(module_name, None)


def test_archive_for_resolves_cross_provider_entry_point(fake_cross):
    """``archive_for(triplet)`` returns the sibling package's archive."""
    triplet, mod = fake_cross
    assert ppbt.common.archive_for(triplet) == mod.ARCHIVE


def test_toolchain_for_resolves_cross_provider_entry_point(fake_cross):
    """``toolchain_for(triplet)`` returns the sibling package's toolchain dir."""
    triplet, mod = fake_cross
    assert ppbt.common.toolchain_for(triplet) == mod.TOOLCHAIN


def test_available_triplets_includes_cross_when_archive_present(fake_cross):
    """Cross triplet shows up in ``available_triplets`` once its archive exists."""
    triplet, mod = fake_cross
    assert triplet not in ppbt.common.available_triplets()
    mod.ARCHIVE.touch()
    assert triplet in ppbt.common.available_triplets()


def test_archive_for_unknown_triplet_falls_back_to_base_path(monkeypatch):
    """Unknown triplet falls back to a predictable base-package path."""
    monkeypatch.setattr(ppbt.common.metadata, "entry_points", lambda group=None: [])
    path = ppbt.common.archive_for("mips64-linux-gnu")
    assert path.parent == ppbt.common.TOOLCHAIN_ROOT
    assert path.name == "mips64-linux-gnu.tar.xz"


def test_extract_without_provider_raises(monkeypatch):
    """``extract`` on an unregistered triplet gives a helpful error."""
    monkeypatch.setattr(ppbt.common.metadata, "entry_points", lambda group=None: [])
    with pytest.raises(ppbt.common.PPBTException) as exc:
        ppbt.common.extract(triplet="mips64-linux-gnu")
    assert "mips64-linux-gnu" in str(exc.value)
    assert "ppbt-cross-mips64-linux-gnu" in str(exc.value)


def test_environ_without_provider_raises(monkeypatch):
    """``environ`` on an unregistered triplet gives a helpful error."""
    monkeypatch.setattr(ppbt.common.metadata, "entry_points", lambda group=None: [])
    with pytest.raises(ppbt.common.PPBTException):
        ppbt.common.environ(triplet="mips64-linux-gnu")


def test_environ_defaults_to_host(tmp_path, monkeypatch):
    """``environ()`` without a triplet returns env for the host toolchain."""
    fake_root = tmp_path / "_toolchain"
    fake_root.mkdir()
    fake_toolchain = fake_root / ppbt.common.TRIPLET
    (fake_toolchain / "bin").mkdir(parents=True)
    monkeypatch.setattr(ppbt.common, "TOOLCHAIN_ROOT", fake_root)
    monkeypatch.setattr(ppbt.common, "TOOLCHAIN", fake_toolchain)
    env = ppbt.common.environ()
    assert pathlib.Path(env["TOOLCHAIN_PATH"]) == fake_toolchain
    assert pathlib.PurePath(env["CC"]).name == f"{ppbt.common.TRIPLET}-gcc"


def test_environ_accepts_triplet(fake_cross):
    """``environ(triplet=...)`` returns env for the provider's toolchain."""
    triplet, mod = fake_cross
    (mod.TOOLCHAIN / "bin").mkdir(parents=True)
    env = ppbt.common.environ(triplet=triplet)
    assert pathlib.Path(env["TOOLCHAIN_PATH"]) == mod.TOOLCHAIN
    assert pathlib.PurePath(env["CC"]).name == f"{triplet}-gcc"
