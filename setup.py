from setuptools import setup

requirements = [
    'python-json-logger >=0.1.11, <2.0.0',
    'boto3 >= 1.10.17'
]

setup(
    name='fail_aws_az',
    version='1.0.0',
    author='Adrian Hornsby',
    author_email='adhorn@amazon.com',
    license='MIT',
    classifiers=[
        'Development Status :: 3 - Alpha',
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3 :: Only"
    ],
    keywords='chaos engineering aws',
    description='Python script to simulate the lose of an availability zone in an AWS region.',
    packages=['scripts'],
    entry_points={
        'console_scripts': [
            'script-fail-az=scripts.fail_az:entry_point',
        ],
    },
    install_requires=requirements
)
