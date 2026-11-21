# Copyright 2024-2026 Broadcom Corporation
# SPDX-License-Identifier: Apache-2.0
#
"""
Smoke-test the build backend module loads.

The build backend lives at the repo root (``_build.py``) rather than
inside the installed ``ppbt`` package, so the installed wheel stays
free of setuptools/subprocess machinery.  Reach it via its
``backend-path`` so the test works both in-tree and from an sdist.
"""
import importlib.util
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parent.parent / "_build.py"


def test_build_backend_imports():
    """``_build.py`` loads and exposes the PEP 517 hooks."""
    spec = importlib.util.spec_from_file_location("_build_under_test", BACKEND)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for hook in (
        "build_sdist",
        "build_wheel",
        "build_editable",
        "prepare_metadata_for_build_wheel",
    ):
        assert callable(getattr(mod, hook)), f"backend missing {hook}"
