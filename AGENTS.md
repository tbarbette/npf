# NPF — Network Performance Framework

## Project overview

NPF runs reproducible networking/system experiments defined in `.npf` files, sweeps parameter spaces, and generates graphs, CSVs, Jupyter notebooks, and interactive websites from the results.

## Commands

```bash
pip install -e .                                  # install from source (requires deps)
npf local --test FILE.npf                         # run a test locally
npf local --test FILE.npf --no-graph --csv out.csv  # no graph, CSV output
npf --test FILE.npf [--cluster role=host ...]     # run on cluster, optionally comparing repos
npf-regress --test FILE.npf --regress             # regression through git history
npf-watch --test FILE.npf --mail-to addr          # watch repo, auto-run on new commits
```

> **`local` keyword**: Without a repo argument, NPF complains unless `default_repo=local` is in `%config`. Prefer passing `local` explicitly on the CLI: `npf local --test ...`

## Testing

```bash
# Unit tests (must run from project root, requires deps installed)
python3 -m unittest discover integration/unittests

# Integration tests
bash integration/integration.sh

# Via Docker (recommended — no local deps needed)
docker build --tag npf .
docker run --rm -w /npf npf python3 -m unittest discover integration/unittests
docker run --rm -w /npf npf bash integration/integration.sh

# Run an example .npf via Docker
docker run --rm -w /npf npf npf local --test examples/math.npf --no-graph
```

## Architecture

| Path | Purpose |
|---|---|
| `npf/tests/` | Core engine: `test.py` (execute + parse results), `regression.py`, `build.py` |
| `npf/sections/` | Parsers for each `.npf` section type |
| `npf/models/` | `dataset.py` (Run/Dataset), `variables/` (range/set/tag expansion), `units.py` |
| `npf/executor/` | Local, SSH, and enoslib execution backends |
| `npf/cluster/` | Node/NIC abstractions, cluster spec parsing |
| `npf/repo/` | Git repo interface for multi-version comparisons |
| `npf/output/` | Graphing (`grapher.py`), statistics, Jupyter notebook, web export |
| `npf/expdesign/` | Experimental designs: full, random, LHS, 2k, GP, ZLT, etc. |
| `npf/cmdline.py` | All CLI argument definitions |

## .npf file format

Sections begin with `%name`. Role suffix `@role` (e.g. `@server`, `@client`) targets a specific cluster node. Without a role suffix, scripts run locally.

### Sections

| Section | Purpose |
|---|---|
| `%info` | Human description |
| `%variables` | Parameter space definition |
| `%config` | Test configuration (n_runs, timeouts, graph options) |
| `%script[@role]` | Main test script (bash) |
| `%init[@role]` | Setup script (runs once before the sweep) |
| `%exit[@role]` | Cleanup script (runs once after all combinations) |
| `%file FILENAME` | Write a file before test execution |
| `%import[@role] MODULE` | Include a reusable module |
| `%late_variables` | Variables computed from results |
| `%pyexit` | Python post-processing (access `RESULTS` dict) |

### Roles

Each section can be scoped to a cluster role with `@role`:

```
%script@server
%script@client delay=2
%init@dut sudo=true
```

Without a role specifier the section runs on the **local** machine (where `npf-run` is invoked). For single-machine experiments, omit the role entirely.

### Section parameters

Space-separated after the section name:

| Parameter | Meaning |
|---|---|
| `sudo=true` | Run the script with `sudo` |
| `delay=N` | Wait N seconds before starting this script |
| `timeout=N` | Kill this script after N seconds |
| `autokill=false` | Do not kill this script when the section finishes |
| `critical=false` | Non-zero exit does not abort the whole test |
| `ifeq-VAR=val` | Only include this section when `VAR == val` |
| `name=<id>` | Give this script a name (for `waitfor=`) |
| `waitfor=<id>` | Block until the named script emits its first output |
| `jinja` | Enable Jinja2 template rendering in the script body |

Example: `%script@client delay=1 timeout=30 critical=true sudo=false waitfor=EVENT jinja ifeq-VAR=value`

### Variable syntax

