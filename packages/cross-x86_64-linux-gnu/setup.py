# Copyright 2024-2026 Broadcom Corporation
# SPDX-License-Identifier: Apache-2.0
#
import platform

from setuptools import setup

# Keep in sync with ppbt's base crosstool-ng config.
GLIBC_VERSION = "2.17"


def plat_name():
    # The cross wheel ships binaries that *run on* the build host and
    # emit code for a different target.  The wheel's platform tag is the
    # host's, not the target's.
    return f"manylinux_{GLIBC_VERSION.replace('.', '_')}_{platform.machine()}"


setup(
    options={
        "bdist_wheel": {
            "plat_name": f"{plat_name()}",
            "python_tag": "py3",
        }
    }
)
