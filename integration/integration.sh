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
    $python npf.py --force-test --no-graph-time --test $test --quiet --config n_runs=1 --tags fastregression ${@:3}
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

if [ $# -eq 1 ] ; then
    python=$1
else
    python=python
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
try integration/cdf.npf $python "--config n_runs=20"
try integration/heatmap.npf $python
try examples/iperf.npf $python "--variables TIME=1"
tryweb

bash doc/build_graphs.sh || ret=1

#compare_watcher $python

exit $ret
