#!/bin/bash


ret=0

compare_raw() {
    test=$2
    python=$3
    echo "Executing npf test $test..."
    $python $1 click-2022 --force-test --no-graph-time --test integration/$test.npf --quiet-build ${@:4} &> res$test
    if [ $? -ne 0 ] ; then
        echo "npf.py returned an error for test $test !"
        cat res$test
        #exit 1
    fi
    cmp res$test integration/$test.stdout
    if [ $? -eq 0 ] ; then
        echo "$test passed !"
    else
        echo "Error for $test : expected output does not match !"
        echo "Command : $python $1 click-2022 --force-test --no-graph-time --test integration/$test.npf --quiet-build ${@:4}"
        diff res$test integration/$test.stdout
        ret=1
    fi
}

#Function that launches a npf test on click-2022 and compare the expected output
compare() {
    compare_raw npf.py $@
}

#Function that launch watcher on a npf test with click-2022 and compare the expected output
compare_watcher() {
    test=watcher
    python=$1
    echo "Executing watcher test..."
    $python npf-watch.py click-2022 --no-graph-time --force-test --test tests/click/pktgen/infinitesource-01.npf --onerun --history 2 --tags fast-regression &> int_res
    if [ $? -ne 0 ] ; then
        echo "npf-watch.py returned an error for test $test !"
        cat int_res
        exit 1
    fi
    cmp int_res integration/$test.stdout
    if [ $? -eq 0 ] ; then
        echo "$test passed !"
    else
        echo "Error for $test : expected output does not match !"
        echo "Command : $python npf.py click-2022 --no-graph-time --force-test --test integration/$test.npf --quiet-build"
        diff int_res integration/$test.stdout
        ret=1
    fi
}

#Function to launch a test and just check the output
try() {
    test=$1
    python=$2
    echo "Trying $test with ${@:3}"
    kilall -9 click &> /dev/null
    $python npf.py --force-test --no-graph-time --test $test --quiet --config n_runs=1 --tags gen_nosudo fastregression ${@:3}
    if [ $? -ne 0 ] ; then
        echo "npf.py returned an error for test $test !"
        exit 1
    fi
}

#Function to test integration with npf-web-extension
tryweb() {
    FILE=results/index.html
    try examples/math.npf $python "--web $FILE"

    if [ -f "$FILE" ]; then
        echo "integration with npf-web-extension PASSED"
    else
        echo "error for npf-web-extension integration: no file generated through npf.py"
        exit 1
    fi
}
get_csv_value_by_column_name() {
  local csv_file="$1"
  local column_name="$2"

  # Read header and value line
  IFS=',' read -r -a headers < "$csv_file"
  IFS=',' read -r -a values < <(tail -n 1 "$csv_file")

  # Find index of the target column
  for i in "${!headers[@]}"; do
    if [[ "${headers[$i]}" == "$column_name" ]]; then
      echo "${values[$i]}"
      return 0
    fi
  done

  echo "Column '$column_name' not found." >&2
  return 1
}


csv_check() {
    val=$(get_csv_value_by_column_name "out.csv" $1)
    if (( $(echo "$val/$2 < 1.02 && $val/$2 > 0.98 " | bc -l) )); then
        return 0
    else
        echo "Value $val is not $2 for $1"
        ret=1
        return 1
    fi
}

check_stats() {
    local name=$1
    local args=$2
    local required=$3
    local forbidden=$4
    local outfile="resstatistics-$name"

    $python npf.py click-2022 --force-test --no-graph --test integration/statistics.npf --quiet-build $args &> $outfile

    local failed=0

    if [ -n "$required" ]; then
        IFS='|' read -ra REQ <<< "$required"
        for s in "${REQ[@]}"; do
            if ! grep -q "$s" "$outfile"; then
                echo "Error ($name): Expected '$s' not found!"
                failed=1
            fi
        done
    fi

    if [ -n "$forbidden" ]; then
        IFS='|' read -ra FORB <<< "$forbidden"
        for s in "${FORB[@]}"; do
            if grep -q "$s" "$outfile"; then
                echo "Error ($name): Forbidden '$s' found!"
                failed=1
            fi
        done
    fi

    if [ $failed -eq 1 ]; then
        cat "$outfile"
        ret=1
    else
        echo "statistics test ($name) passed !"
    fi
}

