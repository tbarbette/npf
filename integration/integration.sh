#!/bin/bash

#Function that launch a testie on click-2017 and compare the expected output
compare() {
    test=$1
    python=$2
    echo "Executing testie $test..."
    $python npf-run.py click-2017 --force-test --testie integration/$test.testie --quiet-build &> int_res
    if [ $? -ne 0 ] ; then
        echo "npf-run.py returned an error for test $test !"
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
    fi
}

#Function that launch watcher on a testie with click-2017 and compare the expected output
compare_watcher() {
    test=watcher
    python=$1
    echo "Executing watcher test..."
    $python npf-watch.py click-2017 --force-test --testie tests/click/ --onerun --history 2 --tags fast-regression &> int_res
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
    fi
}

#Function to launch a test and just check the output
try() {
    test=$1
    python=$2
    $python npf-run.py --force-test --testie $test --config n_runs=1 --tags fastregression
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

#try tests/tcp/01-iperf.testie $python
#compare integration-01 $python
#compare integration-02 $python
compare_watcher $python
