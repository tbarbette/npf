Network Performance Framework
=============================

Run performance tests on the Click Modular Router or its variants using
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
Three tools come with this performance framework :
  * regression.py for advance regression tests on one repository
  * watcher.py to watch one or multiple repositories for any new commit and e-mail output in case
of change in performances due to the last commits
  * compare.py to compare one testie but accross multiple repository, mainly to compare
how different branches/implementations behaves against each others

###NPF Regressor

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

Example of a generated graph, just when IPFilter compilation process was re-worked :
![alt tag](doc/sample_graph2.png)

Alternatively, you can force regression.py to re-build and compute the data for the old runs directly with the --allow-old-build option :
    python3 regression.py click --allow-old-build

Use --help to print all options

###NPF Watcher

Watcher is a stripped down version of regression.py, but allowing to
loop through a given list of repositories watching for changes. When
a new commit is seen, it will run all testies and e-mail the results
to a given list of addresses.

```bash
python3 watcher.py click fastclick --mail-to tom.barbette@ulg.ac.be --tags fastregression --history 1
```
 * click fastclick : List of repos to watch, as described in the repos folder
 * --history N allows to re-do the tests for the last N commits, you will receive
 an e-mail for each commits of each repos. This arguments is also available in regression.py
 * --tags TAG1 TAG2 [...] allows to set flags which change variables in the tests, see below.

###NPF Comparator

Compare allows to do the contrary of regression.py : instead of
 testing multiple testies on one repository, you test one testie across
 multiple repositories.
 
This example allows to compare click against fastclick for the infinitesource
  test case :

```bash
python3 compare.py click fastclick --testie tests/pktgen/infinitesource-01.testie --variables LENGTH=64
```
 * click fastclick : List of repos to compare
 * --testie FILENAME : Testie to test. This argument is available in all tools.
 * --variables  VAR=VAL [...] : Fix the value of one variable.
 By default in this testie, the test is redone with packet length 64,256 and 1024. This
 allows to have one less "dynamic" variables so the grapher can
 use a lineplot instead of a barplot (see below).
 
Result :
![alt tag](doc/sample_compare.png)
Just for relevance, batching is what makes this difference.

This tool has also less options than Regressor, you should use this
last one to create your tests and tune parameters on one repository
and then only use compare.py. Comparator has no options for statistics.


###Which one to use
Use regression.py for development, trying big matrices of configuration,
get extended graph and customized tests for each testies.

Use watcher.py with the fastregression tags to send you an e-mail automatically
when some new commits introduce performances problems.

Use compare.py to compare multiple Click
instances, typically in research paper or to asser that an
idea of you is good, showing the generated graphs to assert
your sayings.


## Dataset

All results of tests are saved per-commit and per-repo to avoid re-computing the next time
you launch either of the tools. However the set of variables must be exactly the
same.

To force re-computing the tests, use the --force-test option. The --force-rebuild
may also be something you want.


## Tags
All programs have the --tags argument, allowing to give a set of tags
that trigger changes in the testies. The dpdk flags tells that a DPDK
environment is setted up with at least two NICs, allowing DPDK-based
tests to run. The fastregression tag allows to only try important
variable combination and not search for performance points, while full
is the contrary and will run a very big set of variables combinations
to get statistics out of results.

##Writing configuration files

The file is made of multiple sections, starting with a % like
 "%file CONFIG" which means that a file named CONFIG should be
  created.


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

### Repository
All repositories are defined in the repo folder. A repo configuration define how
to fetch and install a specific program, using one of the following ways :

  * **git** : Use git to download and compile a branch or specific commit
  * **get** : Download a file and compile/install it if needed
  * **package** : Use the OS package manager (only Red-Hat and Debian based supported for now)

The git methode supports the "history" parameter, allowing to go back
in commit history to rebuild the history with older versions (commits).
get and package have a hardcoded version in the repo file.

The default method is git.

When giving a repo name to any tool, the version can be overriden by
suffixing a "-version" to the repo name, eg :
```bash
python3 regression.py iperf-3.1.3
```

See the repo folder for examples. Repo can inherit others, as there is only one
configure/make line per repo, you can inherit a repo with a specific
configuration and avoid repeating all other parameters. See click/fastclick/fastclick-nobatch.


### Graph
Graph are automatically generated for all tested variables
combinations.

To choose the type of graph, the number of dynamic variables is taken into account.

Below, regression.py gave two series to the Grapher (current and last commit), while the testie
generate a matrix of Burst and Lengths, that is 2 dynamic variables and only a barplot can render that correctly
as lines would be uncomparable.

![alt tag](doc/sample_graph.png)

If a "previous version" is not given to regression.py (so it just runs the test for the current master but do not compare 
the results), the graph will use one variable as the serie as having only one
line would be a loss of space, leaving only one dybamic variable :
![alt tag](doc/sample_graph3.png)

The Comparator uses the repositories as series.

TODO
----
WIP!!! Looking for collaborators !
