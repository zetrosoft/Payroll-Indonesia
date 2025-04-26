# setup.py yang dikoreksi
from setuptools import setup, find_packages
import os

# Baca versi dari file VERSION atau definisikan langsung
version = '0.0.1'  # atau versi yang Anda inginkan

# Alternatif: baca dari file VERSION jika ada
if os.path.exists('VERSION'):
    with open('VERSION', 'r') as f:
        version = f.read().strip()

setup(
    name="payroll_indonesia",
    version=version,
    description="Payroll module for Indonesian companies with local regulatory features",
    author="PT. Innovasi Terbaik Bangsa",
    author_email="danny.a.pratama@cao-group.co.id",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=["frappe", "erpnext", "hrms"],
)