```
VAR=[1-16]           # integer range
VAR=[1-16#2]         # range with step
VAR={a,b,c}          # explicit set
VAR={a:Label A,...}  # set with display names
tag:VAR=value        # set VAR only when tag is active
tag1,tag2:VAR=value  # set VAR only when BOTH tag1 and tag2 are active (logical AND)
tag:VAR={1,2,4,8}    # sweep VAR only when tag is active
-tag:VAR=value       # set VAR only when tag is NOT active
```

Variables will be substituted in scripts and files sections.

### Tags and conditional variables

Tags are free-form labels passed on the CLI with `--tags tag1,tag2` (or `--tag tag1`). They activate or suppress variable definitions and script sections. Multiple tags can be combined on a single variable or section definition using commas (e.g. `tag1,tag2:VAR=value`), which acts as a logical AND (both tags must be active).

**Use `tag:VAR=` instead of commenting out values.** When you want a variable to sweep a set of values only during focused testing — without changing the default — use a tag-gated definition rather than commenting:

```
// WRONG: commenting out the sweep forces the reader to uncomment manually
VAR=8
//VAR={1,2,4,8}

// RIGHT: tag gates the sweep; default stays 8, sweep activates with --tags sweep
VAR=8
sweep:VAR={1,2,4,8}
```

When the tag is active the tag-gated line **overrides** earlier assignments for the same variable. When the tag is absent, only `VAR=8` applies.

**Common patterns from `examples/iperf-advanced.npf`:**

```
PARALLEL=[1-8]            # always sweep 1..8
cpu:CPU=[1-8]             # CPU variable only exists when --tags cpu is passed
fastregression:PARALLEL={1,8}   # narrow the sweep for a quick CI run
fastregression:TIME=2           # fix TIME when running fast regression
nocongestion:CONGESTION=cubic   # skip CONGESTION sweep with --tags nocongestion
```

**Negated tags** (`-tag:`) apply when the tag is *not* given:

```
-nostat:results_expect+={TOTAL-cycles}   # expect cycles unless --tags nostat
```

**Scripts and imports can also be tag-gated** using the same prefix on the section header:

```
%-nostat:import@server perf-stat         # import perf-stat unless --tags nostat
```

In Jinja scripts you can test whether a tag-gated variable was defined at all:

```bash
{% if CPU is not defined %}
iperf ...
{% else %}
taskset -c 0-{{ CPU - 1 }} iperf ...
{% endif %}
```

> **`$((...))` is NPF math, not bash arithmetic**: NPF intercepts `$((...))` and evaluates it with a Python/asteval evaluator — it is **not** passed to bash. Use it for Python-style math on NPF variables: `$(( log($N) ))`, `$(( $N * 2 ))`. To run real bash arithmetic on shell variables, escape it: `\$((a+b))` — NPF strips the backslash and passes `$((a+b))` to bash unchanged. Alternatively use `expr $a + $b`.

> **Variable expansion gotcha**: NPF substitutes `$VAR` in script text before running it. Always use `$VAR` (not bare `VAR`) inside NPF `$((...))`: `$(( $N * 2 ))` works; `$(( N * 2 ))` does not (asteval sees `N` as undefined → 0).

Variables will be substitued in scripts and files sections.

> **`$((...))` is NPF math, not bash arithmetic**: NPF intercepts `$((...))` and evaluates it with a Python/asteval evaluator — it is **not** passed to bash. Use it for Python-style math on NPF variables: `$(( log($N) ))`, `$(( $N * 2 ))`. To run real bash arithmetic on shell variables, escape it: `\$((a+b))` — NPF strips the backslash and passes `$((a+b))` to bash unchanged. Alternatively use `expr $a + $b`.

> **Variable expansion gotcha**: NPF substitutes `$VAR` in script text before running it. Always use `$VAR` (not bare `VAR`) inside NPF `$((...))`: `$(( $N * 2 ))` works; `$(( N * 2 ))` does not (asteval sees `N` as undefined → 0).

**NPF substitutes `$VAR` (and `${VAR}`) in script bodies before the shell runs.**

```bash
# In %script, after NPF substitution (TRANSPORT=tcp):
if [ "$TRANSPORT" = "tls" ]; then   # becomes: if [ "tcp" = "tls" ]; then
```

Always use `$VAR` (not bare `VAR`) even inside bash arithmetic: `$(( $N * 2 ))`, not `$(( N * 2 ))`. Bare `N` inside `$((...))` is a bash variable, which is unset and equals 0.

To prevent NPF from substituting a literal `$` in a here-doc, escape it: `\$`.

