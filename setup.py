# Copyright 2024 Broadcom Corporation
# SPDX-License-Identifier: Apache-2.0
#
import platform

from setuptools import Distribution, setup

# If crosstool is updated to a newer version of glibc this should get updated
# too. Would also be nice to detect this instead.
# hint: grep CT_GLIBC_VERSION src/ppt/_config/x86_64/x86_64-linux-gnu-ct-ng.config
GLIBC_VERSION = "2.17"


def plat_name():
    return f"manylinux_{GLIBC_VERSION.replace('.', '_')}_{platform.machine()}"


setup(
    options={
        "bdist_wheel": {
            "plat_name": f"{plat_name()}",
            "python_tag": "py3",
        }
    }
)
