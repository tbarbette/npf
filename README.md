Click Performance Watcher
=========================

Run performance test on the Click Modular Router or its variants using
configuration files much like Click's testies.

Configuration files allows matrix parameters to try many combinations of
variables for each test files and report performance results for each
parameters.

Finally, a graph will be made for each test showing the evolution of
performances through commits.

###Dependencies
This project needs python 3
sudo pip3 install -r requirements.txt

##Tools
Two main tools come with this performance framework, regression.py for
advance regression tests on one repository, and watcher.py to watch one
or multiple repositories for any new commit and e-mail output in case
of change in performances due to the last commits.

###regression.py

Checkout or update a given repository (described in the repo
folder), build Click, and launch the tests discribed in the
tests directory. If the script was previously ran on older
commits, it will make a comparison with last commits, showing
 a regression (or improvement) and will graph 8 old data.

Example :
```bash
    python3 regression.py click #Produce a graph for each tests with the result
    #click master is updated
    python3 regression.py click #The graph now compares HEAD and the last commit, if major performances changes are found, the return code will be different than 0
    #click master is updated again
    python3 regression.py click #The graph includes the older commit for reference, up to "--graph-num", default is 8
```

Alternatively, you can force regression.py to re-build and compute the data for the old runs directly with the --allow-old-build option :
    python3 regression.py click --allow-old-build

Use --help to print all options

###watcher.py

Watcher is a stripped down version of regression.py, but allowing to
loop through a given list of repositories watching for changes. When
a new commit is seen, it will run all testies and e-mail the results
to a given list of addresses.

###Common options
here are the main common options of the tools

####--tags
Both program have the --tags argument, allowing to give a set of tags
that trigger changes in the testies. The dpdk flags tells that a DPDK
environment is setted up with at least two NICs, allowing DPDK-based
tests to run. The fastregression tag allows to only try important
variable combination and not search for performance points, while full
is the contrary and will run a very big set of variables combinations
to get statistics out of results.

###Which one to use
Use regression.py for development, trying big matrices of configuration,
get extended graph and customized tests for each testies.

Use watcher.py with the fastregression tags to send you an e-mail automatically
when some new commits introduce performances problems.

##Writing configuration files

The file is made of multiple sections, starting with a % like "%file CONFIG" which means that a file named CONFIG should be created.


### Config
List of test configuration option
 - acceptable=0.01         Acceptable difference between multiple regression runs
 - n\_runs=1               Number of runs to do of each test
 - unacceptable\_n\_runs=0 Number of runs to do when the value is first rejected (to avoid false positives). Half the most abnormal runs will be rejected to have a most common value average.
 - required\_tags=         Comma-separated list of tags needed to run this run

### Variables
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

### Graph
Graph are automatically generated with all matrix variables expanded and comparing current results vs old results

![alt tag](doc/sample_graph2.png)

![alt tag](doc/sample_graph.png)

If a "previous uuid" is not given to regression.py (so it just run the test for the current master but do not compare the results), the graph will use one variable as the serie :

![alt tag](doc/sample_graph3.png)

TODO
----
WIP!!! Looking for collaborators !
