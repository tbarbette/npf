The testie file is made of multiple sections, starting with a % like
 "%file CONFIG" which means that a file named CONFIG should be
  created.

List of sections :
 * info : Information about what the testie does. Usually the first line is the title and will be by default used as the graph title
 * config : Configuration options. See below.
 * variables : List of variables to define the matrix of parameters to try
 * script : Bash commands to execute, the heart of the test. Can be defined to run with a specific role, role are mapped to cluster nodes. See the cluster section below
 * init : Special script that run only once, before all other scripts (therefore, can be fought as an initialization script)
 * import : Import another testie and optionally under a given role. The repository comes with some "modules" testies intended for importation. They usually do specific tasks that we don't want to rewrite in all testie such as setting the cpu frequency, IP addresses for some NICs, ...
 * require : A special script that tells if the testie can run. If any line produce a return code different than 0, the testie will not run
 * pyexit : A python script that will be executed after each tests, mainly to change or interpret the results

### Config
List of test configuration option
 - acceptable=0.01         Acceptable difference between multiple regression runs
 - n\_runs=1               Number of runs to do of each test
 - unacceptable\_n\_runs=0 Number of runs to do when the value is first rejected (to avoid false positives). Half the most abnormal runs will be rejected to have a most common value average.
 - required\_tags=         Comma-separated list of tags needed to run this run

### Variables
List of variables (like LENGTH) that will be replaced in any file section (searching for pattern $LENGTH).

Optionnaly, variable can describe multiple values to try
 - LENGTH=60 Single value
 - LENGTH=[60+1024] All values between 60 and 1024, included
 - LENGTH=\[64\*1024\] All values starting from 64 multiplied per 2 up to 1024
 - LENGTH={60,64,128,256,1024,1496} A list of values

Variables can optionaly be prefixed with a tag and a colon to be included only
if a tag is given (by the repo, or the command line argument):
 - cpu:CPU={0,1} If the tag cpu is given, $CPU will be expanded by 0 and 1
 - -cpu:CPU=1    If the tag cpu is not given, $CPU will be expanded by 1

This allows to do more extanded tests to grid-search some value, but do not include that in regression test

### pyexit
NPF will extract all results prefixed by *RESULT[-VARNAME]*. If VARNAME is in result_add={...} config list, occurences of the same VARNAME will be added together, if it is in the result_append config_list, results will be append as a list, else the VARNAME will overwrite each others.

To do more, one can use the %pyexit section to interpret the results :
```%pyexit
import numpy as np
loss=RESULTS["RX"] - RESULTS["TX"]
RESULTS["LOSS"]=loss
```
Any python code will be accepted, so one may compute variance among multiple results, etc. Kind results are available under KIND_RESULTS.



## Testies shipped with NPF

### Generic ###
Generic tests are used to do black-box testing, they are L2/L3 generators,
packets trace replay and HTTP generators.

They are generic in the sense that you could use them out of the box to test
any device under test in the middle of a client and a server.

 * generic_dpdk : DPDK-based tests, need a DPDK environment setted up
 * generic : Other tests using the normal OS stack
