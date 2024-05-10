#!/bin/bash

set -e

python3 ./npf-run.py --test integration/filter.npf --graph-size 4 2.5 --graph-filename doc/filter.png
python3 ./npf-run.py 'local:Default' --test doc/example_multiple_result.npf --graph-size 3 2.5 --graph-filename doc/example_multiple_result_default.png --force-retest
python3 ./npf-run.py 'local:Add' --test doc/example_multiple_result.npf --graph-size 3 2.5 --graph-filename doc/example_multiple_result_add.png --config 'result_add={THROUGHPUT}' --force-retest
python3 ./npf-run.py 'local:Append' --test doc/example_multiple_result.npf --graph-size 3 2.5 --graph-filename doc/example_multiple_result_append.png --config 'result_append={THROUGHPUT}' --force-retest
python3 ./npf-run.py local:Namespace --test doc/example_namespaces.npf --graph-size 4 2.5 --graph-filename doc/example_namespaces.svg
python3 ./npf-run.py 'local:Namespace (synced)' --test doc/example_namespaces.npf --graph-size 4 2.5 --graph-filename doc/example_namespaces_synced.svg --config 'var_sync={TIME}'