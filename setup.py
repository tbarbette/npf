import setuptools
from npf.version import __version__

with open("README.md", "r") as fh:
    long_description = fh.read()

install_requires=[
    'require-python-3',
    'pandas',
    'numpy',
    'regex',
    'matplotlib',
    'gitpython',
    'typing',
    'pydotplus',
    'scipy',
    'scikit-learn',
    'orderedset; python_version < "3.7.0"',
    'ordered_set; python_version >= "3.7.0"',
    'paramiko',
    'asteval',
    'cryptography==41.0.2',
    'gitdb',
    'pyasn1',
    'natsort',
    'webcolors',
    'colorama',
    'pygtrie',
    'packaging',
    'importlib_metadata'
        ]

setuptools.setup(
    name="npf",
    version=__version__,
    author="Tom Barbette",
    author_email="tom.barbette@uclouvain.be",
    install_requires=install_requires,
    description="NPF",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/tbarbette/npf",
    packages=setuptools.find_packages(),
    package_data={'': ['*.repo', '*.npf']},
    py_modules=['npf_run','npf_compare','npf_watch'],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
    entry_points = {
              'console_scripts': [
                  'npf=npf_compare:main',
                  'npf-regress=npf_run:main',
                  'npf-run=npf_run:main',
                  'npf-compare=npf_compare:main',
                  'npf-watch=npf_watch:main',
                  'npf-run.py=npf_run:main',
                  'npf-compare.py=npf_compare:main',
                  'npf-watch.py=npf_watch:main',
              ],
          },
)
