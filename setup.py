# Copyright 2023 VMware, Inc.
# SPDX-License-Identifier: Apache-2.0
#
from setuptools import Distribution, setup


class BinaryDistribution(Distribution):
    def has_ext_modules(self):
        return True


setup(
    distclass=BinaryDistribution,
)
