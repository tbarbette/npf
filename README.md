Click Performance Watcher
=========================

Run performance test on click using configuration files much like 
testies.

Configuration files allows matrix parameters to try many different parameters for each test files.

regression.py
-------------
This python scripts takes a test file, parse it, and run the given command for each combination of variables.

Example :
	PATH=$(pwd)/fastclick/master/bin:$PATH python regression.py tests/0050-fastudpgen.conf fastclick master-ref old-master-ref

run\_all.sh
-----------
Checkout or update a given repository, build click, and launch regression.py
for all tests in the test folder. If the script was previously ran, it will
pass the last branch HEAD to regression.py to make a comparison of last
versions.

Example :
	./run_all.sh http://gitlab.run.montefiore.ulg.ac.be/sdn-pp/fastclick.git fastclick

Writing configuration files
---------------------------

The file is made of multiple sections, starting with a % like "%file CONFIG" which means that a file named CONFIG should be created.


# Config
List of test configuration option
 - acceptable=0.01         Acceptable difference between multiple regression runs
 - n\_runs=1               Number of runs to do of each test
 - unacceptable\_n\_runs=0 Number of runs to do when the value is first rejected (to avoid false positives). Half the most abnormal runs will be rejected to have a most common value average.
 - required\_tags=         Comma-separated list of tags needed to run this run

# Variables
List of variables (like LENGTH) that will be replaced in any file section (searching for pattern $LENGTH).

Optionnaly, variable can describe multiple values to try
 - LENGTH=60 Single value
 - LENGTH=[60+1024] All values between 60 and 1024, included
 - LENGTH=\[64\*1024\] All values starting from 64 multiplied per 2 up to 1024
 - LENGTH={60,64,128,256,1024,1496} A list of values

Variables can optionnaly be prefixed with a tag and a colon to be included only
if a tag is given (by the repo, or the command line argument):
 - cpu:CPU={0,1} If the tag cpu is given, $CPU will be expanded by 0 and 1
 - -cpu:CPU=1    If the tag cpu is not given, $CPU will be expanded by 1

This allows to do more extanded tests to grid-search some value, but do not include that in regression test

TODO
----
- Plot results using gnuplot :
  - if no variable, just the result compared to last run in bars,
  - if 1 variable : multiple dual bars comparing for each value of variable the result with the previous run
  - if 2 variable : use variables as X/Y and make one line per run
  - if more : Like 2 variables, but make more lines for each variables 

WIP!!! Looking for collaborators !
