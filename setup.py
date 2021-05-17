"""Package Setup."""
from setuptools import find_packages, setup

readme = open("README.rst").read()

requirements = {
    "package": [],
    "test": [
        "pytest",
        "pytest-cov",
        "pytest-flake8",
        "pytest-mock",
        "pytest-pudb",
    ],
    "setup": [
        "pytest-runner",
    ],
}

requirements.update(all=sorted(set().union(*requirements.values())))

setup(
    name="restraint",
    version="0.0.2",
    description="Rate Limiting Module",
    long_description=readme,
    author="Kyle James Walker",
    author_email="KyleJamesWalker@gmail.com",
    url="https://github.com/KyleJamesWalker/restraint-py",
    packages=find_packages(exclude=["tests*"]),
    install_requires=requirements["package"],
    extras_require=requirements,
    setup_requires=requirements["setup"],
    license="MIT",
    classifiers=[
        "Development Status :: 1 - Planning",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Natural Language :: English",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
    ],
    test_suite="tests",
    tests_require=requirements["test"],
)
