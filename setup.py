#!/usr/bin/env python

if __name__ == "__main__":
    from setuptools import setup, find_packages
    setup(
        name="exps",
        version='0.1',
        description='exps',
        url='https://github.com/nmiculinic/exps',
        packages=find_packages(),
        install_requires=[
            'cytoolz',
            'dash',
            'dash_core_components',
            'dash_html_components',
            'dash-renderer',
            'fn',
            'sqlalchemy',
            'pyfunctional',
            'pyyaml',
            'numpy',
            'pandas',
        ],
        include_dirs=[],
    )
