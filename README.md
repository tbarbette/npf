Click Performance Watcher
-------------------------

Run performance test on click using configuration files much like 
testies.

Configuration files allows matrix parameters to try many different parameters configuration.

perf.py
-------
This python scripts takes a test file, parse it, and run the given command for each combination of variables.

Example :
	PATH=$(pwd)/fastclick/master/bin:$PATH python perf.py tests/0050-fastudpgen.conf fastclick master-ref old-master-ref

run\_all.sh
-----------
Checkout or update a given repository, build click, and launch perf.py for all tests in the test folder. If the script was previously ran, it will pass the last branch HEAD to perf.py to make a comparison of last versions.

Example :
	./run_all.sh http://gitlab.run.montefiore.ulg.ac.be/sdn-pp/fastclick.git fastclick

TODO
----
- The comparison with the last performance test is not done yet
- Plot results using gnuplot :
  - if no variable, just the result compared to last run in bars,
  - if 1 variable : multiple dual bars comparing for each value of variable the result with the previous run
  - if 2 variable : use variables as X/Y and make one line per run
  - if more : Like 2 variables, but make more lines for each variables 

WIP!!! Looking for collaborators !
