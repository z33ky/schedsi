#!/usr/bin/env python3

import setuptools

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
    }
)
