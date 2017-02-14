#/bin/bash
compare() {
    test=$1
    python=$2
    $python regression.py click-2017 --force-test --testie integration/$test.testie &> int_res
    if [ $? -ne 0 ] ; then
        echo "regression.py returned an error for test $test !"
        cat int_res
        exit 1
    fi
    cmp int_res integration/$test.stdout
    if [ $? -eq 0 ] ; then
        echo "$test passed !"
    else
        echo "Error for $test : expected output does not match !"
        diff int_res integration/$test.stdout
    fi

}
if [ $# -eq 1 ] ; then
    python=$1
else
    python=python
fi
compare integration-01 $python
