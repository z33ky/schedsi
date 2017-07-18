#!/usr/bin/env python3

import setuptools
from Cython.Build import cythonize

setuptools.setup(
    name="schedsi",
    version="0.4.0dev",
    description="Primitive scheduling simulator",
    author="Alexander 'z33ky' Hirsch",
    author_email="1zeeky@gmail.com",
    license="CC0",
    packages=["schedsi"],
    entry_points={
        'console_scripts': [
            'schedsi-replay = replay:main'
            'schedsi-plot = plot:main'
            ]
    },
    ext_modules=cythonize("schedsi/cpu/context.pyx")
)
