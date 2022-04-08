Network Performance Framework [![CI](https://github.com/tbarbette/npf/actions/workflows/ci.yml/badge.svg)](https://github.com/tbarbette/npf/actions/workflows/ci.yml) [![CodeQL](https://github.com/tbarbette/npf/actions/workflows/codeql-analysis.yml/badge.svg)](https://github.com/tbarbette/npf/actions/workflows/codeql-analysis.yml)
=============================

Run performance tests on network software by running snippets of bash scripts on a cluster
following a simple definition file. For instance, the following configuration to test iPerf3 performance (omitting graph styling options):
```
%info
IPerf3 Throughput Experiment

%variables
PARALLEL=[1-8]
ZEROCOPY={:without,-Z:with}

%script@server
iperf3 -s &> /dev/null

%script@client delay=1
result=$(iperf3 -f k -t 2 -P $PARALLEL $ZEROCOPY -c ${server:0:ip} | tail -n 3 | grep -ioE "[0-9.]+ [kmg]bits")
echo "RESULT-THROUGHPUT $result"
```
Will automatically produce the following graph:

![sample picture](https://github.com/tbarbette/npf/raw/master/tests/tcp/01-iperf-THROUGHPUT.png "Result for tests/tcp/01-iperf.npf")

When launching npf:

```bash
npf-run --test tests/tcp/01-iperf.npf
```

Test files allow to define a matrix of parameters to try many combinations of
variables (see [here](https://npf.readthedocs.io/en/latest/variables.html) for a description of the possible definitions such as values, ranges, ...) for each test and report performance results and evolution for each combination of variables.

Finally, a graph will be built and statistical results may be computed for each test 
showing the difference between variables values, different softwares, or the evolution of
performances through commits.

Test files are simple to write, and easy to share, as such we encourage
users to share their ".npf" scripts with their code to allow other users to reproduce
their results, and graphs.

NPF supports running the given test across a custer, allowing to try your tests
in multiple different configuration very quickly and on serious hardware.

### Documentation ###
The documentation is available on [read the docs](https://npf.readthedocs.io/en/latest/)!

### Quick Installation
NPF is built using Python 3, and is published on pypi, so it can be installed
with pip using:

```bash
pip3 install --user npf
```

At run-time, NPF uses SSH and can benefit from usage of sudo and NFS, see the [run-time dependencies](https://npf.readthedocs.io/en/latest/usage.html#run-time-dependencies) in the documentation for more information.

### Big picture ###
Your *.npf* test file is composed of a serie of sections, as in the example given above. The sections describe the scripts to run, where to run them, what variables should be tested, what are their ranges, configuration parameters such as timeout or graph colors, etc. Each section is described in more details in [the "writing test script" documentation](https://npf.readthedocs.io/en/latest/tests.html).
When launching NPF, you will also give the name of one or more *repositories*, which are files located in the `repo` folder describing software to download, install and compile so everything is in place when your experiment is launched. They follow a format descrived in [repo/README.md](repo/README.md). It can also be ignored using the `local` fake repository.
Your test script will also define a few script *roles*, such as `client` or `server` as in the example above. When you actually launch your experiment, you must tell which machine (physical or virtual) will take the role. For simple cases, passing the address of a machine with the `--cluster role=machine` will be enough. When you'd like to define parameters such as IPs and MAC addresses, you can define a *cluster* file that will describe details about each machines. See the [cluster documentation](https://npf.readthedocs.io/en/latest/cluster.html) for more details.

## Tools
Three tools come with NPF :
  * npf-run for advance regression and statistics tests on one repository
of change in performances due to the last commits
  * npf-compare to compare one test script but across multiple repository, mainly to compare
how different branches/implementations behaves against each others
  * npf-watch is a CI-like program to watch one or multiple repositories for any new commit and e-mail in case of regression in performance measures

### NPF Run
NPF-Run is the main NPF tool.

It checkouts or updates a given repository (described in the repo
folder), build the software, and launch the given test scripts

Example :
```bash
    npf-run click --test tests/click/ #Produce a graph for each click-based tests with the result
```

#### Regression
NPF-Run is able to check commit history, do regression test, and graph the performance history
for all test script using the --regress flag.

```bash
    #click master is updated
    npf-run click --test tests/click/ --regress #The graph now compares HEAD and the last commit, if major performances changes are found, the return code will be different than 0
    #click master is updated again
    npf-run click --test tests/click/ --regress #The graph includes the older commit for reference, up to "--graph-num", default is 8
```

Example of a generated graph for the Click Modular Router, just when IPFilter compilation process was re-worked :
![alt tag](doc/sample_graph2.png)

Alternatively, you can force npf-run to re-build and compute the data for the old runs directly with the --allow-old-build option :
```bash
    npf-run click --test tests/click/ --allow-old-build [--graph-num=8] #Graph the performance of the current version and the last 8 previous ones
```

#### Statistics
NPF-Run can produce statistics about the results such as the best set of variable, the average per-variable,
a regression tree and the importance of each features.

```bash
    npf-run click --test tests/click/ --statistics
```

See *npf-run --help* for more options

### NPF Watcher

Watcher is a stripped down version of npf-run (without statistics support mostly), but allowing to
loop through a given list of repositories watching for changes. When
a new commit is seen, it will run all given test scripts and e-mail the results
to a given list of addresses.

```bash
npf-watch click fastclick --mail-to barbette@kth.se --tags fastregression --history 1
```
The arguments are :
 * click fastclick : List of repos to watch, as described in the repos folder
 * --history N allows to re-do the tests for the last N commits, you will receive
 an e-mail for each commits of each repos.
 * --tags TAG1 TAG2 [...] allows to set flags which change variables in the tests, see below.

See *npf-watch --help* for more options

### NPF Compare

NPF-Compare allows to do the contrary of npf-run : instead of
 testing multiple npf scripts on one repository, it tests one test script across
 multiple repositories.
 
This example allows to compare Click against [FastClick](https://github.com/tbarbette/fastclick/) (a faster version of the Click Modular Router) for the infinitesource
  test case :

```bash
npf-compare click fastclick --test tests/pktgen/infinitesource-01.npf --variables LENGTH=64
```
 * click fastclick : List of repos to compare
 * --test FILENAME : Test script to test. This argument is available in all tools.
 * --variables  VAR=VAL [...] : Fix the value of one variable.
 By default in this test script, the test is redone with packet length 64,256 and 1024. This
 allows to have one less "dynamic" variables so the grapher can
 use a lineplot instead of a barplot (see below).
 
Result :
![alt tag](doc/sample_compare.png)
Just for relevance, batching is what makes this difference.

This tool has also less options than NPF-Run. You should use NPF-Run
to create your tests and tune parameters for each repository independently.
And then only use npf-compare when ready. Compare does not support statistics or regression tests.

See *npf-compare --help* for more options

### Which one to use
Use npf-run for development, trying big matrices of configuration,
get extended graph and customized tests for each test scripts.

Use npf-watch with the fastregression tags to send you an e-mail automatically
when some new commits introduce performances problems.

Use npf-compare to compare multiple repositories, multiples branches or multiple
different softwares. The test scripts included in this repository support comparing throughput of Click and FastClick in diverse
configurations, or NetPerf and Iperf as packet generators.

### Main common arguments
All tools feature those common arguments :

 * --variables VAR=VAL [VAR2=VAL2 ...] allows to overwrite some test script variables configuration, mainly to reduce the set of parameters
 * --config VAR=VAL [VAR2=VAL2 ...] allows to overwrite some configuration options such as n_runs used to define the number of time a test should be launched for each variable combination
 * --test path : Path to a folder or a test script. By default "tests" is used.


## Dataset
All results of tests are saved per-commit and per-repo to avoid re-computing the next time
you launch either of the tools. However the set of variables must be exactly the
same.

To force re-computing the tests, use the --force-retest option. The --force-rebuild
may also be something you want.

### Output

You can customize the output of NFP by passing different arguments. Below, you can find some of the common outputs:

* **--pandas [PATH]** NFP produces a single Pandas dataframe if you use this argument. Later, you can load the dataframe for post-processing. The following code shows one example for a sample dataframe (i.e., `test-pandas.csv`) with two variables (i.e., `X` and `Y`). Line `3` produces the median of multiple runs, while line `4` shows values of all runs in a list, which can be used for a boxplot.

```python
1 import pandas as pd
2 df = pd.read_csv("test-pandas.csv")
3 df[['X','Y']].groupby('X').agg({'Y' : ['median']})
4 df[['X','Y']].groupby('X').agg({'Y' : lambda x : list(x)})
```

 * **--output** Outputs a standard CSV for each output variable. According to **--output-columns**, by default the X variable(s) and the average of Y value. For instance *--output-columns x perc1 perc25 median perc75 perc99 avg* would have 7 columns with the X value, then the 1st percentile of the results for the variable, etc.
   For instance, if you have a variable PARALLEL=[1-8] and you collect THROUGHPUT, for which you did 3 runs, by default you'll get a csv file for THROUGHPUT, that gives you :
   ```csv
   1 2.2
   2 3.4
   3 4.2
   ...
   ```
   Where the second column is the average of the 3 runs. Instead, with the columns "x all", you would get:
   ```csv
   1 2.0 2.2 2.4
   2 3.1 3.4 3.7
   3 4.0 4.2 4.4
   ...
   ```

## Tags
All programs have the --tags argument, allowing to give a set of tags
that trigger changes in the test scripts. The dpdk flags tells that a DPDK
environment is setted up with at least two NICs, allowing DPDK-based
tests to run. The fastregression tag allows to only try important
variable combination and not search for performance points, while full
is the contrary and will run a very big set of variables combinations
to get statistics out of results.

## Writing test scripts
See [the writing tests documentation](https://npf.readthedocs.io/en/latest/tests.html) to read more about test scripts and learn about creating new ones. Scripts describe the tests and parameters to re-run them in multiple configuration. Test scripts are the heart of NPF.

## Repository files
See [repo/README.md](repo/README.md) to lear how to build repository definition files to let NPF know how to fetch and compile some software

## Cluster
Test scripts define multiple roles such as "client" or "server". Each role can be mapped
 to a given node to run a test across a cluster using the *--cluster ROLE=NODE [ROLE2=NODE2]* argument.

NPF will run the test scripts for each role on the mapped cluster. Giving the node address in the
 command line may be enough. However some tests require more information about each node
 that can be set using cluster files. More information about writing cluster files is given on [the cluster documentation](https://npf.readthedocs.io/en/latest/cluster.html)

### Graph
Graph are automatically generated for all tested variables combinations. See [the graphing documentation](https://npf.readthedocs.io/en/latest/graph.html) to manipulate graphs in numerous ways.

### Where to continue from here?
Have you read the [writing tests documentation](https://npf.readthedocs.io/en/latest/tests.html)? Then, inspire yourself from the test script files in `tests/`, and write your own!

### How to distribute your test scripts, modules and repo files?
We welcome merge requests for generic stuffs! But you can keep your files in your "experimentation" folder. Indeed, NPF will always look for a file first in "./repo" for repo files, "./modules" for modules and "./cluster" for machines definition.
