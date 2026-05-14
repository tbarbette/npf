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
| `%init[@role]` | Setup script (runs before %script) |
| `%exit[@role]` | Cleanup script |
| `%file FILENAME` | Write a file before test execution |
| `%import[@role] MODULE` | Include a reusable module |
| `%late_variables` | Variables computed from results |
| `%pyexit` | Python post-processing (access `RESULTS` dict) |

### Variable syntax

```
VAR=[1-16]           # integer range
VAR=[1-16#2]         # range with step
VAR={a,b,c}          # explicit set
VAR={a:Label A,...}  # set with display names
tag:VAR=value        # conditional on tag
```

### Script parameters

`%script@client delay=1 timeout=30 critical=true sudo=false waitfor=EVENT jinja ifeq-VAR=value`

### Result reporting (stdout protocol)

Scripts report results by printing to stdout:

```bash
echo "RESULT-THROUGHPUT 1000"         # plain number
echo "RESULT-THROUGHPUT 1000 Mbps"    # with unit
echo "RESULT-LATENCY 50 ms"           # time unit
```

Time-series point: `echo "time-10.5-RESULT-LATENCY 50 ms"`

Units supported: `K/M/G/T` multipliers; `b/bits/bytes`; `s/ms/us/ns`.

> **Variable expansion gotcha**: NPF substitutes `$VAR` in script text before running it. Always use `$VAR` (not bare `VAR`) even inside bash arithmetic: `$(( $N * 2 ))`, not `$(( N * 2 ))`. Bare `N` inside `$((...))` is a bash variable, which is unset and equals 0.

> **Zero results**: By default NPF treats a result of 0 as a failure. Add `accept_zero={METRICNAME}` (or `accept_zero=*`) to `%config` to allow zero values.

### Node attribute access in scripts

```bash
${server:0:ip}      # IP of first server node
${client:1:mac}     # MAC of second client node
$NPF_ROLE           # current role name
$NPF_NODE_ID        # current node index
```

## Key conventions

- **Results caching**: NPF caches results per variable combination; re-running adds new points without re-running existing ones if using `--cache`.
- **Parallelism**: Scripts across roles run in parallel within a test run; use `waitfor`/`sendto` (EventBus) to synchronize. If printing `EVENT xxx` in one script, scripts with `waitfor=xxx` will start.
- **`result_overwrite` vs `result_append`**: Default is overwrite (last value wins); use `result_append=METRIC` in `%config` to collect all values.
- **Jinja2**: Add `jinja` parameter to `%script` or `%file` to enable Jinja2 template rendering with all variables in scope. Jinja is the preferred way rather than python inlining with $(( some python code using VAR )). Using variable replacement like ${VAR} is fine for simple cases. When there is some logic, jinja2 is better. All variables and tags defined are available globally in jinja.

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

## Documentation

Full documentation: https://npf.readthedocs.io/en/latest/
