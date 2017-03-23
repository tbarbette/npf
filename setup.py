from distutils.core import setup

desc = """\
Network Performance Framework
"""

install_requires=['python>=3',
          'numpy',
          'regex',
          'matplotlib',
          'gitpython',
          'typing'
          ]


setup(name='npf',
      version='1.0',
      packages=['npf'],
      author='Tom Barbette',
      license='GPL',
      author_email='tom.barbette@ulg.ac.be',
      long_description=desc,
      py_modules=['watcher','regression'],
      url='http://github.com/tbarbette/clickwatcher/',
      )
