#/bin/bash
set -eu
python3 regression.py fastclick --force-test --testie integration/integration-01.testie &> int_res
cmp int_res integration/integration-01.stdout
