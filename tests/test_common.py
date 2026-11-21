# Copyright 2024 Broadcom Corporation
# SPDX-License-Identifier: Apache-2.0
#
"""
Tests for the public ``ppbt.common`` helpers.

These do not require a real toolchain to be extracted; they exercise the
path/lookup logic that downstream tools (relenv) use to pick native vs
cross tarballs out of the installed wheel.
"""
import pathlib

import ppbt
import ppbt.common


def test_archive_for_returns_expected_path():
    """``archive_for`` returns ``_toolchain/<triplet>.tar.xz``."""
    archive = ppbt.common.archive_for("aarch64-linux-gnu")
    assert archive.name == "aarch64-linux-gnu.tar.xz"
    assert archive.parent == ppbt.common.TOOLCHAIN_ROOT


def test_toolchain_for_returns_expected_path():
    """``toolchain_for`` returns ``_toolchain/<triplet>/``."""
    tc = ppbt.common.toolchain_for("aarch64-linux-gnu")
    assert tc.name == "aarch64-linux-gnu"
    assert tc.parent == ppbt.common.TOOLCHAIN_ROOT


def test_archive_for_host_matches_module_constant():
    """The archive for the host triplet is :data:`ARCHIVE`."""
    host_archive = ppbt.common.archive_for(ppbt.common.TRIPLET)
    assert host_archive == ppbt.common.ARCHIVE


def test_toolchain_for_host_matches_module_constant():
    """The toolchain dir for the host triplet is :data:`TOOLCHAIN`."""
    host_tc = ppbt.common.toolchain_for(ppbt.common.TRIPLET)
    assert host_tc == ppbt.common.TOOLCHAIN


def test_available_triplets_returns_sorted_list(tmp_path, monkeypatch):
    """``available_triplets`` reports archives present in ``_toolchain/``."""
    fake_root = tmp_path / "_toolchain"
    fake_root.mkdir()
    (fake_root / "aarch64-linux-gnu.tar.xz").touch()
    (fake_root / "x86_64-linux-gnu.tar.xz").touch()
    # A non-archive file in the same dir must be ignored.
    (fake_root / "README.md").touch()
    monkeypatch.setattr(ppbt.common, "TOOLCHAIN_ROOT", fake_root)
    assert ppbt.common.available_triplets() == [
        "aarch64-linux-gnu",
        "x86_64-linux-gnu",
    ]


def test_available_triplets_empty_when_no_archives(tmp_path, monkeypatch):
    """``available_triplets`` returns an empty list on an unpacked source checkout."""
    fake_root = tmp_path / "_toolchain"
    fake_root.mkdir()
    monkeypatch.setattr(ppbt.common, "TOOLCHAIN_ROOT", fake_root)
    assert ppbt.common.available_triplets() == []


def test_public_api_reexports():
    """New helpers are reachable via the top-level ``ppbt`` namespace."""
    assert ppbt.archive_for is ppbt.common.archive_for
    assert ppbt.toolchain_for is ppbt.common.toolchain_for
    assert ppbt.available_triplets is ppbt.common.available_triplets


def test_environ_defaults_to_host(tmp_path, monkeypatch):
    """``environ()`` without a triplet returns env for the host toolchain."""
    # Pretend the host toolchain is extracted so ``environ`` doesn't raise.
    fake_root = tmp_path / "_toolchain"
    fake_root.mkdir()
    fake_toolchain = fake_root / ppbt.common.TRIPLET
    (fake_toolchain / "bin").mkdir(parents=True)
    monkeypatch.setattr(ppbt.common, "TOOLCHAIN_ROOT", fake_root)
    monkeypatch.setattr(ppbt.common, "TOOLCHAIN", fake_toolchain)
    env = ppbt.common.environ()
    assert pathlib.Path(env["TOOLCHAIN_PATH"]) == fake_toolchain
    assert env["CC"].endswith(f"bin/{ppbt.common.TRIPLET}-gcc")


def test_environ_accepts_triplet(tmp_path, monkeypatch):
    """``environ(triplet=...)`` returns env for the named cross toolchain."""
    fake_root = tmp_path / "_toolchain"
    fake_root.mkdir()
    # Use the "other" arch so we actually exercise the triplet= branch
    # regardless of which host arch is running the test suite.
    cross_triplet = (
        "aarch64-linux-gnu"
        if ppbt.common.TRIPLET.startswith("x86_64")
        else "x86_64-linux-gnu"
    )
    fake_cross = fake_root / cross_triplet
    (fake_cross / "bin").mkdir(parents=True)
    monkeypatch.setattr(ppbt.common, "TOOLCHAIN_ROOT", fake_root)
    env = ppbt.common.environ(triplet=cross_triplet)
    assert pathlib.Path(env["TOOLCHAIN_PATH"]) == fake_cross
    assert env["CC"].endswith(f"bin/{cross_triplet}-gcc")
