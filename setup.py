# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

with open('requirements.txt') as f:
	install_requires = f.read().strip().split('\n')

# get version from __version__ variable in ice/__init__.py
from ice import __version__ as version

setup(
	name='ice',
	version=version,
	description='iCalender Extension for ERPNext',
	author='Marius Widmann',
	author_email='marius.widmann@gmail.com',
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires
)