## Tests

if [ $# -eq 1 ] ; then
    python=$1
else
    python=python
fi


## Tests with DPDK
if pkg-config --exists libdpdk ; then

    #Play a trace, single thread
    try integration/fastclick-generator.npf $python --variables LIMIT=100 trace=../integration/tls.pcap-1 --csv out.csv
    csv_check y_COUNT 44

    #Play the same trace, 2 threads
    try integration/fastclick-generator.npf $python --variables LIMIT=100 trace=../integration/tls.pcap-1 GEN_THREADS=2 --csv out.csv
    csv_check y_COUNT 88


    #Play two traces, 2 threads (one trace per thread)
    try integration/fastclick-generator.npf $python --variables LIMIT=100 trace=../integration/tls.pcap-1 GEN_THREADS=2 --csv out.csv
    csv_check y_COUNT 88


    #Play the same trace, 2 threads but with pipeling, so using RR with gen_pipeline
    try integration/fastclick-generator.npf $python --tags gen_pipeline --variables LIMIT=100 trace=../integration/tls.pcap-1 GEN_THREADS=2 --csv out.csv
    csv_check y_COUNT 44

    #Now replay the trace, preloaded from memory, 10 times
    try integration/fastclick-generator.npf $python --tags replay --variables LIMIT=100 trace=../integration/tls.pcap-1 PKTGEN_REPLAY_COUNT=10 --csv out.csv
    csv_check y_COUNT 440
    csv_check y_BYTES 186370

    #Now replay 2 traces, preloaded from memory, 10 times, using 2 threads
    try integration/fastclick-generator.npf $python --tags replay scale_multi_trace --variables LIMIT=100 trace=../integration/tls.pcap GEN_MULTI_TRACE=2 PKTGEN_REPLAY_COUNT=10 GEN_THREADS=2 --csv out.csv
    csv_check y_COUNT 880

    try integration/fastclick-generator.npf $python --tags udpgen replay --variables LIMIT=10000 PKTGEN_REPLAY_COUNT=10 LIMIT_TIME=10 --csv out.csv

    #We have to IGNORE=2 as the token bucket starts full, so the rate is slightly higher at the beginning, still there is a small increase in PPS left
    try integration/fastclick-generator.npf $python --tags udpgen rate --variables LIMIT=50 GEN_RATE=10000 GEN_LENGTH=1000 GEN_RATE_LINK=0 GEN_BURST=1 IGNORE=2 --csv out.csv
    csv_check y_PPS 10.5

    try integration/fastclick-generator.npf $python --tags udpgen prate --variables LIMIT=1000 GEN_RATE=500  --csv out.csv
    csv_check y_COUNT 1000
    csv_check y_PPS 500
    try integration/fastclick-generator.npf $python --tags udpgen --variables LIMIT=1000  --csv out.csv
    csv_check y_COUNT 1000
fi

try integration/empty.npf $python
compare_raw npf.py single $python --no-graph --no-graph-time --csv out.csv
diff out.csv integration/single.csv
if [ $? -ne 0 ] ; then
    echo "single.csv changed !"
    ret=1
fi
compare negative $python
compare experimental $python
compare pyexit $python
compare integration-01 $python
compare integration-02 $python
compare timeout $python
compare timeout-overwrite $python
compare event $python
compare math $python
compare jinja $python
compare globsync $python
compare zlt $python --exp-design "zlt(RATE,THROUGHPUT)"

# Test statistics option
echo "Testing statistics options..."


# Test 1: without --statistics, there should be no "Statistics for" or "Building dataset" output
check_stats "none" "" "" "Building dataset"

# Test 2: with --statistics (no arguments), should get statistics for all 3 metrics
check_stats "all" "--statistics" "Building dataset|Statistics for EXP|Statistics for LOG|Statistics for N" ""

# Test 3: with --statistics EXP, should get statistics only for EXP
check_stats "exp" "--statistics EXP" "Building dataset|Statistics for EXP" "Statistics for LOG|Statistics for N"

try integration/cdf.npf $python "--config n_runs=20"
try integration/heatmap.npf $python
try examples/iperf.npf $python "--variables TIME=1"
tryweb

bash doc/build_graphs.sh || ret=1

#compare_watcher $python

exit $ret
