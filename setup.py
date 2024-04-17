# Copyright 2023 VMware, Inc.
# SPDX-License-Identifier: Apache-2.0
#
from setuptools import Distribution, setup
#from setuptools.command.install import install


#class CustomInstallCommand(install):
#    def run(self):
#        print("Here is where I would be running my code...")
#        install.run(self)


class BinaryDistribution(Distribution):
    def has_ext_modules(self):
        return True


setup(
    distclass=BinaryDistribution,
#    cmdclass={
#        "isntall": CustomInstallCommand
#    }
)
