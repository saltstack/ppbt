# Copyright 2024 Broadcom Corporation.
# SPDX-License-Identifier: Apache-2.0
#
import platform

from setuptools import Distribution, setup

uname = platform.uname()


setup(
    options={
        "bdist_wheel": {
            "plat_name": f"{uname.system.lower()}_{uname.machine.lower()}",
        }
    }
)
