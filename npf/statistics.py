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

            print('')

            ys = np.ndarray(shape = (len(X), len(dataset)))

            for i,d in enumerate(dataset):
                ys[:,i] = d[2]
            import pandas as pd
            df = pd.DataFrame(np.concatenate((X,ys),axis=1),columns=list(vars_values.keys()) + [d[0] if d[0] else "y" for d in dataset])
            pd.options.display.float_format = "{:,.2f}".format
            print("Correlation matrix:")

            corr = df.corr()
            corr = corr.dropna(axis=0,how='all')

            corr = corr.dropna(axis=1,how='all')
            keep = np.triu(np.ones(corr.shape)).astype(bool)
            corr = corr.where(keep==True, np.nan)
            print(corr.fillna(""))

            import seaborn as sn
            import matplotlib.pyplot as plt
            ax = sn.heatmap(corr, cmap="viridis", fmt=".2f", annot=True)
            ax.figure.tight_layout()
            f = npf.build_filename(test, build, filename if not filename is True else None, {}, 'pdf', result_type, show_serie=False, suffix="correlation")
            plt.savefig(f)
            print(f"Graph of correlation matrix saved to {f}")

            plt.clf()

            import statsmodels.api as sm

            from statsmodels.formula.api import ols
            variables = [k for k,v in vars_values.items() if len(v) > 1]

            m = result_type + ' ~ ' +' * '.join( [f"{v}" for v in variables])

            pd.set_option("display.max_rows", None)

            dfn = df[variables + [result_type]].replace([np.inf, -np.inf], np.nan).dropna(axis=1)
            dfn = dfn.replace([np.inf, -np.inf], np.nan).dropna(axis=0)

            model =  ols(m, data=dfn).fit()

            anova_table = sm.stats.anova_lm(model, typ=2)

            interaction_pvalues = anova_table.loc[anova_table.index.str.count(':') <= 1, 'PR(>F)']

            interaction_matrix = pd.DataFrame(np.nan, index=variables, columns=variables + [result_type])

            for interaction in interaction_pvalues.index:
                if interaction == "Residual":
                    continue
                factors = interaction.split(':')

                if len(factors) > 1:
                    interaction_matrix.loc[factors[0], factors[1]] = interaction_pvalues[interaction]
                    #interaction_matrix.loc[factors[1], factors[0]] = interaction_pvalues[interaction]
                else:
                    interaction_matrix.loc[factors[0],result_type] = interaction_pvalues[interaction]

            print("")
            print("P-value of ANOVA (low p-value indicates a probable interaction):")
            print(interaction_matrix.fillna(""))
            ax = sn.heatmap(interaction_matrix, cmap="viridis", fmt=".2f", annot=True)
            ax.figure.tight_layout()
            f = npf.build_filename(test, build, filename if not filename is True else None, {}, 'pdf', result_type, show_serie=False, suffix="anova")
            plt.savefig(f)
            print(f"Graph of a ANOVA matrix saved to {f}")

            pd.reset_option("display.float_format")

    @classmethod
    def buildDataset(cls, all_results: Dataset, test: Test) -> List[tuple]:
        #map of every <variable name, format>
        dtype = test.variables.dtype()

        y = OrderedDict()
        dataset = []
        for i, (run, results_types) in enumerate(all_results.items()):
            vars = list(run.read_variables()[k] for k in dtype['names'])
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