### Built-in NPF variables

| Variable | Value |
|---|---|
| `$NPF_SCRIPT_PATH` | Directory containing the `.npf` file |
| `$NPF_TESTIE_PATH` | Deprecated alias for `$NPF_SCRIPT_PATH` |
| `$NPF_ARRAY_ID` | Run index within the current combination |
| `$NPF_ROLE` | Current role name |
| `$NPF_NODE_ID` | Current node index |

Use `EXPAND()` to resolve paths at variable-definition time:
```
MYPATH=EXPAND(${NPF_SCRIPT_PATH}/build)
```

### Result reporting (stdout protocol)

Scripts report results by printing to stdout:

```bash
echo "RESULT-THROUGHPUT 1000"         # plain number
echo "RESULT-THROUGHPUT 1000 Mbps"    # with unit
echo "RESULT-LATENCY 50 ms"           # time unit
```

Time-series point: `echo "time-10.5-RESULT-LATENCY 50 ms"`

Units supported: `K/M/G/T` multipliers; `b/bits/bytes`; `s/ms/us/ns`.

Multiple `RESULT` lines per script run are all captured. `RESULT <value>` (without a key) is the default single metric. Units can be scaled or named via `var_names` and `var_unit` in `%config`.

> **Zero results**: By default NPF treats a result of 0 as a failure. Add `accept_zero={METRICNAME}` (or `accept_zero=*`) to `%config` to allow zero values.

### Node attribute access in scripts

```bash
${server:0:ip}      # IP of first server node
${client:1:mac}     # MAC of second client node
$NPF_ROLE           # current role name
$NPF_NODE_ID        # current node index
```

## %config reference

```
%config
n_runs=3                         # repeat each combination N times (averaged)
timeout=120                      # seconds before a test run is killed
default_repo=local               # use 'local' for single-machine experiments
accept_zero={METRIC,...}         # allow zero results for these metrics
var_names={KEY:Label,...}        # human-readable names for variables and results
var_unit={KEY:unit,...}          # units shown in graphs and tables
var_log={VAR,...}                # plot this axis on log scale
var_divider={KEY:N,...}          # divide result by N before plotting
result_overwrite={METRIC,...}    # last value wins (default)
result_append={METRIC,...}       # collect all values across runs
graph_subplot_results={A:1,B:2}  # put A and B on separate subplots
```

## %init and %exit

- `%init` runs **once** before the variable sweep. It does not need to print `RESULT` lines. If it exits with a non-zero code, NPF aborts.
- `%exit` runs **once** after all test combinations finish (cleanup).
- Both support `sudo=true` and role specifiers.

## %file — embed configuration files

```
%file nginx.conf
server { listen $PORT; }
```

NPF writes the `%file` contents to disk (with variable substitution) before the scripts run. Files are placed in the test's working directory.

## %import — reusable modules

```
%import graph-beautiful      # graph styling
%import dev_irq_affinity     # pin IRQs to cores
%import perf-stat            # hardware perf counters
```

Modules live in `./modules/` or the installed NPF `modules/` directory. Pass parameters to override module variables:
```
%import wrk THREADS=16 CONNECTIONS=128
```

## Conditional sections (tags)

Tags are enabled on the command line with `--tags`:
```
npf-run --test mytest.npf --tags tls
```

In the .npf file, prefix a section or variable with `tag:` to make it conditional:
```
tls:%script
  echo "TLS-only script"
-tls:%script            # runs when tag 'tls' is NOT active
  echo "plain script"
```

## Key conventions

- **Results caching**: The default is to re-run all tests. Use `--cache` to skip combinations already in the result files. The flag is exactly `--cache` — not `--use-cache`, `--no-retest`, or `--force-cache`.
- **Parallelism**: Scripts across roles run in parallel within a test run; use `waitfor`/`sendto` (EventBus) to synchronize. If printing `EVENT xxx` in one script, scripts with `waitfor=xxx` will start.
- **`result_overwrite` vs `result_append`**: Default is overwrite (last value wins); use `result_append=METRIC` in `%config` to collect all values.
- **Jinja2**: Add `jinja` parameter to `%script` or `%file` to enable Jinja2 template rendering with all variables in scope. Jinja is the preferred way rather than python inlining with $(( some python code using VAR )). Using variable replacement like ${VAR} is fine for simple cases. When there is some logic, jinja2 is better. All variables and tags defined are available globally in jinja.

