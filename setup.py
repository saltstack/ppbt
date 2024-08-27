# Copyright 2024 Broadcom Corporation.
# SPDX-License-Identifier: Apache-2.0
#
import sysconfig

from setuptools import Distribution, setup


setup(
    options={
        "bdist_wheel": {
            "plat_name": f"{sysconfig.get_platform()}",
        }
    }
)
