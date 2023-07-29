Network Performance Framework [![CI](https://github.com/tbarbette/npf/actions/workflows/ci.yml/badge.svg)](https://github.com/tbarbette/npf/actions/workflows/ci.yml) [![CodeQL](https://github.com/tbarbette/npf/actions/workflows/codeql-analysis.yml/badge.svg)](https://github.com/tbarbette/npf/actions/workflows/codeql-analysis.yml)
=============================

Run performance tests on network and system software by running snippets of bash scripts on a cluster
following a simple definition file. For instance, the following configuration to test iPerf2 performance:
```bash
%info
IPerf 2 Throughput Experiment

%config
n_runs=5
var_names={PARALLEL:Number of parallel connections,WINDOW:Window size (kB),THROUGHPUT:Throughput}

%variables
PARALLEL=[1-8]
WINDOW={16,512}
TIME=2

%script@server
iperf -s

%script@client delay=1
//Launch the program, copy the output to a log
iperf -c ${server:0:ip} -w ${WINDOW}k -t $TIME -P $PARALLEL 2>&1 | tee iperf.log
//Parse the log to find the throughput
result=$(cat iperf.log | grep -ioE "[0-9.]+ [kmg]bits" | tail -n 1)
//Give the throughput to NPF through stdout
echo "RESULT-THROUGHPUT $result"
```

When launching NPF with:

```bash
npf-run --test tests/tcp/01-iperf.npf --cluster client=machine01.cluster.com server=machine02.cluster.com
```

NPF will automatically produce the following graph (configuration option allow to change the graph type, and many other options easily):

![sample picture](https://github.com/tbarbette/npf/raw/master/tests/tcp/iperf2-THROUGHPUT-wide.svg "Result for tests/tcp/01-iperf.npf")


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

### Where to continue from here?
Have you read the [writing tests documentation](https://npf.readthedocs.io/en/latest/tests.html)? Then, inspire yourself from the test script files in `tests/`, and write your own!

### How to distribute your test scripts, modules and repo files?
We welcome merge requests for generic stuffs! But you can keep your files in your "experimentation" folder. Indeed, NPF will always look for a file first in "./repo" for repo files, "./modules" for modules and "./cluster" for machines definition.
