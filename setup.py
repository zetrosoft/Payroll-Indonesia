# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

with open('requirements.txt') as f:
    install_requires = f.read().strip().split('\n')

# get version from __version__ variable in payroll_indonesia/__init__.py
from payroll_indonesia import __version__ as version

setup(
    name='payroll_indonesia',
    version=version,
    description='Payroll module for Indonesian companies with local regulatory features',
    author='PT. Innovasi Terbaik Bangsa',
    author_email='danny.a.pratama@cao-group.co.id',
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires
)