## Running experiments

```bash
# Local single-machine experiment
npf-run --test experiments/mytest.npf --no-build

# With cluster (roles mapped to SSH hosts)
npf-run --test mytest.npf \
  --cluster client=user@host1 server=user@host2

# Force re-run ignoring cached results
npf-run --test mytest.npf --force-test

# Override a variable on the command line
npf-run --test mytest.npf --variables RUNTIME=30

# Enable tags
npf-run --test mytest.npf --tags tls quic
```

## Common patterns

### ifeq — per-value scripts
```
%script ifeq-TRANSPORT=quic
  run_quic_target

%script ifeq-TRANSPORT=tcp
  run_tcp_target
```

### Multiple scripts in parallel (delay= for startup order)
```
%script@server
  start_server

%script@client delay=2
  run_client
```

### Shared background script (autokill=false keeps it alive)
```
%script name=monitor autokill=false sudo=true
  while true; do iostat -x 1; done

%script waitfor=monitor delay=1
  run_actual_test
```

### Parsing fio output
```bash
FIO_OUT=$(sudo fio --bs=$BS --rw=$RW --iodepth=$QD ... 2>&1)
echo "$FIO_OUT" | python3 -c "
import sys, re
text = sys.stdin.read()
# NPF has already substituted \$RW before the script runs
section = 'read' if '$RW' in ('randread','read') else 'write'
m = re.search(r'\s+' + section + r':.*?IOPS=([0-9.]+)([kKMG]?)', text)
if m:
    mult = {'k':1e3,'K':1e3,'M':1e6,'G':1e9}.get(m.group(2), 1.0)
    print('RESULT-IOPS', int(float(m.group(1)) * mult))
"
```

## Output files

After a run, NPF writes:
- `results/<testname>.csv` — all raw results
- `<testname>-<RESULT_KEY>.png` — auto-generated graphs
- A Jupyter notebook (with `--notebook`)
- A web page (with `--web`)

## Debugging

```bash
# Show the exact command NPF would run (dry run)
npf-run --test mytest.npf --show-cmd

# See full script output
npf-run --test mytest.npf --show-full

# Keep temp files for inspection
npf-run --test mytest.npf --preserve-temporaries
```

## Examples

All examples are in [`examples/`](examples/). Start with the simplest:

### 1. Local math — no network tools required ([`examples/math.npf`](examples/math.npf))

Sweeps N=1..50, computes log and 2^N on the local machine. Good template for any local benchmark.

```bash
npf local --test examples/math.npf --no-graph --csv out.csv
# or via Docker:
docker run --rm -w /npf npf npf local --test examples/math.npf --no-graph
```

Key patterns shown: `default_repo=local`, `accept_zero`, `var_unit`, math via `$((...))`.

### 2. Variable showcase ([`examples/doc-variable-example.npf`](examples/doc-variable-example.npf))

Demonstrates range, set, and labeled variable types and how they map to graph axes.

### 3. Two-machine iperf2 ([`examples/iperf.npf`](examples/iperf.npf))

Canonical cluster example: server/client roles, `%import graph-beautiful`, `default_repo=iperf2`.

```bash
npf local --test examples/iperf.npf \
    --cluster client=client.example.com server=server.example.com \
    --variables TIME=1
```

### 4. Advanced iperf2 with Jinja, CPU pinning, perf-stat ([`examples/iperf-advanced.npf`](examples/iperf-advanced.npf))

Shows: jinja templates, conditional blocks, `%init`, `cpu:` tag-gated variables, `perf-stat` import, and `fastregression` tag for quick CI runs.

### 5. Writing a new experiment from scratch

Minimal template for a local single-machine benchmark:

```
%info
My benchmark

%config
default_repo=local
n_runs=3

%variables
SIZE=[1-8]

%script jinja
# run your tool, capture its output
result=$(my_tool --size {{SIZE}} | grep "rate:" | awk '{print $2}')
echo "RESULT-RATE $result"
```

Run it:
```bash
npf local --test my_bench.npf --no-graph --csv results.csv
```

## Do's and Don'ts for AI agents

