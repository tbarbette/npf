#!/bin/bash


ret=0

#Function that launch a testie on click-2017 and compare the expected output
compare() {
    test=$1
    python=$2
    echo "Executing testie $test..."
    $python npf-run.py click-2017 --force-test --testie integration/$test.testie --quiet-build &> res$test
    if [ $? -ne 0 ] ; then
        echo "npf-run.py returned an error for test $test !"
        cat res$test
        exit 1
    fi
    cmp res$test integration/$test.stdout
    if [ $? -eq 0 ] ; then
        echo "$test passed !"
    else
        echo "Error for $test : expected output does not match !"
        echo "Command : $python npf-run.py click-2017 --force-test --testie integration/$test.testie --quiet-build"
        diff res$test integration/$test.stdout
        ret=1
    fi
}

#Function that launch watcher on a testie with click-2017 and compare the expected output
compare_watcher() {
    test=watcher
    python=$1
    echo "Executing watcher test..."
    $python npf-watch.py click-2017 --force-test --testie tests/click/pktgen/infinitesource-01.testie --onerun --history 2 --tags fast-regression &> int_res
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
        echo "Command : $python npf-run.py click-2017 --force-test --testie integration/$test.testie --quiet-build"
        diff int_res integration/$test.stdout
        ret=1
    fi
}

#Function to launch a test and just check the output
try() {
    test=$1
    python=$2
    params=$3
    $python npf-run.py --force-test --testie $test --config n_runs=1 --tags fastregression $3
    if [ $? -ne 0 ] ; then
        echo "npf-run.py returned an error for test $test !"
        exit 1
    fi
}

if [ $# -eq 1 ] ; then
    python=$1
else
    python=python
fi

compare pyexit $python
compare integration-01 $python
compare integration-02 $python
compare timeout $python
compare timeout-overwrite $python
compare event $python
compare math $python
try tests/tcp/01-iperf.testie $python "--variables TIME=1"
#compare_watcher $python

exit $ret
