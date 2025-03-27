import setuptools
from npf.version import __version__

with open("README.md", "r") as fh:
    long_description = fh.read()

install_requires = [
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
    'cryptography==44.0.1',
    'gitdb',
    'pyasn1',
    'natsort',
    'webcolors',
    'colorama',
    'pygtrie',
    'packaging',
    'importlib_metadata',
    'npf-web-extension >= 0.6.4',
    'nbformat',
    'nbconvert',
    'jinja2',
    'spellwise',
    'seaborn',
    'statsmodels',
    'scikit-optimize',
    'colorama',
    'scikit-optimize',
    'lark'
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
    py_modules=['npf', 'npf_regress', 'npf_watch'],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
    entry_points={
        'console_scripts': [
            'npf=npf.tests.main:main',
            'npf-regress=npf_regress:main',
            'npf-watch=npf_watch:main',

            #Backward compat
            'npf-run=npf_regress:main',
            'npf-compare=npf:main',

            #With .py (backward compat)
            'npf-run.py=npf_regress:main',
            'npf-compare.py=npf:main',
            'npf-watch.py=npf_watch:main',
        ],
    },
)
