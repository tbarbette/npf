import os

import numpy as np
import pydotplus as pydotplus
import sys
if sys.version_info < (3, 7):
    from orderedset import OrderedSet
else:
    from ordered_set import OrderedSet

from sklearn import tree
from collections import OrderedDict

from typing import List

from npf.build import Build
from npf.test import Test
from npf.types.dataset import Dataset
from npf import npf

class Statistics:
    @staticmethod
    def run(build: Build, all_results: Dataset, test: Test, max_depth=3, filename=None, doviz=True):
        print("Building dataset...")

        #Transform the dataset into a standard table of X/Features and Y observations
        dataset = Statistics.buildDataset(all_results, test)

        #There's one per serie, so for each of those
        for result_type, X, y, dtype in dataset:
            if len(dataset) > 1:
                print("Statistics for %s" % result_type)
            print("Learning dataset built with %d samples and %d features..." % (X.shape[0], X.shape[1]))
            clf = tree.DecisionTreeRegressor(max_depth=max_depth)
            try:
                clf = clf.fit(X, y)
            except Exception as e:
                print("Error while trying to fit the clf:")
                print(e)
                continue

            if doviz:
                if (max_depth is None and len(X) > 16) or (max_depth is not None and max_depth > 8):
                    print("No tree graph when maxdepth is > 8. Use --statistics-maxdepth 8 to fix it to 8.")
                else:
                    dot_data = tree.export_graphviz(clf, out_file=None, filled=True, rounded=True, special_characters=True,
                                                    feature_names=dtype['names'])
                    graph = pydotplus.graph_from_dot_data(dot_data)


                    f = npf.build_filename(test, build, filename if not filename is True else None, {}, 'pdf', result_type, show_serie=False, suffix="clf")
                    try:
                        graph.write(f, format=os.path.splitext(f)[1][1:])
                        print("Decision tree visualization written to %s" % f)
                    except Exception as e:
                        print("Could not generate the tree vizualization : %s" % str(e))

            vars_values = OrderedDict()

            print("")
            for i, column in enumerate(X.T):
                varname = dtype['names'][i]
                vars_values[varname] = set([v for v in np.unique(column)])

            print("")
            print("Feature importance:")
            # noinspection PyUnresolvedReferences
            l = list(zip(dtype['names'], clf.feature_importances_))
            l.sort(key=lambda x: x[1])
            for key, f in l:
                if len(vars_values[key]) > 1:
                    print("  %s : %0.4f" % (key, f))

            print('')
            def printline(n):
                best = X[n]
                vs=[]
                for i, name in enumerate(dtype['names']):
                    vs.append("%s = %s" % (name, best[i] if (dtype['values'][i] is None) else best[i] if type(best[i]) is np.str_ else dtype['values'][i][int(best[i])]))
                print("  " + ", ".join(vs), end='')
                print(' : %.02f' % y[n])

            print("Max:")
            printline(y.argmax())

            print("Min:")
            printline(y.argmin())


            print('')
            print("Means per variables:")
            for i, (k, vals) in enumerate(vars_values.items()):
                if len(vals) == 1:
                    continue
                print("%s:" % k)
                for v in sorted(vals):
                    vs = v if (dtype['values'][i] is None) else dtype['values'][i][int(v)]
                    tot = 0
                    n = 0
                    for ic in range(X.shape[0]):
                        if X[ic,i] == v:
                            tot += y[ic]
                            n += 1
                    if n == 0:
                        print("  %s : None" % vs)
                    else:
                        print("  %s : %.02f " % (vs, tot / n))
                print("")

    @classmethod
    def buildDataset(cls, all_results: Dataset, test: Test) -> List[tuple]:
        #map of every <variable name, format>
        dtype = test.variables.dtype()

        y = OrderedDict()
        dataset = []
        for i, (run, results_types) in enumerate(all_results.items()):
            vars = list(run.variables[k] for k in dtype['names'])
            if not results_types is None and len(results_types) > 0:

                dataset.append([v for v in vars])
                for result_type, results in results_types.items():
                    r = np.mean(results)
                    y.setdefault(result_type, []).append(r)
        dtype['values'] = [None] * len(dtype['formats'])

        for i, f in enumerate(dtype['formats']):
            if f is str:
                dtype['formats'][i] = int
                values = OrderedSet()
                for row in dataset:
                    values.add(row[i])
                    row[i] = values.index(row[i])
                dtype['values'][i] = list(values)
        X = np.array(dataset, ndmin=2)

        lset = []
        for result_type, v in y.items():
            lset.append((result_type, X, np.array(v),dtype))
        return lset