**Do:**
- Use `$NPF_SCRIPT_PATH` (with `EXPAND()` in `%variables`) to reference files relative to the .npf file, making the script portable.
- Use `RESULT-KEY value` lines — not print statements or log lines — for metrics.
- Print the raw tool output before the RESULT lines so humans can debug.
- Use `%init` for one-time setup (start servers, allocate resources) and `%exit` for cleanup.
- Keep `timeout` generous: SPDK/QEMU startup can take 5–30 s.
- **Always build and run your application via small local tests first** before wrapping it in an NPF script. NPF can hide application panics, syntax errors, and environment issues. Ensure the app works standalone before adding the NPF layer. When building Iris applications, run the binary locally or through `./build-in-docker.sh` and perform offline PCAP evaluation *before* embedding the execution pipeline in an NPF `.npf` file.
- Remember that when orchestrating Docker-based tools (like Iris's `./build-in-docker.sh`), any host paths expanded via `EXPAND(${NPF_SCRIPT_PATH}/...)` must be manually translated to the mapped paths inside the Docker container (e.g., `/build/...`) before passing them as command-line arguments in `%script`.

**Don't:**
- Do not put `RESULT` lines in `%init` or `%exit` — they are ignored there.
- Do not use NPF variable names (`$TRANSPORT`, `$QD`, etc.) as shell variable names inside a script — NPF will substitute them before the shell sees the script, causing confusing double-expansion.
- Do not rely on state from one `%script` run surviving to the next — each combination is run in its own subshell.
- Do not use `%teardown` — the correct section name is `%exit`.
- Do not hide output of programs, pipe to log file without revealing the output to the user. If need to re-parse a log to extract number for some RESULT, use "tee" to save the log but let it go to stdout still.

## Enoslib / Grid5000 usage

NPF can run experiments on reserved infrastructure via [enoslib](https://beyondtheclouds.github.io/enoslib/). The `npf.enoslib.run()` Python API replaces the CLI and accepts enoslib `Host` objects as roles.

```python
from npf import enoslib as npf

results, time_series = npf.run(
    "my_test.npf",
    series=[],                    # optional: list of repo strings like CLI
    argsv=["--force-retest"],     # extra CLI flags as a list
    roles={"client": host_a, "server": host_b},  # enoslib Host objects
)
```

`roles` values can be a single `Host` or a list of `Host` objects. The key is the NPF role name used in `%script@role`.

### Grid5000 two-machine example ([`examples/g5k_iperf.ipynb`](examples/g5k_iperf.ipynb))

See [`examples/iperf-g5k.npf`](examples/iperf-g5k.npf) for the matching test file.

```python
import enoslib as en
from npf import enoslib as npf

conf = (
    en.G5kConf.from_settings(job_name="npf-iperf", walltime="0:30:00",
                              job_type=["allow_classic_ssh"])
    .add_machine(roles=["server"], cluster="gros", nodes=1)
    .add_machine(roles=["client"], cluster="gros", nodes=1)
)
provider = en.G5k(conf)
roles, networks = provider.init()

# install iperf on both nodes — pass roles directly, NOT list(roles.values())
with en.actions(roles=roles) as a:
    a.apt(name="iperf", state="present", update_cache=True)

results, _ = npf.run("iperf-g5k.npf", ["local"],
                     argsv=["--no-graph"], roles=roles)
if results is None:
    raise RuntimeError("NPF run failed — check output above")
provider.destroy()
```

### Inter-node addressing

Use `${role:ip}` (not `${role:0:ip}`) in `.npf` scripts for enoslib-backed nodes.
`${role:0:ip}` accesses the NIC table which requires a `.node` config file or auto-discovery;
`${role:ip}` uses the node-level IP set directly from `eno_obj.address`.

### G5K SSH "Shared connection closed" error

If you see `EnosUnreachableHostsError: Failed to connect … Shared connection to X closed`, the
SSH ControlMaster socket created during `provider.init()` or the apt install cell has expired
(G5K's `~/.ssh/config` typically sets `ControlPersist 10` — a 10-second idle timeout).

NPF's `EnoslibExecutor` disables ControlMaster for its own ansible calls, so the connection
uses a fresh socket each time and won't be affected by an expired shared socket. If you still
see this error, check your `~/.ssh/config` and increase `ControlPersist` for G5K hosts, or run
the cells closer together to avoid the idle timeout.

## Documentation

Full documentation: https://npf.readthedocs.io/en/latest/
